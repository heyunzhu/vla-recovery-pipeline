#!/usr/bin/env python3
"""Run documented HF caption-string inference in an independent dependency version."""
import argparse
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--model", type=Path, required=True)
    p.add_argument("--reference-audit", type=Path, required=True)
    p.add_argument("--evidence", type=Path, required=True)
    p.add_argument("--manifest", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    import numpy as np
    import torch
    import transformers
    from PIL import Image
    from transformers import AutoModelForZeroShotObjectDetection, AutoProcessor

    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("use an empty output directory")
    args.output.mkdir(parents=True, exist_ok=True)
    torch.set_num_threads(4)
    processor = AutoProcessor.from_pretrained(str(args.model), local_files_only=True)
    model = AutoModelForZeroShotObjectDetection.from_pretrained(str(args.model), local_files_only=True).eval()
    (args.output / "environment.json").write_text(json.dumps({"torch": torch.__version__, "transformers": transformers.__version__, "device": "cpu"}, indent=2))
    rows = []
    for case in json.loads(args.manifest.read_text())["cases"]:
        image = Image.open(args.evidence / case["image"]).convert("RGB")
        for mode in ("full_joint", "task_joint"):
            ref = args.reference_audit / case["case"] / mode
            caption = json.loads((ref / "comparison.json").read_text())["caption"]
            inputs = processor(images=image, text=caption, return_tensors="pt")
            with torch.no_grad():
                output = model(**inputs)
            result = processor.post_process_grounded_object_detection(output, inputs.input_ids,
                        box_threshold=.25, text_threshold=.35, target_sizes=[image.size[::-1]])[0]
            boxes = [{"box_xyxy": b.tolist(), "score": float(s), "text_label": str(t)}
                     for b, s, t in zip(result["boxes"], result["scores"], result.get("text_labels", result["labels"]))]
            out = args.output / case["case"] / mode; out.mkdir(parents=True)
            np.savez_compressed(out / "raw.npz", logits=output.logits.numpy(), pred_boxes=output.pred_boxes.numpy(),
                                input_ids=inputs.input_ids.numpy(), pixel_values=inputs.pixel_values.numpy())
            row = {"case": case["case"], "mode": mode, "caption": caption, "boxes": boxes}
            (out / "result.json").write_text(json.dumps(row, indent=2))
            rows.append(row); (args.output / "summary.json").write_text(json.dumps(rows, indent=2))
        print(json.dumps({"completed_case": case["case"], "comparisons": len(rows)}), flush=True)
    (args.output / "completed.json").write_text(json.dumps({"comparisons": len(rows)}))


if __name__ == "__main__":
    main()
