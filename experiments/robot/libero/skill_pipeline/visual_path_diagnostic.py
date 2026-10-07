"""Sampled EEF sphere proxy and optical-depth visibility, not collision certification."""
from __future__ import annotations
import numpy as np
from .rgbd_observation import RGBDObservation, unproject_world


def inspect_pregrasp_path(frame, proposal, *, probe_radius_m=.04, spacing_m=.01, depth_margin_m=.005, robot_pixels=None):
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    if proposal.get('episode_id')!=frame.episode_id or proposal.get('env_step')!=frame.env_step or proposal.get('camera_id')!=frame.camera_id:
        raise ValueError('path proposal does not match observation')
    if not np.isfinite([probe_radius_m,spacing_m,depth_margin_m]).all() or not .01<=probe_radius_m<=.15 or not .002<=spacing_m<=.05 or not 0<=depth_margin_m<=.02:
        raise ValueError('invalid path diagnostic thresholds')
    start=np.asarray(frame.robot_state['robot0_eef_pos'],float)
    waypoints=np.asarray(proposal['waypoints_world_m'],float)
    if start.shape!=(3,) or waypoints.ndim!=2 or waypoints.shape[1]!=3 or not 1<=len(waypoints)<=10 or not np.isfinite(waypoints).all():
        raise ValueError('finite bounded xyz waypoints required')
    path=np.vstack((start,waypoints));centres=[]
    for a,b in zip(path[:-1],path[1:]):
        length=np.linalg.norm(b-a)
        if length>.5:raise ValueError('path segment exceeds diagnostic bound')
        centres.extend(np.linspace(a,b,max(2,int(np.ceil(length/spacing_m))+1)))
    centres=np.asarray(centres)
    offsets=np.vstack((np.zeros((1,3)),np.eye(3),-np.eye(3))) * probe_radius_m
    probes=(centres[:,None,:]+offsets[None,:,:]).reshape(-1,3)
    camera=np.linalg.inv(frame.T_world_camera)
    xyz=probes @ camera[:3,:3].T+camera[:3,3]
    uvw=xyz @ frame.K.T
    uv=np.divide(uvw[:,:2],uvw[:,2,None],out=np.full((len(xyz),2),np.nan),where=uvw[:,2,None]>1e-8)
    in_view=(xyz[:,2]>1e-8)&np.isfinite(uv).all(axis=1)&(uv[:,0]>=0)&(uv[:,0]<frame.rgb.shape[1])&(uv[:,1]>=0)&(uv[:,1]<frame.rgb.shape[0])
    valid=np.zeros(len(xyz),bool);depth=np.full(len(xyz),np.nan)
    ix=np.flatnonzero(in_view);pixels=np.floor(uv[ix]).astype(int)
    valid[ix]=frame.depth_valid[pixels[:,1],pixels[:,0]]
    depth[ix]=frame.depth_m[pixels[:,1],pixels[:,0]]
    front=valid & (xyz[:,2]<depth-depth_margin_m)
    # Compare against ALL observed points; no target or robot pixels are silently removed.
    points=unproject_world(frame)
    nearest=[float(np.sqrt(np.min(np.sum((points-centre)**2,axis=1)))) if len(points) else None for centre in centres]
    intersect=[i for i,d in enumerate(nearest) if d is not None and d<=probe_radius_m]
    result=dict(status='diagnostic_only',probe_shape='declared_eef_sphere_not_robot_mesh',probe_radius_m=probe_radius_m,
        spacing_m=spacing_m,depth_margin_m=depth_margin_m,centre_count=len(centres),probe_count=len(probes),
        front_of_observed_surface_count=int(front.sum()),outside_view_count=int((~in_view).sum()),
        invalid_depth_count=int((in_view & ~valid).sum()),occluded_or_near_surface_count=int((valid & ~front).sum()),
        observed_point_intersection_count=len(intersect),first_intersection_centre_index=intersect[0] if intersect else None,
        min_observed_point_distance_m=min((d for d in nearest if d is not None),default=None),
        observed_points_include_robot=True,unknown_space='unverified',full_arm_collision_verified=False,
        continuous_swept_volume_verified=False,reachability='unknown',execution_allowed=False)
    if robot_pixels is not None:
        from .visual_robot_pixels import RobotPixelEvidence
        from .rgbd_scene_provider import _frame_digest
        if type(robot_pixels) is not RobotPixelEvidence or robot_pixels.frame_content_sha256!=_frame_digest(frame).hex():
            raise ValueError('robot pixels do not match current observation')
        mask=robot_pixels.mask
        if mask.dtype!=np.bool_ or mask.shape!=frame.depth_m.shape or np.any(mask & ~frame.depth_valid):
            raise ValueError('invalid robot pixel evidence')
        model_depth=robot_pixels.mesh_depth_m
        tolerance=robot_pixels.report.get('depth_tolerance_m')
        if (model_depth.shape!=mask.shape or not isinstance(tolerance,(float,int))
                or not .0005<=tolerance<=.005
                or not np.array_equal(mask,np.isfinite(model_depth)&frame.depth_valid&(np.abs(frame.depth_m-model_depth)<=tolerance))):
            raise ValueError('robot mask does not follow declared depth consistency')
        points_remaining=points[~mask[frame.depth_valid]]
        pixel_yx=np.argwhere(frame.depth_valid)[~mask[frame.depth_valid]]
        remaining=[];witnesses=[]
        for i,centre in enumerate(centres):
            if not len(points_remaining):remaining.append(None);continue
            distances=np.sum((points_remaining-centre)**2,axis=1)
            index=int(np.argmin(distances));distance=float(np.sqrt(distances[index]));remaining.append(distance)
            if distance<=probe_radius_m:
                y,x=map(int,pixel_yx[index])
                projected=np.isfinite(model_depth[y,x])
                witnesses.append(dict(centre_index=i,pixel_xy=[x,y],point_world_m=points_remaining[index].tolist(),
                    distance_m=distance,gripper_mesh_projected=bool(projected),
                    observed_minus_mesh_depth_m=float(frame.depth_m[y,x]-model_depth[y,x]) if projected else None))
        count=sum(d is not None and d<=probe_radius_m for d in remaining)
        result.update(robot_pixel_evidence=robot_pixels.report,removed_matched_gripper_point_count=int(mask.sum()),
            remaining_point_count=len(points_remaining),remaining_point_intersection_count=count,
            min_remaining_point_distance_m=min((d for d in remaining if d is not None),default=None),
            remaining_nearest_witnesses=witnesses,
            remaining_points_may_include_robot=True)
    return result
