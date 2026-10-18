import json
from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008")
summary = json.loads((root / "snapshot/summary.json").read_text())
print("SUMMARY_KEYS", sorted(summary))
for key in ("language", "task_language", "suite", "task_id", "task_suite_name"):
    if key in summary:
        print(key, summary[key])
cfg = json.loads((root / "snapshot/detector/run_config.json").read_text())
print("CFG", json.dumps(cfg, ensure_ascii=False)[:2000])
boxes = json.loads((root / "snapshot/detector/grounding_boxes.json").read_text())
print("BOXES_TYPE", type(boxes).__name__)
if isinstance(boxes, dict):
    print("BOX_KEYS", list(boxes)[:20])
    text = json.dumps(boxes, ensure_ascii=False)
    print(text[:4000])
else:
    print("NBOX", len(boxes))
    print(json.dumps(boxes[:12], ensure_ascii=False)[:4000])
dets = json.loads((root / "snapshot/detector/detections.json").read_text())
print("DET_TYPE", type(dets).__name__)
if isinstance(dets, dict):
    print("DET_KEYS", list(dets)[:30])
    print(json.dumps({k: dets[k] for k in list(dets)[:8]}, ensure_ascii=False)[:3000])
else:
    print("NDET", len(dets))
    slim = []
    for item in dets[:8]:
        if isinstance(item, dict):
            slim.append({k: item[k] for k in item if k not in ("mask", "segmentation")})
        else:
            slim.append(item)
    print(json.dumps(slim, ensure_ascii=False)[:3000])
