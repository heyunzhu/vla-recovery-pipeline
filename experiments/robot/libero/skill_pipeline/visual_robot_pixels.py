"""Depth-consistent static gripper pixels, never a complete robot mask."""
from __future__ import annotations
import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
import numpy as np
from .rgbd_observation import RGBDObservation
from .rgbd_scene_provider import _frame_digest
from .visual_rim_grasp import rotation_xyzw
from .visual_robot_frames import STATIC_SOURCE_SHA256
from scripts.recovery.skill_pipeline.probe_static_wrist_gripper import pose,read_stl,raster_depth


@dataclass(frozen=True)
class RobotPixelEvidence:
    frame_content_sha256: str
    mask: np.ndarray
    mesh_depth_m: np.ndarray
    report: dict


def _owned(array):
    a=np.ascontiguousarray(array)
    return np.frombuffer(a.tobytes(),dtype=a.dtype).reshape(a.shape)


def project_static_gripper(frame,model_dir,*,depth_tolerance_m=.002):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if not np.isfinite(depth_tolerance_m) or not .0005<=depth_tolerance_m<=.005:
        raise ValueError('robot pixel depth tolerance outside declared range')
    root=Path(model_dir).resolve()
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    sources=manifest['source_sha256']
    expected=STATIC_SOURCE_SHA256['panda_gripper.xml']
    xml_rel='models/assets/grippers/panda_gripper.xml'
    if sources.get(xml_rel)!=expected:raise ValueError('unsupported static gripper model')
    def verified_path(relative):
        path=(root/relative).resolve()
        path.relative_to(root)
        rel=path.relative_to(root).as_posix()
        if rel not in sources or hashlib.sha256(path.read_bytes()).hexdigest()!=sources[rel]:
            raise ValueError('static model source digest mismatch: '+rel)
        return path
    gripper=ET.parse(verified_path(xml_rel));base=gripper.find('./worldbody/body')
    site=pose(base) @ pose(gripper.find('.//body[@name="eef"]')) @ pose(gripper.find('.//site[@name="grip_site"]'))
    # The deployment's quaternion refers to right_hand, position to grip_site.
    world_hand=np.eye(4);world_hand[:3,:3]=rotation_xyzw(frame.robot_state['robot0_eef_quat'])
    world_hand[:3,3]=np.asarray(frame.robot_state['robot0_eef_pos'])-world_hand[:3,:3] @ site[:3,3]
    camera_hand=np.linalg.inv(frame.T_world_camera) @ world_hand
    q=np.asarray(frame.robot_state['robot0_gripper_qpos'],float)
    if q.shape!=(2,) or not np.isfinite(q).all() or not 0<=q[0]<=.041 or not -.041<=q[1]<=0:
        raise ValueError('gripper positions incompatible with static slide model')
    qmap=dict(zip(('finger_joint1','finger_joint2'),q))
    meshes={};used_sources={xml_rel:expected}
    for element in gripper.findall('./asset/mesh'):
        relative=Path('models/assets/grippers')/element.get('file')
        path=verified_path(relative)
        meshes[element.get('name')]=read_stl(path)
        used_sources[path.relative_to(root).as_posix()]=sources[path.relative_to(root).as_posix()]
    triangles=[]
    def visit(body,parent):
        t=parent @ pose(body)
        for joint in body.findall('./joint'):
            if joint.get('type')!='slide' or joint.get('name') not in qmap:raise ValueError('unsupported gripper joint')
            jt=np.eye(4);jt[:3,3]=np.array([float(x) for x in joint.get('axis').split()])*qmap[joint.get('name')]
            t=t @ jt
        for geom in body.findall('./geom'):
            if geom.get('group')!='1' or geom.get('type')!='mesh':continue
            transform=camera_hand @ t @ pose(geom)
            v=meshes[geom.get('mesh')]
            triangles.append(v @ transform[:3,:3].T+transform[:3,3])
        for child in body.findall('./body'):visit(child,t)
    visit(base,np.eye(4))
    depth,skipped=raster_depth(np.concatenate(triangles),frame.K,frame.depth_m.shape)
    projected=np.isfinite(depth)
    matched=projected & frame.depth_valid & (np.abs(frame.depth_m-depth)<=depth_tolerance_m)
    report=dict(source='static_gripper_visual_mesh_depth_match',frame_content_sha256=_frame_digest(frame).hex(),
        depth_tolerance_m=depth_tolerance_m,projected_pixel_count=int(projected.sum()),
        matched_pixel_count=int(matched.sum()),triangles_skipped_near_plane=skipped,
        model_source_sha256=used_sources,complete_robot_mask=False,arm_mesh_projected=False,
        boundary_and_occlusion_uncertainty='retained',execution_allowed=False)
    return RobotPixelEvidence(report['frame_content_sha256'],_owned(matched),_owned(depth),report)
