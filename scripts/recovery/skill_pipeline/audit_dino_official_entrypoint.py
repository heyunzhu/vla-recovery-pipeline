#!/usr/bin/env python3
"""Audit HF documented inference against the recovery DINO wrapper on fixed RGBs.

This is a detector-only diagnostic. It does not run SAM, a simulator, or training.
Use the independent native-repository runner for cross-implementation validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--code-root", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", default="cuda:0")
    args = p.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("preserve previous artifacts; use an empty output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    sys.path.insert(0, str(args.code_root))
    import numpy as np
    import torch
    import transformers
    from PIL import Image, ImageDraw
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor
    from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector, _resolve_grounded_boxes
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language

    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    processor = AutoProcessor.from_pretrained(str(args.model), local_files_only=True)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(str(args.model), local_files_only=True).to(args.device).eval()
    # Reuse the exact production DINO method; omit only SAM initialization.
    # Constructor DINO load arguments are the same as the documented calls above.
    wrapper = GroundedSam2Detector.__new__(GroundedSam2Detector)
    wrapper._torch = torch
    wrapper.grounding_processor = processor
    wrapper.grounding_model = model
    wrapper.device = args.device
    wrapper.box_threshold = 0.25
    wrapper.text_threshold = 0.35
    wrapper.grounding_mode = "joint"
    manifest = json.loads(args.manifest.read_text())
    dump(args.output / "environment.json", {
        "torch": torch.__version__, "transformers": transformers.__version__,
        "model_sha256": digest(args.model / "model.safetensors"),
        "model_config": model.config.to_dict(), "tf32": False,
        "device": args.device, "script_sha256": digest(Path(__file__)),
        "wrapper_sha256": digest(Path(sys.modules[GroundedSam2Detector.__module__].__file__))})
    rows = []
    for case in manifest["cases"]:
        image_path = args.evidence / case["image"]
        if digest(image_path) != case["image_sha256"]:
            raise ValueError("fixed image SHA256 changed")
        image = Image.open(image_path).convert("RGB")
        rgb = np.array(image)
        prompts_by_mode = {"full_joint": case["prompts"], "task_joint": prompts_from_task_language(case["language"])}
        for mode, prompts in prompts_by_mode.items():
            caption = ". ".join(prompts.values()).lower().strip() + "."
            official_inputs = processor(images=image, text=caption, return_tensors="pt").to(args.device)
            ours_inputs = processor(images=np.ascontiguousarray(rgb), text=[list(prompts.values())], return_tensors="pt").to(args.device)
            input_checks = {k: bool(torch.equal(official_inputs[k], ours_inputs[k])) for k in official_inputs}
            with torch.no_grad():
                official_outputs = model(**official_inputs)
            captured = {}

            def capture(_module, _inputs, outputs):
                captured["logits"] = outputs.logits.detach().cpu()
                captured["pred_boxes"] = outputs.pred_boxes.detach().cpu()

            handle = model.register_forward_hook(capture)
            wrapper.prompts = prompts
            error = None
            try:
                boxes, categories, scores = wrapper._ground_image(rgb, rgb.shape[:2])
            except Exception as exc:
                error = {"type": type(exc).__name__, "message": str(exc)}
                boxes, categories, scores = [], [], []
            finally:
                handle.remove()
            official = processor.post_process_grounded_object_detection(
                official_outputs, official_inputs.input_ids, threshold=.25, text_threshold=.35,
                target_sizes=[rgb.shape[:2]])[0]
            raw = [{"box_xyxy": b.tolist(), "score": float(s), "text_label": str(t)}
                   for b, s, t in zip(official["boxes"].cpu(), official["scores"].cpu(),
                                      official.get("text_labels", official.get("labels", [])))]
            filtered_error = None
            try:
                ref_boxes, ref_categories, ref_scores = _resolve_grounded_boxes(official, prompts, rgb.shape[:2])
            except Exception as exc:
                filtered_error = {"type": type(exc).__name__, "message": str(exc)}
                ref_boxes, ref_categories, ref_scores = [], [], []
            d = args.output / case["case"] / mode
            d.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(d / "official_raw.npz", logits=official_outputs.logits.cpu().numpy(),
                                pred_boxes=official_outputs.pred_boxes.cpu().numpy(),
                                input_ids=official_inputs.input_ids.cpu().numpy(),
                                pixel_values=official_inputs.pixel_values.cpu().numpy())
            np.savez_compressed(d / "wrapper_raw.npz", **{k: v.numpy() for k, v in captured.items()})
            diff = {}
            for key, official_tensor in (("logits", official_outputs.logits), ("pred_boxes", official_outputs.pred_boxes)):
                a = official_tensor.detach().cpu(); b = captured[key]
                finite = torch.isfinite(a) & torch.isfinite(b)
                diff[key] = {"exact_equal": bool(torch.equal(a, b)),
                             "finite_max_abs": float((a[finite] - b[finite]).abs().max()) if finite.any() else 0.,
                             "same_nonfinite_mask": bool(torch.equal(torch.isfinite(a), torch.isfinite(b)))}
            row = {"case": case["case"], "mode": mode, "caption": caption,
                   "input_tensor_equal": input_checks, "raw_output_comparison": diff,
                   "raw_boxes_equal": raw == wrapper.last_grounding_boxes,
                   "filtered_equal": boxes == ref_boxes and categories == ref_categories and scores == ref_scores,
                   "wrapper_error": error, "reference_filter_error": filtered_error,
                   "official_boxes": raw, "wrapper_boxes": wrapper.last_grounding_boxes,
                   "retained_categories": categories,
                   "input_ids": official_inputs.input_ids.cpu().tolist()}
            dump(d / "comparison.json", row)
            canvas = image.resize((768, 768)); draw = ImageDraw.Draw(canvas)
            for b in raw:
                box = [max(0, min(767, v * 3)) for v in b["box_xyxy"]]
                draw.rectangle(box, outline="lime", width=2)
                draw.text((box[0], max(0, box[1] - 12)), f'{b["text_label"] or "EMPTY"} {b["score"]:.3f}',
                          fill="lime", stroke_fill="black", stroke_width=1)
            canvas.save(d / "official_boxes.png")
            rows.append(row)
            dump(args.output / "summary.json", rows)
        print(json.dumps({"completed_case": case["case"], "comparisons": len(rows)}), flush=True)
    dump(args.output / "completed.json", {"comparisons": len(rows)})


if __name__ == "__main__":
    main()
