"""Compare observed point/part memberships to the actual current joint pose.

Baseline intersections remain unresolved. Joint subdivision is discrete, not
continuous collision detection, and never authorizes execution.
"""
import numpy as np
from .rgbd_observation import RGBDObservation,unproject_world
from .rgbd_scene_provider import _frame_digest
from .visual_robot_frames import infer_world_from_base,panda_base_from_hand
from .visual_panda_ik import JOINT_LIMITS
from .visual_arm_path import load_arm_model,arm_parts_at_joints
from .visual_robot_pixels import load_static_gripper_geometry
from .visual_gripper_path import supporting_planes,points_in_outer_body
from .visual_mesh_diagnostic import classify_mesh_points


def subdivide_joint_path(current,targets,*,max_joint_step_rad=.01):
    if not np.isfinite(max_joint_step_rad) or not .001<=max_joint_step_rad<=.05:
        raise ValueError('invalid joint subdivision bound')
    q=np.asarray(current,float);targets=np.asarray(targets,float)
    if q.shape!=(7,) or targets.ndim!=2 or targets.shape[1]!=7 or not len(targets):
        raise ValueError('seven joint coordinates and nonempty targets required')
    all_q=np.vstack((q,targets))
    if not np.isfinite(all_q).all() or np.any(all_q<JOINT_LIMITS[:,0]) or np.any(all_q>JOINT_LIMITS[:,1]):
        raise ValueError('joint path outside static limits')
    rows=[dict(joints=q.tolist(),target_sample_index=None,fraction=0.)]
    for index,target in enumerate(targets):
        change=float(np.max(np.abs(target-q)))
        if change>1e-12:
            count=int(np.ceil(change/max_joint_step_rad))
            for step in range(1,count+1):
                fraction=step/count
                rows.append(dict(joints=(q+(target-q)*fraction).tolist(),target_sample_index=index,fraction=fraction))
        q=target
    return rows


def membership_changes(baseline,current):
    """Indices belong to one part; a different part is a new membership."""
    baseline=np.asarray(baseline,dtype=np.int64);current=np.asarray(current,dtype=np.int64)
    return dict(new=np.setdiff1d(current,baseline),persistent=np.intersect1d(current,baseline),
                resolved=np.setdiff1d(baseline,current))


def outer_hit_indices(points,remaining,part,margin_m):
    triangles=part['triangles_world_m'];lo=triangles.reshape(-1,3).min(axis=0);hi=triangles.reshape(-1,3).max(axis=0)
    broad=np.flatnonzero(remaining & np.all((points>=lo-margin_m)&(points<=hi+margin_m),axis=1))
    transform=part['world_from_geom'];local=(points[broad]-transform[:3,3]) @ transform[:3,:3]
    return broad[points_in_outer_body(local,part['local_planes'],margin_m)]


def inspect_collision_changes(frame,trajectory,model_dir,robot_pixels,*,max_joint_step_rad=.01,margin_m=.002):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if trajectory.get('status')!='kinematic_candidate' or trajectory.get('frame_content_sha256')!=_frame_digest(frame).hex() or not trajectory.get('samples'):
        raise ValueError('current converged joint trajectory required')
    if not np.isfinite(margin_m) or not 0<=margin_m<=.01:raise ValueError('invalid geometry margin')
    if any(sample['status']!='converged' for sample in trajectory['samples']):raise ValueError('nonconverged sample')
    from .visual_path_diagnostic import inspect_pregrasp_path
    inspect_pregrasp_path(frame,dict(episode_id=frame.episode_id,env_step=frame.env_step,camera_id=frame.camera_id,
        waypoints_world_m=[frame.robot_state['robot0_eef_pos']]),robot_pixels=robot_pixels)
    base=infer_world_from_base(frame)
    if not np.allclose(base,trajectory['world_from_base_candidate'],rtol=0,atol=1e-12):raise ValueError('IK base candidate changed')
    arm=load_arm_model(model_dir);gripper=load_static_gripper_geometry(frame,model_dir,geometry_mode='collision')
    current_hand=base @ panda_base_from_hand(frame.robot_state['robot0_joint_pos'])
    gripper_local=[]
    for part in gripper.parts:
        local=(part['triangles_world_m']-current_hand[:3,3]) @ current_hand[:3,:3]
        gripper_local.append(dict(name=part['name'],triangles=local,planes=supporting_planes(local)))
    def parts_at(q):
        parts=arm_parts_at_joints(arm,q,base);hand=base @ panda_base_from_hand(q)
        for p in gripper_local:
            parts.append(dict(name=p['name'],mesh=None,world_from_geom=hand,local_planes=p['planes'],
                triangles_local_m=p['triangles'],triangles_world_m=p['triangles'] @ hand[:3,:3].T+hand[:3,3]))
        return parts
    points=unproject_world(frame);pixel_yx=np.argwhere(frame.depth_valid)
    flat_pixels=np.flatnonzero(frame.depth_valid);remaining=~robot_pixels.mask[frame.depth_valid]
    poses=subdivide_joint_path(frame.robot_state['robot0_joint_pos'],[s['joints'] for s in trajectory['samples']],max_joint_step_rad=max_joint_step_rad)
    baseline_parts=parts_at(frame.robot_state['robot0_joint_pos'])
    names=[p['name'] for p in baseline_parts]
    baseline=[outer_hit_indices(points,remaining,p,margin_m) for p in baseline_parts]
    baseline_records=[[i,int(flat_pixels[j])] for i,indices in enumerate(baseline) for j in indices]
    records=[];rows=[];first_events=[];seen_parts=set()
    for pose_index,pose in enumerate(poses):
        hits=[];union=set();new_total=persistent_total=resolved_total=0
        for part_index,part in enumerate(parts_at(pose['joints'])):
            indices=outer_hit_indices(points,remaining,part,margin_m)
            change=membership_changes(baseline[part_index],indices)
            new_total+=len(change['new']);persistent_total+=len(change['persistent']);resolved_total+=len(change['resolved'])
            records.extend([pose_index,part_index,int(flat_pixels[j])] for j in indices)
            union.update(map(int,indices))
            if len(indices) or len(change['resolved']):
                hits.append(dict(part_index=part_index,part_name=part['name'],remaining_point_count=len(indices),
                    new_membership_count=len(change['new']),persistent_membership_count=len(change['persistent']),
                    resolved_baseline_membership_count=len(change['resolved'])))
            if len(change['new']) and part_index not in seen_parts:
                seen_parts.add(part_index);chosen=change['new'][:3]
                transform=part['world_from_geom'];local=(points[chosen]-transform[:3,3]) @ transform[:3,:3]
                mesh=arm['meshes'][part['mesh']] if part['mesh'] is not None else part['triangles_local_m']
                diagnostic=classify_mesh_points(local,mesh,margin_m=margin_m)
                witnesses=[]
                for j,result in zip(chosen,diagnostic['points']):
                    y,x=map(int,pixel_yx[j]);projected=np.isfinite(robot_pixels.mesh_depth_m[y,x])
                    witnesses.append(dict(pixel_xy=[x,y],point_world_m=points[j].tolist(),**result,
                        current_visual_depth_residual_m=float(frame.depth_m[y,x]-robot_pixels.mesh_depth_m[y,x]) if projected else None))
                first_events.append(dict(part_index=part_index,part_name=part['name'],pose_index=pose_index,
                    target_sample_index=pose['target_sample_index'],fraction=pose['fraction'],witnesses=witnesses,
                    witness_mesh_topology=diagnostic['topology']))
        rows.append(dict(pose_index=pose_index,**pose,hits=hits,remaining_unique_point_count=len(union),
            new_membership_count=new_total,persistent_membership_count=persistent_total,resolved_baseline_membership_count=resolved_total))
    report=dict(status='diagnostic_only',frame_content_sha256=_frame_digest(frame).hex(),world_from_base_candidate=base.tolist(),
        part_names=names,input_sample_count=len(trajectory['samples']),subdivided_pose_count=len(poses),
        max_joint_step_rad=max_joint_step_rad,margin_m=margin_m,baseline_membership_count=sum(map(len,baseline)),
        baseline_unique_point_count=len(set(j for indices in baseline for j in indices)),
        poses_with_new_memberships=sum(r['new_membership_count']>0 for r in rows),first_new_events=first_events,poses=rows,
        membership_key='part_index_and_current_frame_flat_pixel_index',baseline_pose='actual_current_proprio',
        baseline_intersections_ignored=False,new_membership_is_external_collision=False,
        fixed_point_cloud=True,unknown_space='unverified',gripper_qpos='fixed_current',
        continuous_sweep_verified=False,native_collision_verified=False,execution_allowed=False,
        arm_model_source_sha256=arm['source_sha256'],gripper_source_sha256=gripper.report['model_source_sha256'])
    arrays=dict(baseline_memberships=np.asarray(baseline_records,np.int64).reshape(-1,2),
                observed_memberships=np.asarray(records,np.int64).reshape(-1,3))
    return report,arrays
