"""Signed distances to explicit observed cuboids, without simulator geometry."""
import numpy as np


def cuboid_point_signed_distance(points,centre,half_extents):
    points=np.asarray(points,float);centre=np.asarray(centre,float);half=np.asarray(half_extents,float)
    if (points.ndim!=2 or points.shape[1]!=3 or centre.shape!=(3,) or half.shape!=(3,)
            or not np.isfinite(np.r_[points.ravel(),centre,half]).all() or np.any(half<=0)):
        raise ValueError('finite xyz and positive cuboid extents required')
    delta=np.abs(points-centre)-half
    return np.linalg.norm(np.maximum(delta,0),axis=1)+np.minimum(np.max(delta,axis=1),0)


def sphere_cuboid_penetrations(spheres,centre,half_extents):
    spheres=np.asarray(spheres,float)
    if spheres.ndim!=2 or spheres.shape[1]!=4 or not np.isfinite(spheres).all() or np.any(spheres[:,3]<=0):
        raise ValueError('finite positive-radius spheres required')
    return np.maximum(spheres[:,3]-cuboid_point_signed_distance(spheres[:,:3],centre,half_extents),0)


def inspect_proxy_overlaps(problem,target_points_base):
    points=np.asarray(target_points_base,float)
    movable=problem.movables[0];centre=np.asarray(movable.pos);half=np.asarray(movable.half_extents)
    rows=[]
    for obj in problem.surfaces+problem.statics:
        if not np.array_equal(obj.quat,[1,0,0,0]):raise ValueError('axis-aligned visual proxies required')
        overlap=half+np.asarray(obj.half_extents)-np.abs(centre-np.asarray(obj.pos))
        if np.all(overlap>0):
            distances=cuboid_point_signed_distance(points,obj.pos,obj.half_extents)
            rows.append(dict(name=obj.name,source=obj.geometry['source'],aabb_overlap_axes_m=overlap.tolist(),
                target_visible_points_inside_proxy=int(np.sum(distances<0)),
                target_visible_points_within_5mm=int(np.sum(distances<.005)),
                min_target_visible_signed_distance_m=float(distances.min())))
    return dict(target=movable.name,aabb_overlap_count=len(rows),overlaps=rows,
        actual_contact_verified=False,execution_allowed=False)
