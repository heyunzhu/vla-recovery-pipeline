#!/usr/bin/env python3
"""Export a non-actionable RGB-D recovery handoff from a frozen frame."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def export_handoff(snapshot: Path, detections_dir: Path, language_summary: Path) -> dict[str, object]:
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff

    summary = json.loads(language_summary.read_text(encoding="utf-8"))
    language = summary.get("language")
    if not isinstance(language, str) or not language.strip():
        raise ValueError("language summary must provide task language")
    config = json.loads((detections_dir / "run_config.json").read_text(encoding="utf-8"))
    if (config.get("prompt_source") != "task_language"
            or config.get("task_language") != language
            or config.get("prompts") != prompts_from_task_language(language)):
        raise ValueError("frozen detections must use prompts from the same task language")
    frame = load_observation(snapshot)
    detector_id, detections = load_detections(frame, detections_dir)
    provider = RGBDSceneProvider(lambda _: detections, detector_id=detector_id, camera_id=frame.camera_id)
    handoff = build_visual_recovery_handoff(language, frame, provider.get_admission(frame))
    return {"schema_version": 1, "kind": "visual_recovery_handoff_diagnostic",
            "handoff": dataclasses.asdict(handoff)}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("detections_dir", type=Path)
    parser.add_argument("language_summary", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    output = json.dumps(
        export_handoff(args.snapshot, args.detections_dir, args.language_summary),
        ensure_ascii=False, allow_nan=False, indent=2,
    ) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
