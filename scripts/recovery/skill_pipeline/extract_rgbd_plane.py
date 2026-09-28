#!/usr/bin/env python3
"""Extract an unnamed visible horizontal plane candidate from one RGB-D frame."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--workspace-x", type=float, nargs=2, required=True)
    parser.add_argument("--workspace-y", type=float, nargs=2, required=True)
    parser.add_argument("--workspace-z", type=float, nargs=2, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.visual_geometry import WorkspaceBounds, dominant_horizontal_plane

    frame = load_observation(args.snapshot)
    workspace = WorkspaceBounds(tuple(args.workspace_x), tuple(args.workspace_y), tuple(args.workspace_z))
    plane = dominant_horizontal_plane(frame, workspace)
    payload = {
        "snapshot_id": f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}",
        "episode_id": frame.episode_id,
        "env_step": frame.env_step,
        "camera_id": frame.camera_id,
        "source": "rgbd_visible_points",
        "workspace_bounds_m": dataclasses.asdict(workspace),
        "horizontal_plane_candidate": dataclasses.asdict(plane) if plane else None,
        "status": "candidate_found" if plane else "no_reliable_candidate",
        "semantic_label": None,
        "placement_region": None,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
