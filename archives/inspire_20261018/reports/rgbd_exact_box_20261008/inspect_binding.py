import json
from pathlib import Path
import sys
code = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/code")
sys.path.insert(0, str(code))
from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter

root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/snapshot_t6")
summary = json.loads((root / "summary.json").read_text())
frame = load_observation(root / "agentview")
detector_id, detections = load_detections(frame, root / "detector")
provider = RGBDSceneProvider(lambda _frame: detections, detector_id=detector_id, camera_id=frame.camera_id)
handoff = VisualDryRunAdapter(provider).query_state(frame, summary["language"])
binding = handoff.binding
print("status", handoff.status)
print("reason", handoff.reason)
print("checks", handoff.unresolved_checks)
print("objects", [(obj.id, obj.category, obj.identity_status, obj.validity) for obj in handoff.visible_objects])
if binding is not None:
    print("binding_status", binding.status)
    print("binding_reason", binding.reason)
    print("target", binding.target_id, "goal", binding.goal_id, "relation", binding.goal_relation)
