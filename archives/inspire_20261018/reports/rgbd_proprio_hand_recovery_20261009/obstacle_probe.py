from pathlib import Path
import json,numpy as np
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
from experiments.robot.libero.skill_pipeline.visual_anchor_obstacles import observed_anchor_obstacles
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
a=root/'logs/rgbd_bottle_plate_geometry_recovery_20261009'
r=root/'logs/rgbd_proprio_hand_recovery_20261009'
f=load_observation(a/'snapshots/recovery01/pre_solver_attempt01/agentview')
d=a/'visual_nomination_step41/recovery01/pre_solver_attempt01/agentview'
v=json.loads((d/'visual_scene.json').read_text());b=json.loads((d/'binding.json').read_text());print(np.load(d/'detections.npz').files,flush=True)
m=np.load(d/'detections.npz')['masks'];selected=[o['detection_index'] for o in v['objects'] if o['id'] in (b['target_id'],b['goal_id'])]
robot=project_static_arm_gripper(f,root/'logs/rgbd_bottle_geometry_recovery_20261009/static_panda_model',depth_tolerance_m=.005)
obs=observed_anchor_obstacles(f,np.logical_or.reduce(m[selected]),robot)
(r/'obstacles_offline.json').write_text(json.dumps(obs,indent=2));print({k:obs[k] for k in ('table_z','residual_point_count','robot_pixel_count')},'boxes',len(obs['centres']),flush=True)
