"""Ray visibility of the measured pad gap; no contact or holding assumption."""
import numpy as np
from .rgbd_observation import RGBDObservation
from .rgbd_scene_provider import _frame_digest
from .visual_rim_grasp import rotation_xyzw
from .visual_robot_pixels import load_static_gripper_geometry


def inspect_box_visibility(frame,world_from_box,half_extents,*,depth_margin_m=.002):
    """Classify every intersecting in-image pixel-centre ray against an oriented box."""
    if type(frame) is not RGBDObservation:raise TypeError('RGBDObservation required')
    t=np.asarray(world_from_box,float);half=np.asarray(half_extents,float)
    if (t.shape!=(4,4) or half.shape!=(3,) or not np.isfinite(np.r_[t.ravel(),half]).all()
            or np.any(half<=0) or not np.allclose(t[3],[0,0,0,1])
            or not np.allclose(t[:3,:3].T@t[:3,:3],np.eye(3),atol=1e-8)
            or not np.isclose(np.linalg.det(t[:3,:3]),1)):raise ValueError('proper oriented box required')
    if not .0005<=depth_margin_m<=.005:raise ValueError('bounded depth margin required')
    camera_from_box=np.linalg.inv(frame.T_world_camera)@t
    corners=np.array([[x,y,z] for x in (-half[0],half[0]) for y in (-half[1],half[1]) for z in (-half[2],half[2])])
    corners_camera=corners@camera_from_box[:3,:3].T+camera_from_box[:3,3]
    result=dict(snapshot_id=f'{frame.episode_id}:step{frame.env_step}:{frame.camera_id}',
        frame_content_sha256=_frame_digest(frame).hex(),depth_margin_m=depth_margin_m,
        execution_allowed=False,holding_verified=False,initial_atoms=[],sampling='every_intersecting_pixel_centre_ray')
    if np.any(corners_camera[:,2]<=0):return dict(result,status='unknown',reason='box_crosses_camera_plane')
    projected=corners_camera@frame.K.T;uv=projected[:,:2]/projected[:,2:3]
    h,w=frame.depth_m.shape
    inside_image=bool(np.all(uv>=0) and np.all(uv[:,0]<w) and np.all(uv[:,1]<h))
    lo=np.maximum(np.floor(uv.min(0)).astype(int),[0,0]);hi=np.minimum(np.ceil(uv.max(0)).astype(int),[w-1,h-1])
    if np.any(lo>hi):return dict(result,status='unknown',reason='box_outside_image')
    cols,rows=np.meshgrid(np.arange(lo[0],hi[0]+1),np.arange(lo[1],hi[1]+1))
    rows=rows.ravel();cols=cols.ravel()
    rays=np.linalg.solve(frame.K,np.stack([cols+.5,rows+.5,np.ones(len(rows))])).T
    box_from_camera=np.linalg.inv(camera_from_box)
    origin=box_from_camera[:3,3];directions=rays@box_from_camera[:3,:3].T
    near=np.full(len(rows),-np.inf);far=np.full(len(rows),np.inf);parallel_outside=np.zeros(len(rows),bool)
    for axis in range(3):
        parallel=np.abs(directions[:,axis])<1e-12
        parallel_outside|=parallel & (abs(origin[axis])>half[axis])
        a=np.full(len(rows),-np.inf);b=np.full(len(rows),np.inf)
        nonparallel=~parallel
        first=(-half[axis]-origin[axis])/directions[nonparallel,axis]
        second=(half[axis]-origin[axis])/directions[nonparallel,axis]
        a[nonparallel]=np.minimum(first,second);b[nonparallel]=np.maximum(first,second)
        near=np.maximum(near,a);far=np.minimum(far,b)
    hit=(far>=np.maximum(near,0)) & ~parallel_outside
    rows=rows[hit];cols=cols[hit];near=near[hit];far=far[hit]
    observed=frame.depth_m[rows,cols];valid=frame.depth_valid[rows,cols]
    free=valid & (observed>far+depth_margin_m)
    foreground=valid & (observed<near-depth_margin_m)
    occupied=valid & ~free & ~foreground
    enough=len(rows)>=16
    status='resolved_box_observed_free' if inside_image and enough and np.all(free) else 'unknown'
    return dict(result,status=status,complete_box_in_image=inside_image,ray_count=len(rows),
        free_ray_count=int(free.sum()),foreground_occluded_ray_count=int(foreground.sum()),
        occupied_or_boundary_ray_count=int(occupied.sum()),invalid_depth_ray_count=int((~valid).sum()),
        reason=None if status!='unknown' else 'incomplete_or_nonfree_depth_coverage',
        subpixel_geometry_verified=False,transparent_geometry_verified=False)


def inspect_hand_aperture(frame,model_dir):
    geometry=load_static_gripper_geometry(frame,model_dir,geometry_mode='collision')
    rotation=rotation_xyzw(frame.robot_state['robot0_eef_quat'])
    hand_origin=np.asarray(frame.robot_state['robot0_eef_pos'])-rotation@np.array([0,0,.097])
    pads=[]
    for name in ('finger1_pad_collision','finger2_pad_collision'):
        part=next(p for p in geometry.parts if p['name']==name)
        points=(part['triangles_world_m'].reshape(-1,3)-hand_origin)@rotation
        pads.append((points.min(0),points.max(0)))
    right,left=sorted(pads,key=lambda bounds:bounds[0][1])
    lower=np.maximum(right[0],left[0]);upper=np.minimum(right[1],left[1])
    # Inner pad faces bound Y; X/Z are their shared gripping face extent.
    lower[1]=right[1][1]+.001;upper[1]=left[0][1]-.001
    q=np.asarray(frame.robot_state['robot0_gripper_qpos'])
    if np.any(upper<=lower):return dict(status='unknown',reason='no_open_pad_gap',initial_atoms=[],holding_verified=False,execution_allowed=False)
    centre=(lower+upper)/2;half=(upper-lower)/2
    world_from_box=np.eye(4);world_from_box[:3,:3]=rotation;world_from_box[:3,3]=hand_origin+rotation@centre
    report=inspect_box_visibility(frame,world_from_box,half)
    return dict(report,source='static_pad_gap_and_current_rgbd',pad_gap_half_extents_m=half.tolist(),
        pad_gap_world_from_box=world_from_box.tolist(),gripper_measured_open=bool(q[0]>=.035 and q[1]<=-.035),
        model_source_sha256=geometry.report['model_source_sha256'],hand_state='unknown',
        limitations=['pad gap covers gripping faces, not all possible object attachments',
                    'a free visible gap alone does not prove HandEmpty or a successful release'])


def infer_open_pad_handempty(frame,model_dir):
    """A planning inference under the explicit nonadhesive parallel-pad pinch model.

    Coverage confidence is a measured ray fraction, not a calibrated probability
    of physical HandEmpty. Execution admission must retain that distinction.
    """
    evidence=inspect_hand_aperture(frame,model_dir)
    result=dict(source='rgbd_open_visible_pad_gap_inference',evidence=evidence,
        assumptions=['rigid_nonadhesive_objects','holding_requires_opposed_pad_pinch',
            'objects_resolvable_by_current_depth_sensor','static_pad_pose_error_within_depth_margin'],
        confidence_definition='valid_free_pixel_ray_fraction_not_physical_probability',
        holding_verified=False,release_verified=False,execution_allowed=False,initial_atoms=[])
    if evidence.get('status')!='resolved_box_observed_free' or evidence.get('gripper_measured_open') is not True:
        return dict(result,status='unknown',reason='open_visible_pad_gap_not_observed')
    atom=dict(predicate='handempty',args=[],source=result['source'],
        snapshot_id=evidence['snapshot_id'],frame_content_sha256=evidence['frame_content_sha256'],
        confidence=evidence['free_ray_count']/evidence['ray_count'],
        confidence_definition=result['confidence_definition'],assumptions=result['assumptions'])
    return dict(result,status='handempty_inferred_under_pad_model',reason=None,initial_atoms=[atom])
