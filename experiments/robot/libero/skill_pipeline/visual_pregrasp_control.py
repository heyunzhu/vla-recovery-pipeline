"""Bounded translation-only pregrasp control using RGB-D and proprioception.

This is a simulation integration canary, not a grasp or collision-free TAMP plan.
"""
import numpy as np
from .rgbd_observation import RGBDObservation, unproject_world


def make_pregrasp_plan(frame, mask, clearance_m=.12):
    if type(frame) is not RGBDObservation:
        raise TypeError('RGBDObservation required')
    mask=np.asarray(mask)
    if mask.dtype!=np.bool_ or mask.shape!=frame.depth_m.shape or not mask.any():
        raise ValueError('aligned nonempty bool mask required')
    if not np.isfinite(clearance_m) or not .10<=clearance_m<=.20:
        raise ValueError('clearance outside canary bounds')
    valid=mask & frame.depth_valid
    if valid.sum()<100 or valid.sum()/mask.sum()<.8:
        raise ValueError('insufficient current depth')
    points=unproject_world(frame)[mask[frame.depth_valid]]
    xy=np.median(points[:,:2],axis=0);z=float(np.percentile(points[:,2],95))+clearance_m
    goal=np.array([*xy,z]);start=np.asarray(frame.robot_state['robot0_eef_pos'],float)
    if start.shape!=(3,) or not np.isfinite(start).all():raise ValueError('invalid proprioception')
    if (not np.isfinite(goal).all() or not -.5<=goal[0]<=.4 or not -.5<=goal[1]<=.5 or not 1.0<=goal[2]<=1.5
            or np.linalg.norm(goal-start)>.35):
        raise ValueError('goal outside declared canary workspace or displacement bounds')
    safe_z=max(float(start[2]),z)
    waypoints=[[float(start[0]),float(start[1]),safe_z],[float(xy[0]),float(xy[1]),safe_z],goal.tolist()]
    return dict(kind='assistant_selected_rgbd_pregrasp_canary',episode_id=frame.episode_id,env_step=frame.env_step,
                camera_id=frame.camera_id,visible_depth_points=int(valid.sum()),visible_z_percentile95_m=z-clearance_m,
                clearance_m=clearance_m,goal_world_m=goal.tolist(),waypoints_world_m=waypoints,
                identity_verified=False,holding_verified=False,collision_free_verified=False,task_success_verified=False)


def translation_action(current, goal, *, tolerance_m=.008):
    current=np.asarray(current,float);goal=np.asarray(goal,float)
    if current.shape!=(3,) or goal.shape!=(3,) or not np.isfinite([current,goal]).all():
        raise ValueError('finite xyz vectors required')
    error=goal-current;distance=float(np.linalg.norm(error))
    if distance<=tolerance_m:return None,distance
    # Installed OSC_POSE maps +/-1 to +/-0.05m. Cap each command to 0.01m.
    action=np.zeros(7);action[:3]=np.clip(.5*error/.05,-.2,.2);action[6]=-1.
    return action,distance
