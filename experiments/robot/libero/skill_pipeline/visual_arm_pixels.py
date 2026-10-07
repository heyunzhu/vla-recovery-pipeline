"""Current-pose visual arm and gripper z-buffer evidence from static geometry."""
import hashlib
import json
import xml.etree.ElementTree as ET
from pathlib import Path
import numpy as np
from .rgbd_observation import RGBDObservation
from .rgbd_scene_provider import _frame_digest
from .visual_robot_frames import STATIC_SOURCE_SHA256,infer_world_from_base
from .visual_arm_path import arm_parts_at_joints
from .visual_robot_pixels import RobotPixelEvidence,_owned,load_static_gripper_geometry
from scripts.recovery.skill_pipeline.probe_static_wrist_gripper import raster_depth


def read_obj_triangles(path):
    """Read static triangulated OBJ; reject polygons and out-of-range indices."""
    vertices=[];faces=[]
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        tokens=line.split()
        if not tokens:continue
        if tokens[0]=='v':
            if len(tokens)!=4:raise ValueError('expected three OBJ vertex coordinates')
            vertices.append([float(v) for v in tokens[1:]])
        elif tokens[0]=='f':
            if len(tokens)!=4:raise ValueError('expected triangulated OBJ')
            indices=[int(t.split('/')[0]) for t in tokens[1:]]
            if any(i<=0 or i>len(vertices) for i in indices):raise ValueError('invalid OBJ vertex index')
            faces.append([i-1 for i in indices])
    v=np.asarray(vertices,float)
    if not faces or v.ndim!=2 or not np.isfinite(v).all():raise ValueError('invalid OBJ geometry')
    return v[np.asarray(faces)]


def load_arm_visual_model(model_dir):
    root=Path(model_dir).resolve()/'models/assets/robots/panda'
    xml=root/'robot.xml';xml_sha=STATIC_SOURCE_SHA256['panda/robot.xml']
    if hashlib.sha256(xml.read_bytes()).hexdigest()!=xml_sha:raise ValueError('static Panda XML digest mismatch')
    expected=json.loads((Path(__file__).with_name('fixtures')/'panda_arm_visual_sha256.json').read_text())
    tree=ET.parse(xml);meshes={};sources={'robot.xml':xml_sha}
    used={geom.get('mesh') for geom in tree.findall('.//geom') if geom.get('group')=='1'}
    for asset in tree.findall('./asset/mesh'):
        if asset.get('name') not in used:continue
        relative=asset.get('file');path=(root/relative).resolve();path.relative_to(root)
        if relative not in expected or hashlib.sha256(path.read_bytes()).hexdigest()!=expected[relative]:
            raise ValueError('arm visual mesh digest mismatch: '+relative)
        if asset.get('scale','1 1 1')!='1 1 1':raise ValueError('unsupported mesh scale')
        meshes[asset.get('name')]=read_obj_triangles(path);sources[relative]=expected[relative]
    if len(meshes)!=50:raise ValueError('expected fifty Panda visual meshes')
    return dict(xml=tree,meshes=meshes,source_sha256=sources)


def depth_match_evidence(frame,depth,*,depth_tolerance_m,source_sha256,skipped,geom_names):
    if not np.isfinite(depth_tolerance_m) or not .0005<=depth_tolerance_m<=.005:
        raise ValueError('robot pixel depth tolerance outside declared range')
    depth=np.asarray(depth,float)
    if depth.shape!=frame.depth_m.shape or np.isnan(depth).any() or np.any(depth<=0):raise ValueError('invalid projected depth')
    projected=np.isfinite(depth);matched=projected & frame.depth_valid & (np.abs(frame.depth_m-depth)<=depth_tolerance_m)
    report=dict(source='static_arm_gripper_visual_mesh_depth_match',geometry_mode='visual',
        frame_content_sha256=_frame_digest(frame).hex(),depth_tolerance_m=depth_tolerance_m,
        projected_pixel_count=int(projected.sum()),matched_pixel_count=int(matched.sum()),
        unmatched_valid_projected_pixel_count=int((projected & frame.depth_valid & ~matched).sum()),
        projected_geom_names=geom_names,triangles_skipped_near_plane=skipped,model_source_sha256=source_sha256,
        arm_mesh_projected=True,complete_robot_mask=False,eligible_for_point_removal=True,
        boundary_and_occlusion_uncertainty='retained',execution_allowed=False)
    return RobotPixelEvidence(report['frame_content_sha256'],_owned(matched),_owned(depth),report)


def project_static_arm_gripper(frame,model_dir,*,depth_tolerance_m=.002):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    model=load_arm_visual_model(model_dir)
    parts=arm_parts_at_joints(model,frame.robot_state['robot0_joint_pos'],infer_world_from_base(frame),geometry_mode='visual')
    gripper=load_static_gripper_geometry(frame,model_dir,geometry_mode='visual')
    camera=np.linalg.inv(frame.T_world_camera)
    triangles=np.concatenate([p['triangles_world_m'] for p in parts+list(gripper.parts)])
    triangles=triangles @ camera[:3,:3].T+camera[:3,3]
    depth,skipped=raster_depth(triangles,frame.K,frame.depth_m.shape)
    sources={'arm/'+k:v for k,v in model['source_sha256'].items()}
    sources.update(gripper.report['model_source_sha256'])
    return depth_match_evidence(frame,depth,depth_tolerance_m=depth_tolerance_m,source_sha256=sources,
        skipped=skipped,geom_names=[p['name'] for p in parts+list(gripper.parts)])
