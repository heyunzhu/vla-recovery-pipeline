"""Static Panda link geometry along an offline IK candidate; no execution gate."""
from __future__ import annotations
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from .rgbd_observation import RGBDObservation,unproject_world
from .rgbd_scene_provider import _frame_digest
from .visual_robot_frames import STATIC_SOURCE_SHA256,infer_world_from_base,_pose
from .visual_panda_ik import JOINT_LIMITS
from .visual_gripper_path import supporting_planes,points_in_outer_body
from scripts.recovery.skill_pipeline.probe_static_wrist_gripper import pose,read_stl


def load_arm_model(model_dir):
    root=Path(model_dir).resolve();xml=root/'models/assets/robots/panda/robot.xml'
    if hashlib.sha256(xml.read_bytes()).hexdigest()!=STATIC_SOURCE_SHA256['panda/robot.xml']:
        raise ValueError('static Panda XML digest mismatch')
    expected=json.loads((Path(__file__).with_name('fixtures')/'panda_arm_collision_sha256.json').read_text())
    meshes={};proxies={};sources={'robot.xml':STATIC_SOURCE_SHA256['panda/robot.xml']}
    for name,digest in expected.items():
        path=xml.parent/'meshes'/name
        if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise ValueError('arm mesh digest mismatch: '+name)
        mesh=read_stl(path);meshes[name[:-4]]=mesh;proxies[name[:-4]]=supporting_planes(mesh);sources[name]=digest
    return dict(xml=ET.parse(xml),meshes=meshes,proxies=proxies,source_sha256=sources)


def arm_parts_at_joints(model,joints,world_from_base,*,geometry_mode='collision'):
    if geometry_mode not in ('collision','visual'):raise ValueError('unsupported arm geometry mode')
    q=np.asarray(joints,float)
    base=np.asarray(world_from_base,float)
    if (base.shape!=(4,4) or not np.isfinite(base).all() or not np.allclose(base[3],[0,0,0,1])
            or not np.allclose(base[:3,:3].T @ base[:3,:3],np.eye(3),atol=1e-6)
            or np.linalg.det(base[:3,:3])<0):
        raise ValueError('arm geometry requires a rigid base transform')
    if q.shape!=(7,) or not np.isfinite(q).all() or np.any(q<JOINT_LIMITS[:,0]) or np.any(q>JOINT_LIMITS[:,1]):
        raise ValueError('arm geometry requires joints within static limits')
    qmap={f'joint{i+1}':angle for i,angle in enumerate(q)};parts=[]
    def visit(body,parent):
        t=parent @ pose(body)
        for joint in body.findall('./joint'):
            if joint.get('name') not in qmap or joint.get('axis')!='0 0 1' or joint.get('pos','0 0 0')!='0 0 0':
                raise ValueError('unsupported static Panda joint')
            angle=qmap[joint.get('name')]
            t=t @ _pose((0,0,0),(np.cos(angle/2),0,0,np.sin(angle/2)))
        for geom in body.findall('./geom'):
            if geom.get('group')!=('0' if geometry_mode=='collision' else '1'):continue
            if geom.get('type')!='mesh':raise ValueError('unsupported Panda collision geom')
            mesh_name=geom.get('mesh');transform=t @ pose(geom)
            local=model['meshes'][mesh_name]
            world=local @ transform[:3,:3].T+transform[:3,3]
            parts.append(dict(name=geom.get('name') or mesh_name,mesh=mesh_name,world_from_geom=transform,
                              triangles_world_m=world,local_planes=model.get('proxies',{}).get(mesh_name)))
        for child in body.findall('./body'):visit(child,t)
    visit(model['xml'].find('./worldbody/body'),base)
    if len(parts)!=(8 if geometry_mode=='collision' else 50):raise ValueError('unexpected static Panda geometry count')
    return parts


def face_axis_overlap_candidate(vertices_a,vertices_b,axes):
    """A separating face axis proves convex-hull separation; overlap remains potential."""
    a=np.asarray(vertices_a,float);b=np.asarray(vertices_b,float)
    if np.any(a.max(axis=0)<b.min(axis=0)) or np.any(b.max(axis=0)<a.min(axis=0)):return False
    for axis in axes:
        pa=a @ axis;pb=b @ axis
        if pa.max()<pb.min()-1e-8 or pb.max()<pa.min()-1e-8:return False
    return True


def inspect_arm_joint_trajectory(frame,trajectory,model_dir,*,robot_pixels=None,margin_m=.002):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if trajectory.get('status')!='kinematic_candidate' or trajectory.get('frame_content_sha256')!=_frame_digest(frame).hex():
        raise ValueError('current converged joint trajectory required')
    if not trajectory.get('samples'):raise ValueError('nonempty joint trajectory required')
    if not np.isfinite(margin_m) or not 0<=margin_m<=.01:raise ValueError('invalid arm geometry margin')
    model=load_arm_model(model_dir);base=infer_world_from_base(frame)
    if not np.allclose(base,trajectory['world_from_base_candidate'],rtol=0,atol=1e-12):raise ValueError('IK base candidate changed')
    points=unproject_world(frame);pixel_yx=np.argwhere(frame.depth_valid);remaining=np.ones(len(points),bool)
    if robot_pixels is not None:
        from .visual_path_diagnostic import inspect_pregrasp_path
        # Reuse strict current-frame/depth-match validation.
        proposal=dict(episode_id=frame.episode_id,env_step=frame.env_step,camera_id=frame.camera_id,
                      waypoints_world_m=[frame.robot_state['robot0_eef_pos']])
        inspect_pregrasp_path(frame,proposal,robot_pixels=robot_pixels)
        remaining=~robot_pixels.mask[frame.depth_valid]
    rows=[]
    for index,sample in enumerate(trajectory['samples']):
        if sample['status']!='converged':raise ValueError('nonconverged trajectory sample')
        parts=arm_parts_at_joints(model,sample['joints'],base);hits=[];self_pairs=[]
        for part in parts:
            vertices=part['triangles_world_m'].reshape(-1,3);lo=vertices.min(axis=0);hi=vertices.max(axis=0)
            broad=np.flatnonzero(np.all((points>=lo-margin_m)&(points<=hi+margin_m),axis=1))
            transform=part['world_from_geom']
            local=(points[broad]-transform[:3,3]) @ transform[:3,:3]
            indices=broad[points_in_outer_body(local,part['local_planes'],margin_m)]
            kept=indices[remaining[indices]]
            if len(indices):
                witness=None;residual=None;projected=None
                if len(kept):
                    y,x=map(int,pixel_yx[kept[0]]);witness=[x,y]
                    if robot_pixels is not None:
                        projected=bool(np.isfinite(robot_pixels.mesh_depth_m[y,x]))
                        if projected:residual=float(frame.depth_m[y,x]-robot_pixels.mesh_depth_m[y,x])
                hits.append(dict(link_name=part['name'],raw_point_count=len(indices),remaining_point_count=len(kept),
                    first_remaining_pixel_xy=witness,first_remaining_pixel_model_projected=projected,
                    first_remaining_observed_minus_model_depth_m=residual))
        for i,a in enumerate(parts):
            for j,b in enumerate(parts):
                if j<=i+1:continue  # Only arm non-neighbour pairs, explicitly recorded below.
                axes=np.vstack((a['local_planes'][:,:3] @ a['world_from_geom'][:3,:3].T,
                                b['local_planes'][:,:3] @ b['world_from_geom'][:3,:3].T))
                if face_axis_overlap_candidate(a['triangles_world_m'].reshape(-1,3),b['triangles_world_m'].reshape(-1,3),axes):
                    self_pairs.append([a['name'],b['name']])
        rows.append(dict(sample_index=index,hits=hits,arm_nonadjacent_overlap_candidates=self_pairs))
    return dict(status='diagnostic_only',sample_count=len(rows),model_source_sha256=model['source_sha256'],
        robot_pixel_evidence=robot_pixels.report if robot_pixels is not None else None,
        removed_depth_matched_point_count=int((~remaining).sum()),
        frame_content_sha256=_frame_digest(frame).hex(),world_from_base_candidate=base.tolist(),
        observed_intersection_sample_count=sum(bool(row['hits']) for row in rows),
        remaining_intersection_sample_count=sum(any(hit['remaining_point_count'] for hit in row['hits']) for row in rows),
        self_overlap_candidate_sample_count=sum(bool(row['arm_nonadjacent_overlap_candidates']) for row in rows),samples=rows,
        margin_m=margin_m,arm_geometry='eight_collision_links_supporting_halfspace_outer_proxies',
        self_test='nonadjacent_arm_face_axis_candidates_without_edge_axis_test',adjacent_arm_pairs_skipped=True,
        gripper_self_pairs_checked=False,current_arm_pixels_not_removed=not (robot_pixels is not None and robot_pixels.report.get('arm_mesh_projected',False)),
        unmatched_robot_pixels_retained=True,unknown_space='unverified',
        continuous_sweep_verified=False,native_collision_verified=False,execution_allowed=False)
