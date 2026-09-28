#!/usr/bin/env python3
"""Score cached visual masks against visually inspected image points."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("detections_dir", type=Path)
    parser.add_argument("reference", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.visual_perception_eval import (
        evaluate_reference_points,
        load_visual_reference,
    )

    frame = load_observation(args.snapshot)
    detector_id, detections = load_detections(frame, args.detections_dir)
    reference = load_visual_reference(frame, args.reference)
    result = evaluate_reference_points(frame, detections, reference)
    result["detector_id"] = detector_id
    output = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")
    if not result["passed"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
