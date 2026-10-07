"""Bounded offline approach alternatives; scores never certify safe motion."""
import copy
import numpy as np
from .visual_panda_ik import prepare_panda_joint_trajectory
from .visual_collision_changes import inspect_collision_changes


def approach_alternatives(frame,proposal):
    if any(proposal.get(k)!=getattr(frame,k) for k in ('episode_id','env_step','camera_id')):
        raise ValueError('approach snapshot mismatch')
    start=np.asarray(frame.robot_state['robot0_eef_pos'],float)
    goal=np.asarray(proposal['goal_world_m'],float)
    original=np.asarray(proposal['waypoints_world_m'],float)
    if goal.shape!=(3,) or original.shape!=(3,3) or not np.isfinite(original).all() or not np.array_equal(original[-1],goal):
        raise ValueError('three waypoint proposal and preserved goal required')
    candidates=[('original',original)]
    for height in (.02,.04):
        z=max(start[2],goal[2])+height
        candidates.append((f'raise_{round(height*1000)}mm',np.array([[*start[:2],z],[*goal[:2],z],goal])))
    for name,offset in [('retreat_x_positive',[.03,0]),('retreat_x_negative',[-.03,0]),
                        ('retreat_y_positive',[0,.03]),('retreat_y_negative',[0,-.03])]:
        retreat=start.copy();retreat[:2]+=offset
        z=max(start[2],goal[2]);candidates.append((name,np.array([retreat,[*goal[:2],z],goal])))
    results=[]
    for name,waypoints in candidates:
        if np.any(waypoints<[-.5,-.5,1.0]) or np.any(waypoints>[.4,.5,1.5]):continue
        p=copy.deepcopy(proposal);p['waypoints_world_m']=waypoints.tolist()
        results.append(dict(name=name,proposal=p))
    return results


def compare_approaches(frame,proposal,model_dir,pixels):
    reports=[];artifacts={};expected_baseline=None
    for candidate in approach_alternatives(frame,proposal):
        name=candidate['name'];ik=prepare_panda_joint_trajectory(frame,candidate['proposal'])
        report=dict(name=name,proposal=candidate['proposal'],ik=ik,execution_allowed=False)
        if ik['status']=='kinematic_candidate':
            changes,arrays=inspect_collision_changes(frame,ik,model_dir,pixels)
            if expected_baseline is None:expected_baseline=arrays['baseline_memberships']
            elif not np.array_equal(expected_baseline,arrays['baseline_memberships']):raise ValueError('path comparison baseline changed')
            counts=[p['new_membership_count'] for p in changes['poses']]
            path=np.vstack((frame.robot_state['robot0_eef_pos'],candidate['proposal']['waypoints_world_m']))
            report.update(collision_changes=changes,score=dict(max_new_memberships=max(counts),
                mean_new_memberships=float(np.mean(counts)),poses_with_new_memberships=changes['poses_with_new_memberships'],
                path_length_m=float(np.linalg.norm(np.diff(path,axis=0),axis=1).sum())))
            artifacts[name]=arrays
        reports.append(report)
    ranked=sorted((r for r in reports if 'score' in r),key=lambda r:(r['score']['max_new_memberships'],r['score']['mean_new_memberships'],r['score']['path_length_m']))
    return dict(status='offline_comparison_only',candidates=reports,ranking=[r['name'] for r in ranked],
        ranking_rule='max_new_memberships_then_sample_mean_then_length',
        baseline_constraints_ignored=False,ranking_certifies_safety=False,
        unknown_space='unverified',continuous_sweep_verified=False,execution_allowed=False),artifacts
