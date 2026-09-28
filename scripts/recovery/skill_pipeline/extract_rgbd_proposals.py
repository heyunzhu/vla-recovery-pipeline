#!/usr/bin/env python3
"""Cache unnamed height-based RGB-D object proposals and an RGB overlay."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path

import numpy as np


PALETTE = np.asarray(
    [
        [230, 25, 75],
        [60, 180, 75],
        [255, 225, 25],
        [0, 130, 200],
        [245, 130, 48],
        [145, 30, 180],
        [70, 240, 240],
        [240, 50, 230],
    ],
    dtype=np.uint8,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--workspace-x", type=float, nargs=2, required=True)
    parser.add_argument("--workspace-y", type=float, nargs=2, required=True)
    parser.add_argument("--workspace-z", type=float, nargs=2, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.perception_artifact import save_detections
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
    from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
    from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds, dominant_horizontal_plane
    from experiments.robot.libero.skill_pipeline.visual_object_proposals import foreground_proposals
    from scripts.recovery.skill_pipeline.render_rgbd_diagnostic import _write_rgb_png

    frame = load_observation(args.snapshot)
    workspace = WorkspaceBounds(tuple(args.workspace_x), tuple(args.workspace_y), tuple(args.workspace_z))
    plane = dominant_horizontal_plane(frame, workspace, min_inliers=500)
    if plane is None:
        raise ValueError("no reliable horizontal plane candidate; cannot extract foreground")
    proposals = foreground_proposals(frame, plane, workspace, min_pixels=30)
    output = args.out_dir.expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)
    masks = (
        np.stack([proposal.mask for proposal in proposals])
        if proposals
        else np.empty((0, *frame.depth_m.shape), bool)
    )
    np.savez_compressed(output / "proposal_masks.npz", masks=masks)
    overlay = frame.rgb.copy()
    rows = []
    for index, proposal in enumerate(proposals):
        color = PALETTE[index % len(PALETTE)].astype(np.float32)
        overlay[proposal.mask] = (0.45 * overlay[proposal.mask] + 0.55 * color).astype(np.uint8)
        rows.append(
            {
                "proposal_id": proposal.proposal_id,
                "mask_index": index,
                "pixel_bbox_xyxy": proposal.pixel_bbox_xyxy,
                "pixel_count": proposal.pixel_count,
                "visible_centroid_world_m": proposal.visible_centroid_world_m,
                "visible_bounds_world_m": proposal.visible_bounds_world_m,
                "height_above_plane_m": proposal.height_above_plane_m,
                "touches_image_boundary": proposal.touches_image_boundary,
                "source": proposal.source,
                "semantic_label": None,
                "stable_track_id": None,
            }
        )
    _write_rgb_png(output / "proposal_overlay.png", overlay)
    payload = {
        "snapshot_id": f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}",
        "camera_id": frame.camera_id,
        "workspace_bounds_m": {"x": workspace.x, "y": workspace.y, "z": workspace.z},
        "source": "rgbd_height_components",
        "proposals": rows,
    }
    (output / "proposals.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    detections = [
        VisualDetection(mask=proposal.mask, category=None, raw_score=None, source="rgbd_height_component")
        for proposal in proposals
    ]
    save_detections(frame, detections, output, detector_id="rgbd-height-components-v1")
    provider = RGBDSceneProvider(
        lambda _: detections,
        detector_id="rgbd-height-components-v1",
        camera_id=frame.camera_id,
    )
    scene = provider.get_scene(frame)
    (output / "visual_scene.json").write_text(
        json.dumps(dataclasses.asdict(scene), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"snapshot_id": payload["snapshot_id"], "proposal_count": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
