"""Remaining point attribution and gripper/arm face-axis pair diagnostics."""
import numpy as np
from .rgbd_observation import unproject_world
from .rgbd_scene_provider import _frame_digest
from .visual_robot_frames import infer_world_from_base,panda_base_from_hand
from .visual_arm_path import load_arm_model,arm_parts_at_joints,face_axis_overlap_candidate
from .visual_robot_pixels import load_static_gripper_geometry
from .visual_gripper_path import supporting_planes,points_in_outer_body
from .visual_mesh_diagnostic import classify_mesh_points


def attribute_current_arm_hits(frame,model_dir,robot_pixels,*,margin_m=.002):
    from .visual_path_diagnostic import inspect_pregrasp_path
    inspect_pregrasp_path(frame,dict(episode_id=frame.episode_id,env_step=frame.env_step,camera_id=frame.camera_id,
        waypoints_world_m=[frame.robot_state['robot0_eef_pos']]),robot_pixels=robot_pixels)
    model=load_arm_model(model_dir);base=infer_world_from_base(frame)
    points=unproject_world(frame);pixels=np.argwhere(frame.depth_valid)
    remaining=~robot_pixels.mask[frame.depth_valid];parts=arm_parts_at_joints(model,frame.robot_state['robot0_joint_pos'],base)
    rows=[]
    for part in parts:
        transform=part['world_from_geom'];local=(points-transform[:3,3]) @ transform[:3,:3]
        selected=np.flatnonzero(remaining & points_in_outer_body(local,part['local_planes'],margin_m))
        diagnostic=classify_mesh_points(local[selected],model['meshes'][part['mesh']],margin_m=margin_m)
        counts={};evidence=[]
        for index,result in zip(selected,diagnostic['points']):
            y,x=map(int,pixels[index]);projected=np.isfinite(robot_pixels.mesh_depth_m[y,x])
            counts[result['category']]=counts.get(result['category'],0)+1
            evidence.append(dict(pixel_xy=[x,y],point_world_m=points[index].tolist(),**result,
                observed_minus_model_depth_m=float(frame.depth_m[y,x]-robot_pixels.mesh_depth_m[y,x]) if projected else None))
        rows.append(dict(link_name=part['name'],remaining_outer_proxy_point_count=len(selected),categories=counts,
            topology=diagnostic['topology'],points=evidence))
    return dict(scope='current_proprio_pose_only_not_future_trajectory',frame_content_sha256=_frame_digest(frame).hex(),
        links=rows,margin_m=margin_m,method='triangle_distance_and_two_ray_parity_no_points_removed',
        model_source_sha256=model['source_sha256'],execution_allowed=False)


def transform_gripper_parts(geometry,current_hand,candidate_hand):
    delta=candidate_hand @ np.linalg.inv(current_hand)
    return [dict(name=p['name'],triangles_world_m=p['triangles_world_m'] @ delta[:3,:3].T+delta[:3,3]) for p in geometry.parts]


def inspect_gripper_arm_pairs(frame,trajectory,model_dir):
    if trajectory.get('frame_content_sha256')!=_frame_digest(frame).hex() or trajectory.get('status')!='kinematic_candidate' or not trajectory.get('samples'):
        raise ValueError('current converged joint trajectory required')
    base=infer_world_from_base(frame)
    if not np.allclose(base,trajectory['world_from_base_candidate'],rtol=0,atol=1e-12):raise ValueError('IK base candidate changed')
    model=load_arm_model(model_dir);gripper=load_static_gripper_geometry(frame,model_dir,geometry_mode='collision')
    current_hand=base @ panda_base_from_hand(frame.robot_state['robot0_joint_pos'])
    rows=[]
    for i,sample in enumerate(trajectory['samples']):
        if sample['status']!='converged':raise ValueError('nonconverged trajectory sample')
        arms=arm_parts_at_joints(model,sample['joints'],base)
        parts=transform_gripper_parts(gripper,current_hand,base @ panda_base_from_hand(sample['joints']))
        pairs=[]
        for part in parts:
            planes=supporting_planes(part['triangles_world_m'])
            for arm in arms[:-1]: # link7 directly attaches to the gripper; explicit exclusion.
                axes=np.vstack((planes[:,:3],arm['local_planes'][:,:3] @ arm['world_from_geom'][:3,:3].T))
                if face_axis_overlap_candidate(part['triangles_world_m'].reshape(-1,3),arm['triangles_world_m'].reshape(-1,3),axes):
                    pairs.append([part['name'],arm['name']])
        rows.append(dict(sample_index=i,overlap_candidates=pairs))
    return dict(sample_count=len(rows),pairs_checked_per_sample=len(gripper.parts)*7,
        candidate_sample_count=sum(bool(r['overlap_candidates']) for r in rows),samples=rows,
        method='face_axis_separation_without_edge_axis_test',excluded_arm_link='link7_direct_attachment',
        gripper_internal_pairs_checked=False,gripper_qpos='fixed_at_current_observation',
        model_source_sha256=model['source_sha256'],gripper_source_sha256=gripper.report['model_source_sha256'],
        native_collision_verified=False,continuous_sweep_verified=False,execution_allowed=False)
