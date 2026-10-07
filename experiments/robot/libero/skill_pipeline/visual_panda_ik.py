"""Bounded offline Panda IK using static FK and a proprio-derived base candidate.

No environment/action interface. Convergence certifies only this kinematic
model, not independent calibration, collision clearance or task execution.
"""
from __future__ import annotations
import numpy as np
from .rgbd_observation import RGBDObservation
from .rgbd_scene_provider import _frame_digest
from .visual_robot_frames import panda_base_from_hand,infer_world_from_base,STATIC_SOURCE_SHA256
from .visual_rim_grasp import rotation_xyzw

JOINT_LIMITS=np.array([[-2.8973,2.8973],[-1.7628,1.7628],[-2.8973,2.8973],[-3.0718,-.0698],
                       [-2.8973,2.8973],[-.0175,3.7525],[-2.8973,2.8973]])


def rotation_log(rotation):
    r=np.asarray(rotation,float)
    angle=float(np.arccos(np.clip((np.trace(r)-1)/2,-1,1)))
    skew=np.array([r[2,1]-r[1,2],r[0,2]-r[2,0],r[1,0]-r[0,1]])
    if angle<1e-6:return skew*.5
    if np.pi-angle<1e-5:
        column=int(np.argmax(np.diag(r)))
        axis=(r+np.eye(3))[:,column];axis=axis/np.linalg.norm(axis)
        if axis @ skew<0:axis=-axis
        return axis*angle
    return skew*(angle/(2*np.sin(angle)))


def world_grip_pose(q,world_from_base):
    hand=world_from_base @ panda_base_from_hand(q)
    return hand[:3,3]+hand[:3,:3] @ np.array([0,0,.097]),hand[:3,:3]


def solve_panda_pose(q_seed,world_from_base,target_position,target_rotation,*,max_iterations=100):
    q=np.asarray(q_seed,float).copy();base=np.asarray(world_from_base,float)
    target=np.asarray(target_position,float);rotation=np.asarray(target_rotation,float)
    if q.shape!=(7,) or not np.isfinite(q).all() or np.any(q<JOINT_LIMITS[:,0]) or np.any(q>JOINT_LIMITS[:,1]):
        raise ValueError('IK seed must satisfy seven static joint limits')
    if (base.shape!=(4,4) or not np.isfinite(base).all() or not np.allclose(base[3],[0,0,0,1])
            or not np.allclose(base[:3,:3].T @ base[:3,:3],np.eye(3),atol=1e-6) or np.linalg.det(base[:3,:3])<0
            or target.shape!=(3,) or not np.isfinite(target).all()
            or rotation.shape!=(3,3) or not np.isfinite(rotation).all()
            or not np.allclose(rotation.T @ rotation,np.eye(3),atol=1e-6) or np.linalg.det(rotation)<0
            or type(max_iterations) is not int or not 1<=max_iterations<=300):
        raise ValueError('invalid rigid pose or iteration budget')
    for iteration in range(max_iterations+1):
        pos,r=world_grip_pose(q,base)
        error=np.r_[target-pos,rotation_log(rotation @ r.T)]
        if np.linalg.norm(error[:3])<=.001 and np.linalg.norm(error[3:])<=np.deg2rad(.5):break
        if iteration==max_iterations:break
        jac=np.empty((6,7));eps=1e-5
        for j in range(7):
            plus=q.copy();plus[j]+=eps
            p2,r2=world_grip_pose(plus,base)
            jac[:,j]=np.r_[(p2-pos)/eps,rotation_log(r2 @ r.T)/eps]
        weighted=error.copy();weighted[3:]*=.15;jac[3:]*=.15
        delta=jac.T @ np.linalg.solve(jac @ jac.T+np.eye(6)*.01**2,weighted)
        delta*=min(1,.08/max(np.linalg.norm(delta),1e-12))
        q=np.clip(q+delta,JOINT_LIMITS[:,0],JOINT_LIMITS[:,1])
    position_error=float(np.linalg.norm(error[:3]));rotation_error=float(np.degrees(np.linalg.norm(error[3:])))
    return dict(status='converged' if position_error<=.001 and rotation_error<=.5 else 'not_converged',
        joints=q.tolist(),position_error_m=position_error,rotation_error_deg=rotation_error,iterations=iteration,
        actual_position_world_m=pos.tolist(),actual_hand_rotation_world=r.tolist(),execution_allowed=False)


def prepare_panda_joint_trajectory(frame,proposal,*,spacing_m=.01,max_iterations=100):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if any(proposal.get(key)!=getattr(frame,key) for key in ('episode_id','env_step','camera_id')):
        raise ValueError('IK proposal snapshot mismatch')
    if not np.isfinite(spacing_m) or not .005<=spacing_m<=.03:raise ValueError('invalid IK path spacing')
    waypoints=np.asarray(proposal['waypoints_world_m'],float)
    if waypoints.ndim!=2 or waypoints.shape[1]!=3 or not 1<=len(waypoints)<=10 or not np.isfinite(waypoints).all():
        raise ValueError('finite bounded waypoints required')
    base=infer_world_from_base(frame);rotation=rotation_xyzw(frame.robot_state['robot0_eef_quat'])
    provenance=dict(frame_content_sha256=_frame_digest(frame).hex(),world_from_base_candidate=base.tolist(),
        static_source_sha256=STATIC_SOURCE_SHA256,independent_calibration_verified=False,
        collision_verified=False,velocity_acceleration_limits_verified=False,execution_allowed=False,
        method='finite_difference_damped_least_squares',max_iterations_per_sample=max_iterations)
    q=np.asarray(frame.robot_state['robot0_joint_pos'],float)
    points=np.vstack((np.asarray(frame.robot_state['robot0_eef_pos']),waypoints));rows=[];max_step=0.
    for segment,(a,b) in enumerate(zip(points[:-1],points[1:])):
        length=float(np.linalg.norm(b-a))
        if length>.5:raise ValueError('IK path segment exceeds bound')
        for target in np.linspace(a,b,max(2,int(np.ceil(length/spacing_m))+1)):
            solved=solve_panda_pose(q,base,target,rotation,max_iterations=max_iterations)
            next_q=np.asarray(solved['joints']);step=float(np.max(np.abs(next_q-q)));max_step=max(max_step,step)
            rows.append(dict(segment=segment,target_position_world_m=target.tolist(),max_joint_change_rad=step,**solved))
            if solved['status']!='converged' or step>.15:
                return dict(status='refused',reason='ik_not_converged' if solved['status']!='converged' else 'joint_step_exceeds_limit',
                    samples=rows,max_joint_change_rad=max_step,**provenance)
            q=next_q
    return dict(status='kinematic_candidate',reason=None,samples=rows,max_joint_change_rad=max_step,
        position_tolerance_m=.001,rotation_tolerance_deg=.5,max_joint_step_rad=.15,
        **provenance)
