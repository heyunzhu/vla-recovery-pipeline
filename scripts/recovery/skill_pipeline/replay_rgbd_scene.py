#!/usr/bin/env python3
"""Build a visual scene from a saved RGB-D frame and frozen detector masks."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("detections_dir", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider

    frame = load_observation(args.snapshot)
    detector_id, detections = load_detections(frame, args.detections_dir)
    provider = RGBDSceneProvider(lambda _: detections, detector_id=detector_id, camera_id=frame.camera_id)
    scene = provider.get_scene(frame)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dataclasses.asdict(scene), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"snapshot_id": scene.snapshot_id, "object_count": len(scene.objects)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
