#!/usr/bin/env python3
"""Run pinned Grounding DINO and SAM 2 on one saved RGB-D observation."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import sys
from pathlib import Path


GROUNDING_MODEL = "IDEA-Research/grounding-dino-tiny"
GROUNDING_REVISION = "a2bb814dd30d776dcf7e30523b00659f4f141c71"
SAM2_MODEL = "facebook/sam2.1-hiera-tiny"
SAM2_REVISION = "de431c4043854a71d8101e17995dfe596bf101a5"
GROUNDING_SHA256 = "1a2412ef99bd74bcd3c2a246fa1e48581f8889a1300c9051974741314fc042f3"
SAM2_SHA256 = "48c14467e5cf9e51870511feb72c89688e82dd74523142c0538b663e193ac2a7"


def _verify_model_weights(directory: Path, expected_sha256: str) -> Path:
    resolved = directory.expanduser().resolve()
    weights = resolved / "model.safetensors"
    if not (resolved / "config.json").is_file() or not weights.is_file():
        raise ValueError(f"model directory is incomplete: {resolved}")
    digest = hashlib.sha256()
    with weights.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    if digest.hexdigest() != expected_sha256:
        raise ValueError(f"model weight SHA256 mismatch: {resolved}")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--prompts-json", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--grounding-model-dir", type=Path, required=True)
    parser.add_argument("--sam2-model-dir", type=Path, required=True)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--box-threshold", type=float, default=0.25)
    parser.add_argument("--text-threshold", type=float, default=0.25)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    import torch
    import transformers

    from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
    from experiments.robot.libero.skill_pipeline.perception_artifact import save_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_perception_eval import (
        evaluate_reference_points,
        load_visual_reference,
    )

    frame = load_observation(args.snapshot)
    grounding_dir = _verify_model_weights(args.grounding_model_dir, GROUNDING_SHA256)
    sam2_dir = _verify_model_weights(args.sam2_model_dir, SAM2_SHA256)
    prompts = json.loads(args.prompts_json.read_text(encoding="utf-8"))
    if not isinstance(prompts, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in prompts.items()):
        raise ValueError("prompts JSON must map category strings to visual prompt strings")
    config = {
        "grounding_model": GROUNDING_MODEL,
        "grounding_revision": GROUNDING_REVISION,
        "sam2_model": SAM2_MODEL,
        "sam2_revision": SAM2_REVISION,
        "grounding_sha256": GROUNDING_SHA256,
        "sam2_sha256": SAM2_SHA256,
        "prompts": prompts,
        "image_shape_hw": list(frame.rgb.shape[:2]),
        "box_threshold": args.box_threshold,
        "text_threshold": args.text_threshold,
        "device": args.device,
        "torch_version": torch.__version__,
        "transformers_version": transformers.__version__,
    }
    detector_id = "grounded-sam2-" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
    output = args.out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    (output / "run_config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")

    detector = GroundedSam2Detector(
        grounding_model=str(grounding_dir),
        grounding_revision=GROUNDING_REVISION,
        sam2_model=str(sam2_dir),
        sam2_revision=SAM2_REVISION,
        prompts=prompts,
        box_threshold=args.box_threshold,
        text_threshold=args.text_threshold,
        device=args.device,
        cache_dir=None,
    )
    detections = detector(frame)
    (output / "grounding_boxes.json").write_text(
        json.dumps(detector.last_grounding_boxes, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    save_detections(frame, detections, output, detector_id=detector_id)
    evaluation = None
    if args.reference is not None:
        reference = load_visual_reference(frame, args.reference)
        evaluation = evaluate_reference_points(frame, detections, reference)
        evaluation["detector_id"] = detector_id
        (output / "perception_eval.json").write_text(
            json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    provider = RGBDSceneProvider(lambda _: detections, detector_id=detector_id, camera_id=frame.camera_id)
    scene = provider.get_scene(frame)
    (output / "visual_scene.json").write_text(
        json.dumps(dataclasses.asdict(scene), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"detector_id": detector_id, "detection_count": len(detections)}, ensure_ascii=False))
    if evaluation is not None and not evaluation["passed"]:
        raise SystemExit("visual reference failed; inspect perception_eval.json")


if __name__ == "__main__":
    main()
