#!/usr/bin/env python3
"""Offline diagnosis of one overlapping mask pair per RGB-D sequence frame.

This never changes scene admission or supplies a scene to an executor. Task
language may favor one hypothesis, but cannot verify the detector's category.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def _binding_row(frame, detections, language):
    from experiments.robot.libero.skill_pipeline.rgbd_scene import RGBDSceneTracker
    from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place

    scene = RGBDSceneTracker().update(frame, detections)
    binding = bind_visual_pick_place(language, scene)
    return {"binding_status": binding.status, "binding_reason": binding.reason,
            "target_id": binding.target_id, "goal_id": binding.goal_id,
            "reference_ids": binding.reference_ids}


def evaluate_sequence(root: Path, camera_id: str, detections_subdir: str) -> dict[str, object]:
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene import RGBDSceneTracker, mask_conflicts
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
    from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place

    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    if summary.get("kind") != "rgbd_motion_probe" or not isinstance(summary.get("language"), str):
        raise ValueError("expected RGB-D motion probe with task language")
    language = summary["language"]
    expected_prompts = prompts_from_task_language(language)
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
        frame = load_observation(frame_dir)
        if frame.env_step != first_env_step + step or frame.camera_id != camera_id:
            raise ValueError("saved frame does not match step/camera path")
        run_dir = frame_dir / detections_subdir
        config = json.loads((run_dir / "run_config.json").read_text(encoding="utf-8"))
        if (config.get("prompt_source") != "task_language"
                or config.get("task_language") != language
                or config.get("prompts") != expected_prompts):
            raise ValueError("sequence detection prompts do not match task language")
        current_id, detections = load_detections(frame, run_dir)
        if detector_id is not None and current_id != detector_id:
            raise ValueError("sequence frames use different detector configurations")
        detector_id = current_id
        frames.append(frame)
        detections_by_step[frame.env_step] = detections

    # The ordinary provider is still the authority on whether the unmodified
    # detections may enter the online scene. The tracker below is diagnostic.
    provider = RGBDSceneProvider(lambda frame: detections_by_step[frame.env_step],
                                 detector_id=detector_id, camera_id=camera_id)
    diagnostic_tracker = RGBDSceneTracker()
    rows = []
    for frame in frames:
        detections = detections_by_step[frame.env_step]
        admission = provider.get_admission(frame)
        conflicts = mask_conflicts(detections)
        row = {"env_step": frame.env_step, "online_admission": admission.status,
               "online_reason": admission.reason, "mask_conflicts": conflicts,
               "hypotheses": []}
        selected = None
        if not conflicts:
            row["diagnostic_status"] = "no_conflict"
            selected = detections
        elif len(conflicts) == 1:
            conflict = conflicts[0]
            for dropped in (conflict["first_index"], conflict["second_index"]):
                subset = [item for index, item in enumerate(detections) if index != dropped]
                candidate = {"dropped_index": dropped,
                             "dropped_category": detections[dropped].category}
                if mask_conflicts(subset):
                    candidate["binding_status"] = "refused"
                    candidate["binding_reason"] = "remaining_mask_conflict"
                else:
                    candidate.update(_binding_row(frame, subset, language))
                row["hypotheses"].append(candidate)
            viable = [item for item in row["hypotheses"]
                      if item["binding_status"] in ("bound_ids", "candidate_requires_attribute_check")]
            if len(viable) == 1:
                dropped = viable[0]["dropped_index"]
                selected = [item for index, item in enumerate(detections) if index != dropped]
                row["diagnostic_status"] = "unique_task_consistent_hypothesis_unverified"
                row["selected_dropped_index"] = dropped
            else:
                row["diagnostic_status"] = "no_unique_task_consistent_hypothesis"
        else:
            row["diagnostic_status"] = "multiple_conflicts_not_enumerated"

        if selected is not None:
            scene = diagnostic_tracker.update(frame, selected)
            binding = bind_visual_pick_place(language, scene)
            row["diagnostic_binding"] = dataclasses.asdict(binding)
        rows.append(row)

    candidate_ids = [row["diagnostic_binding"]["target_id"] for row in rows
                     if row.get("diagnostic_binding", {}).get("target_id") is not None]
    return {"schema_version": 1,
            "scope": "offline_task_conditioned_conflict_hypotheses_not_actionable",
            "sequence_dir": str(root.resolve()), "camera_id": camera_id,
            "detector_id": detector_id, "frame_count": len(rows),
            "online_refusal_count": sum(row["online_admission"] == "refused" for row in rows),
            "diagnostic_target_candidate_frame_count": len(candidate_ids),
            "same_diagnostic_target_id_across_candidate_frames": (
                len(set(candidate_ids)) == 1 if len(candidate_ids) >= 2 else None),
            "frames": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sequence_dir", type=Path)
    parser.add_argument("--camera", default="agentview")
    parser.add_argument("--detections-subdir", default="grounded_sam2_language_v1")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if Path(args.detections_subdir).name != args.detections_subdir:
        parser.error("detections-subdir must be one directory name")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    report = evaluate_sequence(args.sequence_dir, args.camera, args.detections_subdir)
    output = json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
