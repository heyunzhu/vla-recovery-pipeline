"""Static Panda FK and candidate base inference from whitelisted proprioception.

EEF position is grip_site; EEF xyzw orientation follows right_hand in this
robosuite deployment. Inferring a transform is not independent calibration.
"""
from __future__ import annotations
import numpy as np
from .visual_rim_grasp import rotation_xyzw
from .rgbd_observation import RGBDObservation

STATIC_SOURCE_SHA256 = {
    "panda/robot.xml": "263c0f9abacbc8686027ec5545bee144481cbcf5cc74aa421cbe3227030cd95e",
    "panda_gripper.xml": "d9d68123909d6910488310d0fae4e358ed4ac831c6d0957f3e30893a5412baac",
}
_POS = [(0,0,.333),(0,0,0),(0,-.316,0),(.0825,0,0),(-.0825,.384,0),(0,0,0),(.088,0,0)]
_QUAT = [(1,0,0,0),(.707107,-.707107,0,0),(.707107,.707107,0,0),
         (.707107,.707107,0,0),(.707107,-.707107,0,0),(.707107,.707107,0,0),(.707107,.707107,0,0)]


def _pose(pos, wxyz):
    t=np.eye(4);t[:3,:3]=rotation_xyzw([*wxyz[1:],wxyz[0]]);t[:3,3]=pos
    return t


def panda_base_from_hand(joints):
    q=np.asarray(joints,float)
    if q.shape!=(7,) or not np.isfinite(q).all():raise ValueError('seven finite Panda joint positions required')
    t=np.eye(4)
    for pos,quat,angle in zip(_POS,_QUAT,q):
        rotation=_pose((0,0,0),(np.cos(angle/2),0,0,np.sin(angle/2)))
        t=t @ _pose(pos,quat) @ rotation
    return t @ _pose((0,0,.1065),(.924,0,0,-.383))


def infer_world_from_base(frame):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    state=frame.robot_state
    rotation=rotation_xyzw(state['robot0_eef_quat'])
    pos=np.asarray(state['robot0_eef_pos'],float)
    if pos.shape!=(3,) or not np.isfinite(pos).all():raise ValueError('finite grip_site position required')
    world_hand=np.eye(4);world_hand[:3,:3]=rotation
    world_hand[:3,3]=pos-rotation @ np.array([0,0,.097])
    return world_hand @ np.linalg.inv(panda_base_from_hand(state['robot0_joint_pos']))


def base_frame_evidence(frame):
    return dict(source='static_panda_fk_and_proprio_candidate',snapshot_id=f'{frame.episode_id}:step{frame.env_step}:{frame.camera_id}',
        static_source_sha256=STATIC_SOURCE_SHA256,world_from_base_candidate=infer_world_from_base(frame).tolist(),
        position_reference='grip_site',orientation_reference='right_hand_xyzw',hand_to_grip_site_z_m=.097,
        independent_calibration_verified=False,solver_allowed=False)


def compare_base_estimates(frames):
    if len(frames)<2:raise ValueError('at least two observations required')
    if any(f.episode_id!=frames[0].episode_id or f.calibration_version!=frames[0].calibration_version for f in frames):
        raise ValueError('base consistency requires the same episode and calibration')
    if len({f.env_step for f in frames})!=len(frames):raise ValueError('distinct observation steps required')
    reference=infer_world_from_base(frames[0]);rows=[]
    for frame in frames:
        t=infer_world_from_base(frame)
        angle=np.degrees(np.arccos(np.clip((np.trace(reference[:3,:3].T @ t[:3,:3])-1)/2,-1,1)))
        rows.append(dict(env_step=frame.env_step,position_difference_m=float(np.linalg.norm(t[:3,3]-reference[:3,3])),
                         rotation_difference_deg=float(angle)))
    return dict(reference=base_frame_evidence(frames[0]),comparisons=rows,
                scope='same_episode_consistency_not_independent_calibration',solver_allowed=False)
