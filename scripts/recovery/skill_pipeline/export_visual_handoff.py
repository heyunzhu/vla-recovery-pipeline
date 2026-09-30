#!/usr/bin/env python3
"""Export a non-actionable RGB-D recovery handoff from a frozen frame."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def export_handoff(
    snapshot: Path, detections_dir: Path, language_summary: Path,
    *, prompts_override: dict[str, str] | None = None,
    goal_surface_workspace: dict[str, list[float]] | None = None,
) -> dict[str, object]:
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
    expected_source = "task_language" if prompts_override is None else "prompts_json"
    expected_prompts = prompts_from_task_language(language) if prompts_override is None else prompts_override
    if (config.get("prompt_source") != expected_source
            or (prompts_override is None and config.get("task_language") != language)
            or config.get("prompts") != expected_prompts):
        raise ValueError("frozen detections must match the declared prompt configuration")
    frame = load_observation(snapshot)
    detector_id, detections = load_detections(frame, detections_dir)
    provider = RGBDSceneProvider(lambda _: detections, detector_id=detector_id, camera_id=frame.camera_id)
    handoff = build_visual_recovery_handoff(language, frame, provider.get_admission(frame))
    result = {"schema_version": 1, "kind": "visual_recovery_handoff_diagnostic",
              "prompt_source": expected_source, "prompts": expected_prompts,
              "handoff": dataclasses.asdict(handoff)}
    if goal_surface_workspace is not None:
        from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds
        from experiments.robot.libero.skill_pipeline.visual_goal_surface import goal_surface_evidence

        workspace = WorkspaceBounds(**goal_surface_workspace)
        result["schema_version"] = 2
        result["goal_surface_evidence"] = goal_surface_evidence(frame, handoff, detections, workspace)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("detections_dir", type=Path)
    parser.add_argument("language_summary", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--prompts-json", type=Path, help="explicit frozen diagnostic prompt variant")
    parser.add_argument("--goal-surface-workspace-json", type=Path,
                        help="explicit x/y/z bounds in metres for visible goal surface fitting")
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    output = json.dumps(
        export_handoff(
            args.snapshot, args.detections_dir, args.language_summary,
            prompts_override=(json.loads(args.prompts_json.read_text(encoding="utf-8"))
                              if args.prompts_json is not None else None),
            goal_surface_workspace=(json.loads(args.goal_surface_workspace_json.read_text(encoding="utf-8"))
                                    if args.goal_surface_workspace_json is not None else None),
        ),
        ensure_ascii=False, allow_nan=False, indent=2,
    ) + "\n"
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(output, encoding="utf-8")
    print(output, end="")


if __name__ == "__main__":
    main()
