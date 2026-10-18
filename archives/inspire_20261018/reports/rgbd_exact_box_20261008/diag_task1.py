"""Print why the visual path refused the task-1 goal."""
import json
from pathlib import Path

from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/task1")
summary = json.loads((root / "snapshot/summary.json").read_text(encoding="utf-8"))
frame = load_observation(root / "snapshot/agentview")
detector_id, detections = load_detections(frame, root / "snapshot/detector")
print("detections", len(detections))
for item in detections:
    print(json.dumps({
        "category": getattr(item, "category", None),
        "label": getattr(item, "label", None),
        "score": getattr(item, "score", None),
        "prompt": getattr(item, "prompt", None),
    }, ensure_ascii=False))
provider = RGBDSceneProvider(lambda _frame: detections, detector_id=detector_id, camera_id=frame.camera_id)
handoff = VisualDryRunAdapter(provider).query_state(frame, summary["language"])
binding = handoff.binding
print("handoff", handoff.status, getattr(binding, "reason", None), getattr(binding, "status", None))
print("evidence", json.dumps(getattr(binding, "evidence", {}), ensure_ascii=False, default=str)[:3000])
scene = provider.get_admission(frame).scene
if scene is not None:
    for obj in scene.objects:
        print(obj.id, obj.category, obj.validity, obj.identity_status, obj.visible_centroid_world_m)
