import json
from collections import Counter
from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/snapshot_t6")
summary = json.loads((root / "summary.json").read_text())
print("LANG", summary["language"])
print("SUITE", summary["task_suite_name"], "TASK", summary["task_id_zero_based"], "SEED", summary["seed"], "INIT", summary["init_index"])
dets = json.loads((root / "detector/detections.json").read_text())["detections"]
print("NDET", len(dets), Counter(d["category"] for d in dets))
boxes = json.loads((root / "detector/grounding_boxes.json").read_text())
print("NBOX", len(boxes))
for row in boxes:
    print(f"{row.get('query_category')} {row['score']:.3f} {row['text_label']}")
refusal = json.loads((root / "detector/scene_refusal.json").read_text())
print("NCONF", len(refusal["mask_conflicts"]))
pairs = Counter((c["first_category"], c["second_category"], round(c["overlap_fraction_of_smaller_mask"], 3)) for c in refusal["mask_conflicts"])
for key, n in pairs.most_common():
    print(n, key)
