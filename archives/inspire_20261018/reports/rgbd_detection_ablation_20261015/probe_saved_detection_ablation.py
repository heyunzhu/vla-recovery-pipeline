#!/usr/bin/env python3
"""Compare frozen-frame detector queries without executing recovery or a simulator.

Run --prepare-only locally first. Inference requires the existing pinned local
model directories; this script never downloads models or changes their files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def prepare(evidence):
    cases, skipped = [], []
    for case in sorted(evidence.glob("[0-9][0-9]_*")):
        configs = list(case.glob("visual/visual_nomination*/run_config.json"))
        if not configs:
            skipped.append({"case": case.name, "reason": "no_detector_run_config"})
            continue
        if len(configs) != 1:
            raise ValueError(f"ambiguous detector configuration: {case}")
        config = json.loads(configs[0].read_text(encoding="utf-8"))
        image = configs[0].parent / "recovery01/pre_solver_attempt01/agentview/rgb.png"
        snapshot = case / "visual/snapshots/recovery01/pre_solver_attempt01/agentview"
        cases.append({"case": case.name, "language": config["language"],
                      "prompts": config["prompts"], "image": str(image.relative_to(evidence)),
                      "snapshot": str(snapshot.relative_to(evidence)),
                      "image_sha256": sha256(image),
                      "snapshot_sha256": sha256(snapshot / "rgbd.npz"),
                      "original_config": str(configs[0].relative_to(evidence))})
    return {"cases": cases, "skipped": skipped, "text_thresholds": [0.25, 0.30, 0.35],
            "box_threshold": 0.25,
            "variants": ["full_joint", "task_joint", "full_per_category", "task_per_category"],
            "note": "Fixed original RGB frames; scores and class presence are not accuracy labels."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--code-root", type=Path)
    parser.add_argument("--grounding-model-dir", type=Path)
    parser.add_argument("--sam2-model-dir", type=Path)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--prepare-only", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        raise ValueError("output must be empty; preserve prior experimental artifacts")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = prepare(args.evidence)
    manifest["script_sha256"] = sha256(Path(__file__))
    write_json(args.output / "manifest.json", manifest)
    if args.prepare_only:
        print(json.dumps({"cases": len(manifest["cases"]), "skipped": manifest["skipped"],
                          "comparisons": len(manifest["cases"]) * 12}))
        return
    if not all((args.code_root, args.grounding_model_dir, args.sam2_model_dir)):
        parser.error("inference requires code-root and both model directories")
    sys.path.insert(0, str(args.code_root))
    import numpy as np
    import torch
    import transformers
    from PIL import Image, ImageDraw
    from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import (
        GroundedSam2Detector, _normal_label, _resolve_grounded_boxes, _to_numpy)
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    from scripts.recovery.skill_pipeline.run_grounded_sam2_snapshot import (
        _verify_model_weights, GROUNDING_SHA256, SAM2_SHA256, GROUNDING_REVISION, SAM2_REVISION)

    grounding = _verify_model_weights(args.grounding_model_dir, GROUNDING_SHA256)
    sam = _verify_model_weights(args.sam2_model_dir, SAM2_SHA256)
    detector = GroundedSam2Detector(grounding_model=str(grounding), grounding_revision=GROUNDING_REVISION,
                                  sam2_model=str(sam), sam2_revision=SAM2_REVISION,
                                  prompts=manifest["cases"][0]["prompts"], device=args.device)
    write_json(args.output / "environment.json", {
        "torch": torch.__version__, "transformers": transformers.__version__,
        "grounding_sha256": GROUNDING_SHA256, "sam2_sha256": SAM2_SHA256,
        "backend_sha256": sha256(Path(sys.modules[GroundedSam2Detector.__module__].__file__)),
        "device": args.device})
    summary = []
    for case in manifest["cases"]:
        case_out = args.output / case["case"]
        frame = load_observation(args.evidence / case["snapshot"])
        rgb = np.ascontiguousarray(frame.rgb)
        with Image.open(args.evidence / case["image"]) as saved:
            if not np.array_equal(rgb, np.asarray(saved.convert("RGB"))):
                raise ValueError("saved PNG and RGB-D RGB differ")
        full = case["prompts"]
        task = prompts_from_task_language(case["language"])
        write_json(case_out / "prompts.json", {"full": full, "task": task})
        queries = {"full_joint": full, "task_joint": task}
        queries.update({"single_" + key: {key: value} for key, value in full.items()})
        query_results = {}
        for query_name, prompts in queries.items():
            inputs = detector.grounding_processor(images=rgb, text=[list(prompts.values())],
                                                  return_tensors="pt").to(args.device)
            with torch.no_grad():
                output = detector.grounding_model(**inputs)
            qdir = case_out / "queries" / query_name
            qdir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(qdir / "raw_model_output.npz", logits=_to_numpy(output.logits),
                                pred_boxes=_to_numpy(output.pred_boxes),
                                input_ids=_to_numpy(inputs.input_ids))
            # Preserve the actual resized model input to audit image preprocessing.
            pixels = _to_numpy(inputs.pixel_values)[0]
            processor = detector.grounding_processor.image_processor
            restored = pixels.transpose(1, 2, 0) * np.asarray(processor.image_std) + np.asarray(processor.image_mean)
            Image.fromarray(np.clip(restored * 255, 0, 255).astype("uint8")).save(qdir / "model_input.png")
            tokens = detector.grounding_processor.tokenizer.convert_ids_to_tokens(inputs.input_ids[0].tolist())
            write_json(qdir / "tokens.json", tokens)
            for threshold in manifest["text_thresholds"]:
                result = detector.grounding_processor.post_process_grounded_object_detection(
                    output, inputs.input_ids, threshold=0.25, text_threshold=threshold,
                    target_sizes=[rgb.shape[:2]])[0]
                raw = []
                allowed = {_normal_label(v) for v in prompts.values()}
                for box, score, label in zip(_to_numpy(result["boxes"]), _to_numpy(result["scores"]),
                                             result.get("text_labels", result.get("labels", []))):
                    normal = _normal_label(str(label))
                    reason = "kept" if normal in allowed else ("empty_label" if not normal else "non_exact_label")
                    if reason == "kept":
                        x0, y0, x1, y1 = np.clip(box, [0, 0, 0, 0], [rgb.shape[1], rgb.shape[0]] * 2)
                        if x1 - x0 < 2 or y1 - y0 < 2:
                            reason = "small_or_empty_box"
                    raw.append({"box_xyxy": box.tolist(), "score": float(score),
                                "text_label": str(label), "filter_reason": reason, "query": query_name})
                boxes, categories, scores = _resolve_grounded_boxes(result, prompts, rgb.shape[:2])
                query_results[(query_name, threshold)] = (raw, boxes, categories, scores)
                write_json(qdir / f"threshold_{threshold:.2f}.json", raw)
                if query_name == "full_joint" and threshold == 0.35:
                    original = json.loads((args.evidence / case["image"]).with_name(
                        "grounding_boxes.json").read_text(encoding="utf-8"))
                    matched = len(original) == len(raw) and all(
                        a["text_label"] == b["text_label"]
                        and np.allclose(a["box_xyxy"], b["box_xyxy"], atol=0.01, rtol=0)
                        and abs(a["score"] - b["score"]) <= 1e-4
                        for a, b in zip(original, raw))
                    write_json(case_out / "baseline_reproduction.json", {
                        "matched_original_with_tolerance": matched,
                        "box_atol_pixels": 0.01, "score_atol": 1e-4,
                        "original_count": len(original), "rerun_count": len(raw),
                        "note": "A mismatch must be investigated before claiming a controlled comparison."})
        for variant in manifest["variants"]:
            names = ([variant] if variant.endswith("joint") else
                     ["single_" + key for key in (full if variant.startswith("full") else task)])
            for threshold in manifest["text_thresholds"]:
                raw, boxes, categories, scores = [], [], [], []
                for name in names:
                    a, b, c, s = query_results[(name, threshold)]
                    raw.extend(a); boxes.extend(b); categories.extend(c); scores.extend(s)
                out = case_out / variant / f"text_{threshold:.2f}"
                out.mkdir(parents=True, exist_ok=True)
                masks = np.zeros((0, *rgb.shape[:2]), dtype=bool)
                if boxes:
                    sam_inputs = detector.sam2_processor(images=rgb, input_boxes=[boxes], return_tensors="pt").to(args.device)
                    with torch.no_grad():
                        sam_out = detector.sam2_model(**sam_inputs, multimask_output=False)
                    masks = np.asarray(detector.sam2_processor.post_process_masks(
                        sam_out.pred_masks.cpu(), sam_inputs["original_sizes"])[0])[:, 0].astype(bool)
                np.savez_compressed(out / "masks.npz", masks=masks)
                retained = [{"category": c, "score": float(s), "box_xyxy": b,
                             "mask_pixels": int(m.sum()),
                             "valid_depth_pixels": int((m & frame.depth_valid).sum())}
                            for c, s, b, m in zip(categories, scores, boxes, masks)]
                canvas = Image.fromarray(rgb).resize((768, 768))
                draw = ImageDraw.Draw(canvas)
                for item in raw:
                    color = "lime" if item["filter_reason"] == "kept" else "orange"
                    box = [max(0, min(767, v * 3)) for v in item["box_xyxy"]]
                    draw.rectangle(box, outline=color, width=2)
                    draw.text((box[0], max(0, box[1] - 12)),
                              f'{item["text_label"] or "EMPTY"} {item["score"]:.3f}', fill=color, stroke_width=1, stroke_fill="black")
                canvas.save(out / "raw_boxes.png")
                overlay = rgb.astype(float).copy()
                for i, mask in enumerate(masks):
                    color = np.asarray([(i * 73 + 40) % 256, (i * 131 + 160) % 256, (i * 47 + 90) % 256])
                    overlay[mask] = overlay[mask] * .5 + color * .5
                Image.fromarray(overlay.astype("uint8")).resize((768, 768)).save(out / "masks.png")
                row = {"case": case["case"], "variant": variant, "text_threshold": threshold,
                       "raw_count": len(raw), "retained": retained,
                       "missing_task_categories": [k for k in task if k not in categories],
                       "warning": "Class presence alone does not establish correct localization or identity."}
                write_json(out / "result.json", {**row, "raw_boxes": raw})
                summary.append(row)
                write_json(args.output / "summary.json", summary)
        print(json.dumps({"case_completed": case["case"], "comparisons_completed": len(summary)}), flush=True)
    write_json(args.output / "completed.json", {"case_count": len(manifest["cases"]), "comparisons": len(summary)})


if __name__ == "__main__":
    main()
