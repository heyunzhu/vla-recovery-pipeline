"""Associate depth samples with verified static robot surfaces in 3D."""
from dataclasses import replace
import numpy as np
from scipy.spatial import cKDTree
from .rgbd_observation import unproject_world
from .visual_arm_pixels import load_arm_visual_model
from .visual_arm_path import arm_parts_at_joints
from .visual_robot_frames import infer_world_from_base
from .visual_robot_pixels import load_static_gripper_geometry, _owned


def sampled_triangle_surfaces(triangles, spacing_m=.003):
    triangles=np.asarray(triangles,float)
    edges=np.stack([triangles[:,1]-triangles[:,0],triangles[:,2]-triangles[:,0],
                    triangles[:,2]-triangles[:,1]],axis=1)
    subdivisions=np.maximum(1,np.ceil(np.linalg.norm(edges,axis=2).max(1)/spacing_m).astype(int))
    if subdivisions.max()>150:raise ValueError('unexpected static robot triangle size')
    batches=[]
    for n in np.unique(subdivisions):
        uv=np.array([(i/n,j/n) for i in range(n+1) for j in range(n+1-i)])
        t=triangles[subdivisions==n]
        samples=t[:,None,0]+uv[None,:,0,None]*(t[:,None,1]-t[:,None,0])+uv[None,:,1,None]*(t[:,None,2]-t[:,None,0])
        batches.append(samples.reshape(-1,3))
    return np.concatenate(batches)


def augment_robot_surface_ownership(frame, robot_pixels, model_dir):
    model=load_arm_visual_model(model_dir)
    parts=arm_parts_at_joints(model,frame.robot_state['robot0_joint_pos'],
                             infer_world_from_base(frame),geometry_mode='visual')
    gripper=load_static_gripper_geometry(frame,model_dir,geometry_mode='visual')
    triangles=np.concatenate([p['triangles_world_m'] for p in parts+list(gripper.parts)])
    samples=sampled_triangle_surfaces(triangles)
    points=unproject_world(frame)
    distance,_=cKDTree(samples).query(points,k=1)
    close=np.zeros(frame.depth_m.shape,bool);close[frame.depth_valid]=distance<=.005
    mask=robot_pixels.mask|close
    report=dict(robot_pixels.report,source='static_robot_raster_and_3d_surface_ownership',
        original_raster_matched_pixels=int(robot_pixels.mask.sum()),matched_pixel_count=int(mask.sum()),
        additional_surface_owned_pixels=int((close & ~robot_pixels.mask).sum()),
        surface_sample_spacing_m=.003,surface_sample_count=len(samples),
        maximum_sample_distance_m=.005,complete_robot_mask=False,
        boundary_and_occlusion_uncertainty='unmatched_depth_samples_retained')
    return replace(robot_pixels,mask=_owned(mask),report=report)
