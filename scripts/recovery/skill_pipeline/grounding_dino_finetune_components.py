"""MMDetection transforms/hooks used only by the isolated detector training job."""
from pathlib import Path
import json
import math

import numpy as np
from mmcv.transforms import BaseTransform
from mmengine.hooks import Hook
from mmdet.registry import HOOKS, TRANSFORMS


@TRANSFORMS.register_module()
class SampleTaskDetectionPrompt(BaseTransform):
    """Mix full-vocabulary, subset, and single-class (including absent) queries.

    Keep every GT instance belonging to the chosen classes, and remap its class
    index to the actual caption order. Unqueried objects are not relabeled.
    """
    def __init__(self, aliases=None):
        self.aliases = aliases or {}

    def transform(self, results):
        names = tuple(results["text"])
        labels = np.asarray(results["gt_bboxes_labels"], dtype=np.int64)
        present = np.unique(labels)
        absent = np.asarray([i for i in range(len(names)) if i not in present])
        draw = np.random.random()
        if draw < .35:
            pool = absent if len(absent) and np.random.random() < .5 else present
            if not len(pool): pool = np.arange(len(names))
            chosen = np.asarray([int(np.random.choice(pool))])
        elif draw < .60:
            chosen = np.sort(np.random.choice(len(names), size=min(len(names), np.random.randint(2, 5)), replace=False))
        else:
            chosen = np.arange(len(names))
        keep = np.isin(labels, chosen)
        lookup = {int(old): new for new, old in enumerate(chosen)}
        results["gt_bboxes"] = results["gt_bboxes"][keep]
        results["gt_bboxes_labels"] = np.asarray([lookup[int(i)] for i in labels[keep]], dtype=np.int64)
        if "gt_ignore_flags" in results: results["gt_ignore_flags"] = results["gt_ignore_flags"][keep]
        if "gt_masks" in results: results["gt_masks"] = results["gt_masks"][keep]
        captions = tuple(str(np.random.choice(self.aliases.get(names[int(i)], [names[int(i)]]))) for i in chosen)
        results["text"] = captions if len(set(captions)) == len(captions) else tuple(names[int(i)] for i in chosen)
        results["custom_entities"] = True
        return results


@HOOKS.register_module()
class FreezeDetectorLanguageHook(Hook):
    priority = "VERY_HIGH"

    @staticmethod
    def model(runner):
        return getattr(runner.model, "module", runner.model)

    def before_run(self, runner):
        model = self.model(runner)
        for parameter in model.language_model.parameters(): parameter.requires_grad_(False)
        audit = {"total_parameters": sum(p.numel() for p in model.parameters()),
                 "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
                 "language_trainable_parameters": sum(p.numel() for p in model.language_model.parameters() if p.requires_grad),
                 "trainable_names": [n for n,p in model.named_parameters() if p.requires_grad]}
        assert audit["language_trainable_parameters"] == 0
        Path(runner.work_dir, "parameter_audit.json").write_text(json.dumps(audit, indent=2))

    def before_train_iter(self, runner, batch_idx, data_batch=None):
        self.model(runner).language_model.eval()
        if runner.iter < 24 and data_batch:
            rows = [{"text":list(sample.text),"gt_count":len(sample.gt_instances),
                     "labels":sample.gt_instances.labels.tolist()} for sample in data_batch.get("data_samples", [])]
            with Path(runner.work_dir,"training_prompt_audit.jsonl").open("a") as stream:
                stream.write(json.dumps({"iteration":runner.iter,"samples":rows})+"\n")

    def before_train(self, runner):
        name, parameter = next((n,p) for n,p in self.model(runner).named_parameters()
                               if n.endswith("patch_embed.projection.weight"))
        self.reference_name = name
        self.reference = parameter.detach().flatten()[:4096].cpu().clone()
        self.language_reference = next(self.model(runner).language_model.parameters()).detach().flatten()[:4096].cpu().clone()

    def after_train(self, runner):
        parameter = dict(self.model(runner).named_parameters())[self.reference_name]
        current = parameter.detach().flatten()[:4096].cpu()
        delta = (current-self.reference).abs()
        language_current = next(self.model(runner).language_model.parameters()).detach().flatten()[:4096].cpu()
        audit = {"parameter":self.reference_name,"sampled_values":current.numel(),
                 "changed_values":int((delta>0).sum()),"max_abs_delta":float(delta.max()),
                 "all_finite":bool(current.isfinite().all()),
                 "language_sampled_changed_values":int((language_current!=self.language_reference).sum())}
        Path(runner.work_dir,"update_audit.json").write_text(json.dumps(audit,indent=2))
        if not audit["all_finite"] or not audit["changed_values"] or audit["language_sampled_changed_values"]:
            raise RuntimeError(f"training did not produce finite parameter updates: {audit}")

    def after_train_iter(self, runner, batch_idx, data_batch=None, outputs=None):
        if "train/grad_norm" in runner.message_hub.log_scalars:
            norm = float(runner.message_hub.get_scalar("train/grad_norm").current())
            if not math.isfinite(norm): raise RuntimeError(f"non-finite gradient norm: {norm}")
        if not outputs: return
        for key, value in outputs.items():
            if "loss" in key and hasattr(value, "item"): value = value.item()
            if "loss" in key and isinstance(value, (int,float)) and not math.isfinite(value):
                raise RuntimeError(f"non-finite training loss: {key}={value}")
