"""Optional frozen Grounding DINO + SAM 2 backend for offline RGB frames.

This module imports model libraries only when instantiated. It receives an
RGBDObservation, but passes only its RGB array to the models. Prompts are
explicit configuration, never generated from simulator object names.
"""

from __future__ import annotations

from typing import Mapping
import os

import numpy as np

from .rgbd_observation import RGBDObservation
from .rgbd_scene import VisualDetection


def _normal_label(value: str) -> str:
    text = value.strip().lower().strip(". ")
    for article in ("a ", "an ", "the "):
        if text.startswith(article):
            return text[len(article) :]
    return text


def _to_numpy(value: object) -> np.ndarray:
    if hasattr(value, "detach"):
        value = value.detach().cpu()
    return np.asarray(value)


def _resolve_grounded_boxes(
    result: Mapping[str, object],
    prompts: Mapping[str, str],
    image_shape: tuple[int, int],
) -> tuple[list[list[float]], list[str], list[float]]:
    """Keep every allowed instance with a finite, nonempty image box."""

    names = {_normal_label(prompt): category for category, prompt in prompts.items()}
    labels = result.get("text_labels", result.get("labels"))
    if labels is None:
        raise ValueError("Grounding DINO result has no text labels")
    boxes = np.asarray(_to_numpy(result["boxes"]), dtype=np.float64)
    scores = np.asarray(_to_numpy(result["scores"]), dtype=np.float64)
    # Transformers 5.19 can return one empty decoded phrase for zero boxes.
    # Treat only that observed processor artifact as an empty detection result.
    if (boxes.shape == (0, 4) and scores.shape == (0,) and len(labels) == 1
            and not _normal_label(str(labels[0]))):
        return [], [], []
    if boxes.ndim != 2 or boxes.shape[1] != 4 or scores.shape != (len(boxes),) or len(labels) != len(boxes):
        raise ValueError("Grounding DINO result has inconsistent boxes, scores, or labels")
    height, width = image_shape
    selected_boxes: list[list[float]] = []
    selected_categories: list[str] = []
    selected_scores: list[float] = []
    for box, score, label in zip(boxes, scores, labels):
        category = names.get(_normal_label(str(label)))
        if category is None:
            continue
        if not np.isfinite(box).all() or not np.isfinite(score):
            raise ValueError("Grounding DINO produced nonfinite box or score")
        x0, y0, x1, y1 = np.clip(box, [0, 0, 0, 0], [width, height, width, height]).tolist()
        if x1 - x0 < 2 or y1 - y0 < 2:
            continue
        selected_boxes.append([x0, y0, x1, y1])
        selected_categories.append(category)
        selected_scores.append(float(score))
    return selected_boxes, selected_categories, selected_scores


class GroundedSam2Detector:
    def __init__(
        self,
        *,
        grounding_model: str,
        grounding_revision: str,
        sam2_model: str,
        sam2_revision: str,
        prompts: Mapping[str, str],
        box_threshold: float = 0.25,
        text_threshold: float = 0.25,
        device: str = "cpu",
        cache_dir: str | None = None,
        grounding_mode: str = "joint",
        mmdet_export: bool = False,
        mmdet_native_config: str | None = None,
    ) -> None:
        if not grounding_model or not grounding_revision or not sam2_model or not sam2_revision or not prompts:
            raise ValueError("pinned model references and at least one visual prompt are required")
        if any(not category.strip() or not prompt.strip() for category, prompt in prompts.items()):
            raise ValueError("visual categories and prompts cannot be blank")
        if len({_normal_label(prompt) for prompt in prompts.values()}) != len(prompts):
            raise ValueError("visual prompts must be unique after normalization")
        if not (0 < box_threshold <= 1 and 0 < text_threshold <= 1):
            raise ValueError("model thresholds must be in (0, 1]")

        if grounding_mode not in ("joint", "per_category"):
            raise ValueError("grounding mode must be joint or per_category")

        import torch
        from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor, Sam2Model, Sam2Processor

        self._torch = torch
        self.prompts = dict(prompts)
        self.box_threshold = box_threshold
        self.text_threshold = text_threshold
        self.device = device
        self.grounding_mode = grounding_mode
        self.mmdet_export = mmdet_export
        self.mmdet_native_config = mmdet_native_config
        if mmdet_native_config and mmdet_export:
            raise ValueError('native MMDetection and HF export modes are mutually exclusive')
        self.dino_worker_python = os.environ.get('DINO_INFERENCE_PYTHON') if (mmdet_export or mmdet_native_config) else None
        if mmdet_native_config and not self.dino_worker_python:
            raise ValueError('native MMDetection requires its isolated worker Python')
        self.export_directory = grounding_model
        self.grounding_processor = None if self.dino_worker_python else AutoProcessor.from_pretrained(
            grounding_model, revision=grounding_revision, cache_dir=cache_dir, local_files_only=True
        )
        if self.dino_worker_python:
            self.grounding_model = None
        elif mmdet_export:
            from scripts.recovery.skill_pipeline.export_grounding_dino_libero_hf import load_exported_hf_detector
            self.grounding_model = load_exported_hf_detector(grounding_model, device)
        else:
            self.grounding_model = AutoModelForZeroShotObjectDetection.from_pretrained(
                grounding_model, revision=grounding_revision, cache_dir=cache_dir,
                use_safetensors=True, local_files_only=True
            ).to(device).eval()
        self.sam2_processor = Sam2Processor.from_pretrained(
            sam2_model, revision=sam2_revision, cache_dir=cache_dir, local_files_only=True
        )
        self.sam2_model = Sam2Model.from_pretrained(
            sam2_model, revision=sam2_revision, cache_dir=cache_dir,
            use_safetensors=True, local_files_only=True
        ).to(device).eval()

    def __call__(self, frame: RGBDObservation) -> list[VisualDetection]:
        height, width = frame.rgb.shape[:2]
        image = np.ascontiguousarray(frame.rgb)
        boxes, categories, scores = self._ground_image(image, (height, width))
        if not boxes:
            return []
        sam_inputs = self.sam2_processor(images=image, input_boxes=[boxes], return_tensors="pt").to(self.device)
        with self._torch.no_grad():
            sam_output = self.sam2_model(**sam_inputs, multimask_output=False)
        masks = self.sam2_processor.post_process_masks(sam_output.pred_masks.cpu(), sam_inputs["original_sizes"])[0]
        masks = np.asarray(masks)
        if masks.shape != (len(boxes), 1, height, width):
            raise ValueError(f"SAM 2 returned unexpected mask shape {masks.shape}")
        return [
            VisualDetection(mask=np.asarray(masks[i, 0], dtype=bool), category=categories[i], raw_score=scores[i],
                            source="text_guided_segmentation")
            for i in range(len(boxes))
            if np.asarray(masks[i, 0]).any()
        ]

    def _ground_image(self, image, image_shape):
        """Resolve exact labels inside each query; never assign a category by score."""
        height, width = image_shape
        queries = ([self.prompts] if self.grounding_mode == "joint" else
                   [{category: prompt} for category, prompt in self.prompts.items()])
        all_boxes, all_categories, all_scores = [], [], []
        self.last_grounding_boxes = []
        for query in queries:
            if getattr(self, 'dino_worker_python', None):
                result = self._worker_ground_image(image, query)
                for box,score,label in zip(result['boxes'],result['scores'],result['text_labels']):
                    self.last_grounding_boxes.append({'box_xyxy':box,'score':score,'text_label':label})
                result['boxes']=np.asarray(result['boxes'],dtype=np.float64).reshape(-1,4)
                boxes,categories,scores = _resolve_grounded_boxes(result,query,image_shape)
                all_boxes.extend(boxes);all_categories.extend(categories);all_scores.extend(scores)
                continue
            converted = getattr(self, 'mmdet_export', False)
            text = '. '.join(query.values())+'.' if converted else [list(query.values())]
            inputs = self.grounding_processor(images=image, text=text, return_tensors="pt").to(self.device)
            with self._torch.no_grad():
                output = self.grounding_model(**inputs)
            if converted:
                from scripts.recovery.skill_pipeline.grounding_dino_entity_postprocess import entity_token_indices, entity_detections
                tokens = entity_token_indices(self.grounding_processor.tokenizer, text, list(query.values()))
                boxes, scores, labels = entity_detections(output.logits[0], output.pred_boxes[0], tokens, (height,width))
                keep = scores >= self.box_threshold
                result = {'boxes': boxes[keep], 'scores': scores[keep],
                          'text_labels': [list(query.values())[i] for i in labels[keep].tolist()]}
            else:
                result = self.grounding_processor.post_process_grounded_object_detection(
                    output, inputs.input_ids, threshold=self.box_threshold,
                    text_threshold=self.text_threshold, target_sizes=[(height, width)])[0]
            for box, score, label in zip(_to_numpy(result["boxes"]).tolist(),
                                         _to_numpy(result["scores"]).tolist(),
                                         result.get("text_labels", result.get("labels", []))):
                row = {"box_xyxy": box, "score": float(score), "text_label": str(label)}
                if self.grounding_mode == "per_category":
                    row["query_category"] = next(iter(query))
                self.last_grounding_boxes.append(row)
            boxes, categories, scores = _resolve_grounded_boxes(result, query, image_shape)
            all_boxes.extend(boxes)
            all_categories.extend(categories)
            all_scores.extend(scores)
        return all_boxes, all_categories, all_scores

    def _worker_ground_image(self, image, query):
        import json
        from pathlib import Path
        import subprocess
        import tempfile
        from PIL import Image
        parent=Path(os.environ['DINO_INFERENCE_WORKDIR'])
        parent.mkdir(parents=True,exist_ok=True)
        directory=Path(tempfile.mkdtemp(prefix='query_',dir=parent))
        Image.fromarray(image).save(directory/'rgb.png')
        (directory/'prompts.json').write_text(json.dumps(query))
        env=dict(os.environ,PYTHONPATH=os.environ['DINO_INFERENCE_PYTHONPATH'])
        native_config = getattr(self, 'mmdet_native_config', None)
        module = 'scripts.recovery.skill_pipeline.resident_mmdet_grounding_dino_worker' if native_config else 'scripts.recovery.skill_pipeline.grounding_dino_export_worker'
        model_args = ['--config',native_config,'--checkpoint',self.export_directory] if native_config else ['--export',self.export_directory]
        command=[self.dino_worker_python,'-m',module,*model_args,'--rgb',str(directory/'rgb.png'),
                 '--prompts',str(directory/'prompts.json'),'--output',str(directory/'result.json'),
                 '--device',self.device,'--threshold',str(self.box_threshold)]
        (directory/'command.json').write_text(json.dumps(command,indent=2))
        if os.environ.get('DINO_RESIDENT_WORKER') == '1':
            from .resident_vision import JSONLineProcess
            if not hasattr(self, '_resident_dino'):
                self._resident_dino = JSONLineProcess([
                    self.dino_worker_python,'-m',module if native_config else 'scripts.recovery.skill_pipeline.resident_grounding_dino_worker',
                    *model_args,'--device',self.device,
                    '--threshold',str(self.box_threshold)],env=env,log_path=parent/'resident_dino.log',
                    cwd=os.environ.get('ANCHOR_VISUAL_CODE'))
            self._resident_dino.request(dict(rgb=str(directory/'rgb.png'),
                prompts=str(directory/'prompts.json'),output=str(directory/'result.json')))
        else:
            with (directory/'worker.log').open('w') as log:
                subprocess.run(command,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180,check=True)
        result=json.loads((directory/'result.json').read_text())
        self.last_dino_ms=result.get('dino_ms')
        return result
