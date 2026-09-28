#!/usr/bin/env python3
"""Bind task-language object IDs against one saved visual scene, offline."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("summary", type=Path, help="snapshot summary containing the task language")
    parser.add_argument("visual_scene", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualObject, VisualSceneSnapshot
    from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place

    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    if not isinstance(summary, dict) or not isinstance(summary.get("language"), str):
        raise ValueError("snapshot summary must contain a task language string")
    values = json.loads(args.visual_scene.read_text(encoding="utf-8"))
    if not isinstance(values, dict) or not isinstance(values.get("objects"), list):
        raise ValueError("visual scene must contain an object list")
    scene = VisualSceneSnapshot(**{**values, "objects": tuple(VisualObject(**item) for item in values["objects"])})
    result = bind_visual_pick_place(summary["language"], scene)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result.status, "reason": result.reason,
                      "target_id": result.target_id, "goal_id": result.goal_id}, ensure_ascii=False))


if __name__ == "__main__":
    main()
