import json
from pathlib import Path
data = json.loads(Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/truth_t6/plan_summary.json").read_text(encoding="utf-8"))
keep = {k: data.get(k) for k in (
    "target", "goal", "feasible", "failure_reason", "num_satisfying", "elapsed_sec",
    "movable_count", "surface_count", "static_count", "executable_plan_present", "constraint_stats",
)}
print(json.dumps(keep, indent=2))
print("OBJECTS")
for item in data.get("objects", []):
    print(item["role"], item["name"], item["half_extents_m"], item["pos"])
