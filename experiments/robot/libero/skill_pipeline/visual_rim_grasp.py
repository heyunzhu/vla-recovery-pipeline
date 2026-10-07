"""An explicit visible-rim candidate for the single-task simulation canary."""
import numpy as np
from .rgbd_observation import RGBDObservation, unproject_world


def rotation_xyzw(quat):
    q=np.asarray(quat,float)
    if q.shape!=(4,) or not np.isfinite(q).all() or np.linalg.norm(q)<1e-12:
        raise ValueError('invalid robot quaternion')
    x,y,z,w=q/np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def derive_visible_rim_geometry(frame,mask):
    """Derive observed geometry; distance to the current EEF is not a geometry filter."""
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    mask=np.asarray(mask)
    if mask.dtype!=np.bool_ or mask.shape!=frame.depth_m.shape or not mask.any():raise ValueError('aligned bool mask required')
    points=unproject_world(frame)[mask[frame.depth_valid]]
    if len(points)<100 or len(points)/mask.sum()<.8:raise ValueError('insufficient current depth')
    R=rotation_xyzw(frame.robot_state['robot0_eef_quat'])
    if R[2,2]>-.98:raise ValueError('canary requires approximately downward hand z')
    # Static PandaGripper finger slide direction in right_hand coordinates is +Y.
    axis=R[:2,1];axis=axis/np.linalg.norm(axis)
    high=points[points[:,2]>=np.percentile(points[:,2],85)]
    along=high[:,:2]@axis
    rim=high[along>=np.percentile(along,85)]
    if len(rim)<20:raise ValueError('insufficient visible high rim candidate')
    anchor=np.median(rim,axis=0)
    # Static pad center is local z=-.0036 from grip_site. Aim 10mm below visible rim.
    pad_offset=R@np.array([0.,0.,-.0036])
    goal=anchor-pad_offset;goal[2]-=.010
    current=np.asarray(frame.robot_state['robot0_eef_pos'],float)
    if current.shape!=(3,) or not np.isfinite(current).all() or not np.isfinite(goal).all():
        raise ValueError('finite robot position and rim geometry required')
    return dict(kind='visible_high_rim_pinch_candidate',episode_id=frame.episode_id,env_step=frame.env_step,
                visible_points=len(points),rim_candidate_points=len(rim),closing_axis_world_xy=axis.tolist(),
                visible_rim_anchor_world_m=anchor.tolist(),pinch_goal_world_m=goal.tolist(),
                align_goal_world_m=[float(goal[0]),float(goal[1]),float(current[2])],
                hand_pad_offset_world_m=pad_offset.tolist(),rim_depth_offset_m=.010,lift_m=.040,
                static_robot_basis='robosuite1.4.1 PandaGripper XML: finger slide axis hand Y, pad center z minus grip_site z = -.0036m',
                identity_verified=False,contact_verified=False,holding_verified=False,collision_free_verified=False)


def assess_rim_approach(frame,candidate):
    """Check the old canary pose limits, without claiming reachability or collision clearance."""
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if candidate['episode_id']!=frame.episode_id or candidate['env_step']!=frame.env_step:
        raise ValueError('rim candidate is not from the current frame')
    goal=np.asarray(candidate['pinch_goal_world_m'],float)
    current=np.asarray(frame.robot_state['robot0_eef_pos'],float)
    if goal.shape!=(3,) or current.shape!=(3,) or not np.isfinite([goal,current]).all():
        raise ValueError('finite xyz required for approach assessment')
    distance=float(np.linalg.norm(goal-current))
    failures=[]
    if not .915<=goal[2]<=1.05:failures.append('candidate_height_outside_canary_bounds')
    if distance>.2:failures.append('current_eef_distance_exceeds_canary_limit')
    return dict(canary_pose_gate_status='refused' if failures else 'passed',failed_checks=failures,
                candidate_height_world_m=float(goal[2]),height_bounds_world_m=[.915,1.05],
                current_eef_distance_m=distance,max_current_eef_distance_m=.2,
                reachability='unknown',path_collision='unknown',execution_allowed=False)


def make_visible_rim_candidate(frame,mask):
    """Legacy action canaries retain both original pose gates."""
    candidate=derive_visible_rim_geometry(frame,mask)
    assessment=assess_rim_approach(frame,candidate)
    if assessment['canary_pose_gate_status']!='passed':
        raise ValueError('rim goal outside fixed simulation canary bounds: '+','.join(assessment['failed_checks']))
    return candidate
