#!/usr/bin/env python3
"""Replay a frozen sequence and export non-actionable goal surface evidence."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def evaluate_goal_surfaces(
    root: Path, camera_id: str, detections_subdir: str, workspace,
    *, prompts_override: dict[str, str] | None = None,
    placement_diagnostics_dir: Path | None = None,
    heightfield_diagnostics_dir: Path | None = None,
) -> dict[str, object]:
    from scripts.recovery.skill_pipeline.evaluate_rgbd_sequence import evaluate_sequence
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_goal_surface import goal_surface_evidence
    from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff
    if placement_diagnostics_dir is not None:
        import numpy as np
        from experiments.robot.libero.skill_pipeline.visual_placement_region import visible_placement_diagnostic

        if placement_diagnostics_dir.exists():
            raise FileExistsError("placement diagnostic directory already exists")
    if heightfield_diagnostics_dir is not None:
        import numpy as np
        from experiments.robot.libero.skill_pipeline.visual_heightfield import visible_heightfield_diagnostic
        if heightfield_diagnostics_dir.exists():
            raise FileExistsError("heightfield diagnostic directory already exists")
        if (placement_diagnostics_dir is not None
                and heightfield_diagnostics_dir.resolve() == placement_diagnostics_dir.resolve()):
            raise ValueError("heightfield and plane artifacts need separate directories")

    # Reuse frozen configuration, frame offset and detector identity checks.
    sequence = evaluate_sequence(root, camera_id, detections_subdir, prompts_override=prompts_override)
    if placement_diagnostics_dir is not None:
        placement_diagnostics_dir.mkdir(parents=True)
    if heightfield_diagnostics_dir is not None:
        heightfield_diagnostics_dir.mkdir(parents=True)
    summary = json.loads((root / "summary.json").read_text(encoding="utf-8"))
    frames = []
    by_step = {}
    for step in range(sequence["frame_count"]):
        directory = root / f"step{step:03d}" / camera_id
        frame = load_observation(directory)
        _, detections = load_detections(frame, directory / detections_subdir)
        frames.append(frame)
        by_step[frame.env_step] = detections
    provider = RGBDSceneProvider(lambda frame: by_step[frame.env_step],
                                 detector_id=sequence["detector_id"], camera_id=camera_id)
    rows = []
    for frame in frames:
        handoff = build_visual_recovery_handoff(summary["language"], frame, provider.get_admission(frame))
        evidence = goal_surface_evidence(frame, handoff, by_step[frame.env_step], workspace)
        if heightfield_diagnostics_dir is not None:
            diagnostic = visible_heightfield_diagnostic(frame, handoff, by_step[frame.env_step], workspace)
            evidence["visible_heightfield"] = diagnostic.report
            if diagnostic.arrays:
                artifact = heightfield_diagnostics_dir / f"env_step{frame.env_step:06d}_{camera_id}.npz"
                np.savez_compressed(artifact, **diagnostic.arrays)
                evidence["visible_heightfield"]["grid_artifact"] = str(artifact.resolve())
        if placement_diagnostics_dir is not None:
            placement = visible_placement_diagnostic(frame, handoff, by_step[frame.env_step], workspace)
            evidence["visible_placement"] = placement.report
            if placement.arrays:
                artifact = placement_diagnostics_dir / f"env_step{frame.env_step:06d}_{camera_id}.npz"
                np.savez_compressed(artifact, **placement.arrays)
                evidence["visible_placement"]["grid_artifact"] = str(artifact.resolve())
        plane = evidence.get("plane")
        if plane is not None:
            x = sum(plane["visible_xy_bounds_m"][0]) / 2
            y = sum(plane["visible_xy_bounds_m"][1]) / 2
            evidence["plane_height_at_visible_bounds_center_m"] = (
                plane["z_at_world_origin_m"] + plane["slope_x"] * x + plane["slope_y"] * y)
        rows.append(evidence)
    return {
        "schema_version": 2 if placement_diagnostics_dir is not None or heightfield_diagnostics_dir is not None else 1,
        "scope": "offline_visible_goal_surface_only",
        "sequence_dir": str(root.resolve()), "language": summary["language"],
        "prompt_source": sequence["prompt_source"], "prompts": sequence["prompts"],
        "detector_id": sequence["detector_id"], "camera_id": camera_id,
        "workspace_m": dataclasses.asdict(workspace), "shared_tracker": True,
        "planning_allowed": False, "frames": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sequence_dir", type=Path)
    parser.add_argument("--camera", default="agentview")
    parser.add_argument("--detections-subdir", default="grounded_sam2_language_v1")
    parser.add_argument("--prompts-json", type=Path)
    parser.add_argument("--workspace-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--placement-diagnostics-dir", type=Path,
                        help="new directory for sampled containment grids; never authorizes planning")
    parser.add_argument("--heightfield-diagnostics-dir", type=Path,
                        help="new directory for observed curved surface height bins")
    args = parser.parse_args()
    if Path(args.detections_subdir).name != args.detections_subdir:
        parser.error("detections-subdir must be one directory name")
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds

    workspace = WorkspaceBounds(**json.loads(args.workspace_json.read_text(encoding="utf-8")))
    prompts = json.loads(args.prompts_json.read_text(encoding="utf-8")) if args.prompts_json else None
    report = evaluate_goal_surfaces(args.sequence_dir, args.camera, args.detections_subdir,
                                   workspace, prompts_override=prompts,
                                   placement_diagnostics_dir=args.placement_diagnostics_dir,
                                   heightfield_diagnostics_dir=args.heightfield_diagnostics_dir)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"output": str(args.out), "frames": len(report["frames"]),
                      "surface_candidates": sum(row["status"] == "visible_surface_candidate"
                                                for row in report["frames"]),
                      "planning_allowed": False}))


if __name__ == "__main__":
    main()
