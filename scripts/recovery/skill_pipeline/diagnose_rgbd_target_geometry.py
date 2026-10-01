#!/usr/bin/env python3
"""Export visible target boundary/lower-band evidence without authorizing actions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def diagnose_target(snapshot, detections_dir, language_summary, *, prompts_override=None, other_camera=None):
    from scripts.recovery.skill_pipeline.export_visual_handoff import export_handoff
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_recovery_handoff import build_visual_recovery_handoff
    from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import (
        mask_depth_diagnostic, cross_view_depth_diagnostic,
    )

    # Keep frozen prompt configuration validation identical to handoff export.
    export_handoff(snapshot, detections_dir, language_summary, prompts_override=prompts_override)
    frame = load_observation(snapshot)
    detector_id, detections = load_detections(frame, detections_dir)
    language = json.loads(language_summary.read_text(encoding="utf-8"))["language"]
    provider = RGBDSceneProvider(lambda _: detections, detector_id=detector_id, camera_id=frame.camera_id)
    handoff = build_visual_recovery_handoff(language, frame, provider.get_admission(frame))
    report = dict(schema_version=1, scope="offline_target_boundary_and_cross_view_only",
                  detector_id=detector_id, snapshot_id=handoff.snapshot_id,
                  planning_allowed=False, status="refused", reason=handoff.reason)
    if handoff.status != "visual_id_candidate":
        report["reason"] = handoff.reason or "visual_binding_unavailable"
        return report
    target = next(o for o in handoff.visible_objects if o.id == handoff.binding.target_id)
    mask = detections[target.detection_index].mask
    report.update(status="visible_target_geometry_diagnostic", reason=None,
                  target_id=target.id, target_mask_sha256=target.detection_mask_sha256,
                  boundary=mask_depth_diagnostic(frame, mask))
    if other_camera is not None:
        other = load_observation(other_camera)
        report["cross_view"] = cross_view_depth_diagnostic(frame, mask, other)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("detections_dir", type=Path)
    parser.add_argument("language_summary", type=Path)
    parser.add_argument("--prompts-json", type=Path)
    parser.add_argument("--other-camera", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    prompts = json.loads(args.prompts_json.read_text(encoding="utf-8")) if args.prompts_json else None
    report = diagnose_target(args.snapshot, args.detections_dir, args.language_summary,
                             prompts_override=prompts, other_camera=args.other_camera)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2) + "\n",
                        encoding="utf-8")
    print(json.dumps({"status": report["status"], "output": str(args.out), "planning_allowed": False}))


if __name__ == "__main__":
    main()
