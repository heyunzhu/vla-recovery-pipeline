"""Sampled static-gripper convex outer bodies against observed points.

Pad boxes are exact polyhedra. Mesh supporting planes form conservative outer
proxies; this is not a native solver collision test or continuous sweep.
"""
from __future__ import annotations
import numpy as np
from .rgbd_scene_provider import _frame_digest
from .rgbd_observation import RGBDObservation,unproject_world
from .visual_robot_pixels import StaticGripperGeometry
from .visual_path_diagnostic import inspect_pregrasp_path


def supporting_planes(triangles):
    t=np.asarray(triangles,float)
    if t.ndim!=3 or t.shape[1:]!=(3,3) or not len(t) or not np.isfinite(t).all():
        raise ValueError('finite triangles required')
    vertices=np.unique(t.reshape(-1,3),axis=0)
    normals=np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]);length=np.linalg.norm(normals,axis=1)
    good=length>1e-12;normals=normals[good]/length[good,None];anchors=t[good,0]
    planes=[]
    for n,a in zip(normals,anchors):
        d=float(n @ a);projected=vertices @ n
        if projected.max()<=d+1e-8:planes.append([*n,d])
        elif projected.min()>=d-1e-8:planes.append([*(-n),-d])
    # Bound even nonconvex meshes with incomplete supporting faces.
    for i in range(3):
        n=np.eye(3)[i];planes.extend(([*n,float(vertices[:,i].max())],[*(-n),float(-vertices[:,i].min())]))
    return np.unique(np.round(planes,12),axis=0)


def points_in_outer_body(points,planes,margin_m):
    points=np.asarray(points,float)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('finite xyz points required')
    if not np.isfinite(margin_m) or not 0<=margin_m<=.01:raise ValueError('invalid geometry margin')
    inside=np.ones(len(points),bool)
    for plane in planes:
        inside &= points @ plane[:3] <= plane[3]+margin_m+1e-10
    return inside


def inspect_gripper_path(frame,proposal,geometry,*,robot_pixels=None,spacing_m=.01,margin_m=.002):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if type(geometry) is not StaticGripperGeometry or geometry.frame_content_sha256!=_frame_digest(frame).hex() or geometry.report['geometry_mode']!='collision':
        raise ValueError('current collision gripper geometry required')
    # Reuse the established proposal bounds and pixel-evidence validation.
    baseline=inspect_pregrasp_path(frame,proposal,spacing_m=spacing_m,robot_pixels=robot_pixels)
    start=np.asarray(frame.robot_state['robot0_eef_pos'],float)
    path=np.vstack((start,np.asarray(proposal['waypoints_world_m'],float)));centres=[]
    for a,b in zip(path[:-1],path[1:]):
        centres.extend(np.linspace(a,b,max(2,int(np.ceil(np.linalg.norm(b-a)/spacing_m))+1)))
    points=unproject_world(frame);pixel_yx=np.argwhere(frame.depth_valid)
    remaining=np.ones(len(points),bool) if robot_pixels is None else ~robot_pixels.mask[frame.depth_valid]
    prepared=[]
    for part in geometry.parts:
        triangles=part['triangles_world_m'];vertices=triangles.reshape(-1,3)
        prepared.append((part,supporting_planes(triangles),vertices.min(axis=0),vertices.max(axis=0)))
    rows=[]
    for i,centre in enumerate(centres):
        delta=centre-start;raw_union=np.zeros(len(points),bool);hits=[]
        for part,planes,lo,hi in prepared:
            broad=np.flatnonzero(np.all((points>=lo+delta-margin_m)&(points<=hi+delta+margin_m),axis=1))
            indices=broad[points_in_outer_body(points[broad]-delta,planes,margin_m)]
            raw_union[indices]=True
            keep=indices[remaining[indices]]
            if len(keep):
                y,x=map(int,pixel_yx[keep[0]])
                hits.append(dict(part_name=part['name'],part_kind=part['kind'],remaining_point_count=len(keep),
                                 first_witness_pixel_xy=[x,y]))
        rows.append(dict(centre_index=i,eef_world_m=np.asarray(centre).tolist(),
                         raw_point_count=int(raw_union.sum()),remaining_point_count=int((raw_union&remaining).sum()),hits=hits))
    return dict(status='diagnostic_only',geometry='static_collision_parts_supporting_halfspace_outer_proxies',
        margin_m=margin_m,spacing_m=spacing_m,centre_count=len(rows),
        raw_intersection_centre_count=sum(row['raw_point_count']>0 for row in rows),
        remaining_intersection_centre_count=sum(row['remaining_point_count']>0 for row in rows),
        centres=rows,parts=[dict(name=p['name'],kind=p['kind'],plane_count=len(planes),
                               representation='exact_box' if p['kind']=='box' else 'convex_outer_proxy') for p,planes,_,_ in prepared],
        robot_pixel_mask_applied=robot_pixels is not None,baseline_sphere_diagnostic=baseline,
        static_geometry_provenance=geometry.report,
        orientation_and_gripper_qpos='fixed_at_current_observation',unknown_space='unverified',
        continuous_swept_volume_verified=False,full_arm_collision_verified=False,reachability='unknown',execution_allowed=False)
