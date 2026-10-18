"""Check a measured upright target against a stationary RGB-D bowl support.

This is an observation-based geometric check, not proof of physical contact.
The caller supplies current tracked target poses and the measured bowl model.
"""
import numpy as np


def check_rgbd_bowl_placement(scene, target_name, goal_name, support_model):
    target = scene.objects.get(target_name)
    if target is None or goal_name not in scene.objects:
        return dict(ok=False, reason='missing_visual_target_or_support', details={})
    position = np.asarray(target.pos, dtype=float)
    center = np.asarray(support_model['center_xy_world_m'], dtype=float)
    model=target.geometry['model']
    if 'support_footprint_world_m' in model:
        footprint=np.asarray(model['support_footprint_world_m'],float)
        q=np.asarray(scene.gripper_qpos,float)
        opened=bool(q.shape==(2,) and np.isfinite(q).all() and q[0]>=.035 and q[1]<=-.035)
        finite=bool(footprint.shape==(24,3) and np.isfinite(footprint).all())
        inside=bool(finite and np.all(np.linalg.norm(footprint[:,:2]-center,axis=1)<=support_model['support_radius_m']))
        errors=footprint[:,2]-support_model['support_z_world_m']
        supported=bool(finite and np.max(np.abs(errors))<=.01)
        return dict(ok=inside and supported and opened,
            reason='rgbd_transformed_base_footprint_support_and_open_fingers',details=dict(
                footprint_inside=inside,supported_height=supported,gripper_open=opened,
                bottom_height_range_m=[float(footprint[:,2].min()),float(footprint[:,2].max())],
                evidence='current_RGBD_SE3_pose; initial_measured_base_shape; stationary_support'))
    # The visual scene's target position denotes the measured bottle bottom.
    # Its current fitted model is attached by the visual executor hook.
    radius = float(target.geometry['model']['body_radius_m'])
    support_radius = float(support_model['support_radius_m'])
    xy = float(np.linalg.norm(position[:2]-center))
    z_error = float(position[2]-support_model['support_z_world_m'])
    finite = bool(np.all(np.isfinite(position)) and np.isfinite(radius) and
                  np.isfinite(support_radius) and np.isfinite(z_error))
    footprint_inside = finite and radius > 0 and xy+radius <= support_radius
    supported_height = finite and abs(z_error) <= .01
    ok = bool(footprint_inside and supported_height and scene.gripper_open)
    return dict(ok=ok, reason='rgbd_bowl_footprint_support_and_released', details=dict(
        xy_distance_m=xy, target_body_radius_m=radius, support_radius_m=support_radius,
        footprint_inside=bool(footprint_inside), bottom_support_error_m=z_error,
        height_tolerance_m=.01, supported_height=bool(supported_height),
        gripper_open=bool(scene.gripper_open),
        evidence='current_RGBD_target_bottom_and_initial_stationary_RGBD_support'))
