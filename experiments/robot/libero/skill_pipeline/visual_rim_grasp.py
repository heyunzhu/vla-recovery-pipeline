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


def make_visible_rim_candidate(frame,mask):
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
    if not np.isfinite(goal).all() or not .915<=goal[2]<=1.05 or np.linalg.norm(goal-current)>.2:
        raise ValueError('rim goal outside fixed simulation canary bounds')
    return dict(kind='visible_high_rim_pinch_candidate',episode_id=frame.episode_id,env_step=frame.env_step,
                visible_points=len(points),rim_candidate_points=len(rim),closing_axis_world_xy=axis.tolist(),
                visible_rim_anchor_world_m=anchor.tolist(),pinch_goal_world_m=goal.tolist(),
                align_goal_world_m=[float(goal[0]),float(goal[1]),float(current[2])],
                hand_pad_offset_world_m=pad_offset.tolist(),rim_depth_offset_m=.010,lift_m=.040,
                static_robot_basis='robosuite1.4.1 PandaGripper XML: finger slide axis hand Y, pad center z minus grip_site z = -.0036m',
                identity_verified=False,contact_verified=False,holding_verified=False,collision_free_verified=False)
