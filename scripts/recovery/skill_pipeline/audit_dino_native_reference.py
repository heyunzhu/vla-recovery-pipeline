#!/usr/bin/env python3
"""Run the pinned IDEA-Research entrypoint on the same audit frames/captions.

CPU uses the upstream PyTorch deformable-attention fallback, so no custom CUDA
kernel or native source patch is required. The config may relocate BERT files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--native-source", type=Path, required=True)
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--checkpoint", type=Path, required=True)
    p.add_argument("--hf-audit", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--device", default="cpu")
    args = p.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("use a new output directory")
    sys.path.insert(0, str(args.native_source))
    import numpy as np
    import torch
    import transformers
    from PIL import Image, ImageDraw
    from groundingdino.util.inference import load_image, load_model, predict

    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    model = load_model(str(args.config), str(args.checkpoint), device=args.device).to(args.device).eval()
    write(args.output / "environment.json", {"torch": torch.__version__, "transformers": transformers.__version__,
                                            "device": args.device, "native_source": str(args.native_source),
                                            "config": str(args.config), "checkpoint": str(args.checkpoint),
                                            "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    rows = []
    for case in json.loads(args.manifest.read_text())["cases"]:
        image_path = args.evidence / case["image"]
        if hashlib.sha256(image_path.read_bytes()).hexdigest() != case["image_sha256"]:
            raise ValueError("RGB source changed")
        rgb, pixels = load_image(str(image_path))
        for mode in ("full_joint", "task_joint"):
            hf_dir = args.hf_audit / case["case"] / mode
            hf = json.loads((hf_dir / "comparison.json").read_text())
            hf_arrays = np.load(hf_dir / "official_raw.npz")
            captured = {}

            def capture(_model, _inputs, output):
                captured.update({k: v.detach().cpu().numpy() for k, v in output.items()
                                 if k in ("pred_logits", "pred_boxes")})

            handle = model.register_forward_hook(capture)
            try:
                boxes, scores, phrases = predict(model=model, image=pixels, caption=hf["caption"],
                                                box_threshold=.25, text_threshold=.35, device=args.device)
            finally:
                handle.remove()
            a = pixels.unsqueeze(0).cpu().numpy(); b = hf_arrays["pixel_values"]
            token_ids = model.tokenizer(hf["caption"])["input_ids"]
            shape_equal = a.shape == b.shape
            preprocess_diff = float(np.max(np.abs(a - b))) if shape_equal else None
            out = args.output / case["case"] / mode
            out.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(out / "native_raw.npz", **captured, input_ids=np.asarray(token_ids), pixel_values=a)
            native = []
            for box, score, phrase in zip(boxes.cpu(), scores.cpu(), phrases):
                cx, cy, w, h = box.tolist(); H, W = rgb.shape[:2]
                native.append({"box_xyxy": [(cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H],
                               "score": float(score), "text_label": phrase})
            cross = None
            if shape_equal and preprocess_diff > 1e-6:
                # Isolate preprocessing differences from model implementation.
                cross_boxes, cross_scores, cross_phrases = predict(
                    model=model, image=torch.from_numpy(b[0]), caption=hf["caption"],
                    box_threshold=.25, text_threshold=.35, device=args.device)
                cross = []
                for box, score, phrase in zip(cross_boxes.cpu(), cross_scores.cpu(), cross_phrases):
                    cx, cy, w, h = box.tolist(); H, W = rgb.shape[:2]
                    cross.append({"box_xyxy": [(cx-w/2)*W, (cy-h/2)*H, (cx+w/2)*W, (cy+h/2)*H],
                                  "score": float(score), "text_label": phrase})
            row = {"case": case["case"], "mode": mode, "caption": hf["caption"],
                   "same_input_shape": shape_equal, "input_pixel_max_abs": preprocess_diff,
                   "same_token_ids": token_ids == hf["input_ids"][0],
                   "native_boxes": native, "hf_boxes": hf["official_boxes"],
                   "native_with_hf_pixels_boxes": cross,
                   "native_raw_shapes": {k: list(v.shape) for k, v in captured.items()}}
            write(out / "comparison.json", row)
            canvas = Image.fromarray(rgb).resize((768, 768)); draw = ImageDraw.Draw(canvas)
            for item in native:
                box = [max(0, min(767, v*3)) for v in item["box_xyxy"]]
                draw.rectangle(box, outline="lime", width=2)
                draw.text((box[0], max(0, box[1]-12)), f'{item["text_label"] or "EMPTY"} {item["score"]:.3f}',
                          fill="lime", stroke_fill="black", stroke_width=1)
            canvas.save(out / "native_boxes.png")
            rows.append(row); write(args.output / "summary.json", rows)
        print(json.dumps({"completed_case": case["case"], "comparisons": len(rows)}), flush=True)
    write(args.output / "completed.json", {"comparisons": len(rows)})


if __name__ == "__main__":
    main()
