#!/usr/bin/env python3
"""Replay a saved RGB-D sequence through one tracker and report ID continuity.

Frozen detection artifacts must already exist under each step/camera folder.
This evaluates visual ID admission only; it cannot certify task success.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def evaluate_sequence(
    root: Path, camera_id: str, detections_subdir: str,
    *, prompts_override: dict[str, str] | None = None,
) -> dict[str, object]:
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place

    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if summary.get("kind") != "rgbd_motion_probe" or not isinstance(summary.get("language"), str):
        raise ValueError("expected an RGB-D motion probe with task language")
    language = summary["language"]
    expected_prompts = prompts_from_task_language(language) if prompts_override is None else prompts_override
    if (not isinstance(expected_prompts, dict) or not expected_prompts
            or not all(isinstance(key, str) and key.strip() and isinstance(value, str) and value.strip()
                       for key, value in expected_prompts.items())):
        raise ValueError("expected prompts must map nonempty categories to nonempty text")
    steps = int(summary["probe_env_steps"])
    if not 1 <= steps <= 20:
        raise ValueError("invalid probe step count")
    first_env_step = int(summary.get("capture_start_env_step", 0))
    if first_env_step < 0:
        raise ValueError("invalid capture start environment step")

    frames = []
    detections_by_step = {}
    detector_id = None
    for step in range(steps + 1):
        frame_dir = root / f"step{step:03d}" / camera_id
        run_dir = frame_dir / detections_subdir
        frame = load_observation(frame_dir)
        if frame.env_step != first_env_step + step or frame.camera_id != camera_id:
            raise ValueError("saved RGB-D frame does not match its step/camera path")
        config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        expected_source = "task_language" if prompts_override is None else "prompts_json"
        expected_language = language if prompts_override is None else None
        if (config.get("prompt_source") != expected_source
                or config.get("task_language") != expected_language
                or config.get("prompts") != expected_prompts):
            raise ValueError("sequence detection prompts do not match the frozen prompt policy")
        current_id, detections = load_detections(frame, run_dir)
        if detector_id is not None and current_id != detector_id:
            raise ValueError("sequence frames use different detector configurations")
        detector_id = current_id
        frames.append(frame)
        detections_by_step[frame.env_step] = detections

    provider = RGBDSceneProvider(
        lambda frame: detections_by_step[frame.env_step],
        detector_id=detector_id,
        camera_id=camera_id,
    )
    rows = []
    for frame in frames:
        admission = provider.get_admission(frame)
        row: dict[str, object] = {
            "env_step": frame.env_step,
            "timestamp_s": frame.timestamp_s,
            "detection_count": len(detections_by_step[frame.env_step]),
            "scene_status": admission.status,
            "scene_reason": admission.reason,
            "mask_conflicts": admission.mask_conflicts,
        }
        if admission.scene is not None:
            binding = bind_visual_pick_place(language, admission.scene)
            row["binding"] = dataclasses.asdict(binding)
        rows.append(row)

    candidate_ids = [
        row["binding"]["target_id"] for row in rows
        if "binding" in row and row["binding"]["target_id"] is not None
    ]
    return {
        "schema_version": 1,
        "scope": "offline_visual_id_continuity_only",
        "sequence_dir": str(root.resolve()),
        "camera_id": camera_id,
        "detector_id": detector_id,
        "prompt_source": expected_source,
        "prompts": expected_prompts,
        "frame_count": len(rows),
        "capture_start_env_step": first_env_step,
        "scene_refusal_count": sum(row["scene_status"] == "refused" for row in rows),
        "target_candidate_frame_count": len(candidate_ids),
        "same_target_id_across_candidate_frames": (
            len(set(candidate_ids)) == 1 if len(candidate_ids) >= 2 else None
        ),
        "frames": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sequence_dir", type=Path)
    parser.add_argument("--camera", default="agentview")
    parser.add_argument("--detections-subdir", default="grounded_sam2_language_v1")
    parser.add_argument("--prompts-json", type=Path,
                        help="evaluate a frozen prompt variant instead of task-language prompts")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if Path(args.detections_subdir).name != args.detections_subdir:
        parser.error("detections-subdir must be one directory name")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    prompts_override = (
        json.loads(args.prompts_json.read_text(encoding="utf-8"))
        if args.prompts_json is not None else None
    )
    report = evaluate_sequence(
        args.sequence_dir, args.camera, args.detections_subdir,
        prompts_override=prompts_override,
    )
    output = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
