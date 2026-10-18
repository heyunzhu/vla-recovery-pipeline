"""Bind the saved rack skill's region adapter to an observed region, not a simulator site."""
from types import SimpleNamespace
import copy
import numpy as np


def observed_top_region_site(plane):
    basis=np.asarray(plane['basis_world'],dtype=float)
    origin=np.asarray(plane['origin_world_m'],dtype=float)
    bounds=np.asarray(plane['uv_bounds_m'],dtype=float)
    corners=np.array([origin+basis[:,0]*u+basis[:,1]*v
                      for u in bounds[:,0] for v in bounds[:,1]])
    return dict(name='rgbd_observed_top_region',pos=corners.mean(axis=0).tolist(),
                corners_world_m=corners.tolist(),source='current_RGBD_upper_plane')


def resolve_observed_skill_surface(resolver,region_hint,plane,world_from_base,goal_name):
    site=observed_top_region_site(plane)
    transform=np.linalg.inv(np.asarray(world_from_base,dtype=float))
    corners=np.asarray(site['corners_world_m'])@transform[:3,:3].T+transform[:3,3]
    center=corners.mean(axis=0)
    half=(corners[:,:2].max(axis=0)-corners[:,:2].min(axis=0))/2
    measured=dict(name=site['name'],site_id=-1,pos=center.tolist(),
                  size=[*half.tolist(),0.0],quat=[1.,0.,0.,0.],source=site['source'])
    source=SimpleNamespace(name=goal_name,pos=center,geometry={'sites':[measured]})
    hint=copy.deepcopy(region_hint)
    hint.update(surface_name=goal_name,region_name=goal_name,source_object=goal_name,
                source_site_name=measured['name'])
    descriptor=resolver(hint['geometry_profile'],surface_name=goal_name,
                        scene=SimpleNamespace(objects={goal_name:source}),task=None,
                        table_geometry={},hint=hint,hint_key='placement_region')
    if descriptor is None:raise ValueError('saved rack skill did not resolve observed top region')
    descriptor=copy.deepcopy(descriptor)
    descriptor['source']='rgbd_observed_region_via_saved_skill'
    descriptor.setdefault('metadata',{}).update(observed_plane=plane['id'],
        site_geometry_source='current_RGBD_upper_plane',oracle_object_state_used=False)
    return descriptor,dict(original_hint=region_hint,effective_hint=hint,
        observed_site_world=site,observed_site_base=measured,descriptor=descriptor,
        binding='saved geometry profile; simulator site replaced by current observed upper plane')
