import json
from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/snapshot/detector_per_category")
print("FILES", sorted(p.name for p in root.iterdir()))
refusal = json.loads((root / "scene_refusal.json").read_text())
print("REFUSAL", json.dumps(refusal, ensure_ascii=False)[:4000])
boxes = json.loads((root / "grounding_boxes.json").read_text())
print("NBOX", len(boxes))
for row in boxes:
    print(json.dumps({k: row[k] for k in row if k != "mask"}, ensure_ascii=False))
dets = json.loads((root / "detections.json").read_text())["detections"]
print("NDET", len(dets))
for item in dets:
    print({k: item[k] for k in item if k != "mask"})
