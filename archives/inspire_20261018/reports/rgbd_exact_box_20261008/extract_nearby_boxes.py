"""Keep the bowl box and the static boxes that touch it."""
import json
from pathlib import Path

import numpy as np

src = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/result_t6_manual/problem.json")
payload = json.loads(src.read_text(encoding="utf-8"))
problem = payload["problem"]
objects = problem["movables"] + problem["surfaces"] + problem["statics"]
bowl = next(item for item in objects if item["name"] == "obj_001")
bowl_pos = np.asarray(bowl["pos"], dtype=np.float64)
bowl_half = np.asarray(bowl["half_extents"], dtype=np.float64)

def gap(item):
    return bowl_half + np.asarray(item["half_extents"], dtype=np.float64) - np.abs(np.asarray(item["pos"], dtype=np.float64) - bowl_pos)

nearby = []
strict = 0
for item in objects:
    if item["name"] == "obj_001":
        continue
    separation = gap(item)
    if np.any(separation < -0.02):
        continue
    record = {
        "name": item["name"],
        "role": item["role"],
        "category": (item.get("geometry") or {}).get("category"),
        "source": (item.get("geometry") or {}).get("source"),
        "pos": [round(float(v), 5) for v in item["pos"]],
        "half_extents": [round(float(v), 5) for v in item["half_extents"]],
        "overlap_m": [round(float(v), 5) for v in separation],
        "intersects": bool(np.all(separation > 0)),
    }
    nearby.append(record)
    strict += int(record["intersects"])

out = {
    "coordinate_frame": "robot_base",
    "bowl": {
        "name": bowl["name"],
        "pos": [round(float(v), 5) for v in bowl["pos"]],
        "half_extents": [round(float(v), 5) for v in bowl["half_extents"]],
    },
    "world_from_base": problem.get("q_init_debug", {}).get("world_from_base_candidate"),
    "static_count": len(problem["statics"]),
    "nearby_count": len(nearby),
    "strict_aabb_overlap_count": strict,
    "nearby": nearby,
}
dest = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/result_t6_manual/nearby_boxes.json")
dest.write_text(json.dumps(out), encoding="utf-8")
print("nearby", len(nearby), "strict", strict, "bytes", dest.stat().st_size)
