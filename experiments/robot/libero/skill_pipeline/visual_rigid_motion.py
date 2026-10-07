"""Robust local RGB-D correspondence motion, without a holding verdict."""
from itertools import combinations
import numpy as np


def rigid_fit(source, target):
    source, target = np.asarray(source, float), np.asarray(target, float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3 or len(source) < 3:
        raise ValueError('at least three paired 3D points required')
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError('finite points required')
    a, b = source.mean(axis=0), target.mean(axis=0)
    if np.linalg.svd(source-a, compute_uv=False)[1] < .001:
        raise ValueError('spatially spread noncollinear points required')
    u, _, vt = np.linalg.svd((source-a).T @ (target-b))
    correction = np.eye(3); correction[2,2] = np.linalg.det(vt.T @ u.T)
    rotation = vt.T @ correction @ u.T
    translation = b-rotation @ a
    return rotation, translation


def robust_motion(source, target, tolerance_m=.003):
    source, target = np.asarray(source,float), np.asarray(target,float)
    if source.shape != target.shape or source.ndim != 2 or source.shape[1] != 3:
        raise ValueError('paired Nx3 arrays required')
    if not np.isfinite(source).all() or not np.isfinite(target).all():
        raise ValueError('finite points required')
    if len(source) < 6:
        return dict(accepted=False, reason='fewer_than_six_correspondences')
    best = None
    for iteration, ids in enumerate(combinations(range(len(source)),3)):
        if iteration >= 2000: break
        try: r,t=rigid_fit(source[list(ids)],target[list(ids)])
        except ValueError: continue
        residual=np.linalg.norm(source @ r.T+t-target,axis=1)
        mask=residual<=tolerance_m
        score=(int(mask.sum()),-float(np.median(residual[mask])) if mask.any() else -np.inf)
        if best is None or score>best[0]:best=(score,mask)
    if best is None or best[0][0]<max(6,int(np.ceil(.6*len(source)))):
        return dict(accepted=False,reason='no_spatially_coherent_consensus')
    ids=np.flatnonzero(best[1]); train=ids[::2]; holdout=ids[1::2]
    try: r,t=rigid_fit(source[train],target[train])
    except ValueError:return dict(accepted=False,reason='degenerate_training_points')
    held=np.linalg.norm(source[holdout] @ r.T+t-target[holdout],axis=1)
    if np.max(held)>tolerance_m:
        return dict(accepted=False,reason='heldout_residual_too_large',heldout_max_residual_m=float(held.max()))
    r,t=rigid_fit(source[ids],target[ids]);residual=np.linalg.norm(source @ r.T+t-target,axis=1)
    if np.max(residual[ids])>tolerance_m:
        return dict(accepted=False,reason='refitted_consensus_exceeds_tolerance')
    centroid=source[ids].mean(axis=0)
    return dict(accepted=True,inlier_indices=ids.tolist(),rotation_matrix=r.tolist(),
                rotation_deg=float(np.degrees(np.arccos(np.clip((np.trace(r)-1)/2,-1,1)))),
                translation_at_world_origin_m=t.tolist(),source_centroid_m=centroid.tolist(),
                centroid_displacement_m=(r @ centroid+t-centroid).tolist(),
                median_residual_m=float(np.median(residual[ids])),heldout_max_residual_m=float(held.max()),
                holding_verified=False)
