#!/usr/bin/env python3
"""Replay saved RGB-D detections and summarize visual task admission.

This is an offline diagnostic. A bound ID is not permission to execute: grasp,
placement and outcome checks are outside the current visual scene contract.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def evaluate_run(run_dir: Path) -> dict[str, object]:
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place

    snapshot = run_dir.parent.parent
    summary = json.loads((snapshot / "summary.json").read_text(encoding="utf-8"))
    config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
    language = summary.get("language")
    if not isinstance(language, str) or config.get("prompt_source") != "task_language":
        raise ValueError("admission replay requires task language and task-language prompts")
    if config.get("task_language") != language or config.get("prompts") != prompts_from_task_language(language):
        raise ValueError("saved prompts do not match the snapshot task language")

    frame = load_observation(run_dir.parent)
    detector_id, detections = load_detections(frame, run_dir)
    row: dict[str, object] = {
        "snapshot_id": f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}",
        "run_dir": str(run_dir.resolve()),
        "detector_id": detector_id,
        "task_language": language,
        "detection_count": len(detections),
        "detections_by_category": {
            category: sum(item.category == category for item in detections)
            for category in sorted({item.category for item in detections if item.category is not None})
        },
    }
    provider = RGBDSceneProvider(lambda _: detections, detector_id=detector_id, camera_id=frame.camera_id)
    scene_admission = provider.get_admission(frame)
    row["mask_conflicts"] = scene_admission.mask_conflicts
    if scene_admission.scene is None:
        row.update(admission="refused", reason=scene_admission.reason)
        return row

    binding = bind_visual_pick_place(language, scene_admission.scene)
    row["binding"] = dataclasses.asdict(binding)
    row["admission"] = "refused" if binding.status == "refused" else "id_candidate_only"
    row["reason"] = binding.reason if binding.reason else binding.status
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", nargs="+", type=Path, help="directories containing frozen detection artifacts")
    parser.add_argument("--out", type=Path, help="optional JSON report path")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    rows = [evaluate_run(run_dir) for run_dir in args.run_dirs]
    report = {
        "schema_version": 1,
        "scope": "offline_reset_frame_id_admission_only",
        "run_count": len(rows),
        "refused_count": sum(row["admission"] == "refused" for row in rows),
        "runs": rows,
    }
    output = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
