"""Native cuTAMP world from explicit RGB-D proxies; no MuJoCo geometry branch."""
import numpy as np


def build_visual_world(problem):
    from curobo.geom.types import Cuboid
    from cutamp.envs import TAMPEnvironment
    from cutamp.tamp_domain import all_tamp_fluents
    snapshot=problem.q_init_debug.get('rgbd_snapshot_id')
    if not snapshot or problem.q_init_debug.get('scene_source')!='rgbd':raise ValueError('RGB-D problem provenance required')
    objects=problem.movables+problem.surfaces+problem.statics
    if not problem.movables or not problem.surfaces:raise ValueError('visible movable and goal surface required')
    names=[o.name for o in objects]
    if len(set(names))!=len(names):raise ValueError('duplicate visual object ID')
    converted={};debug=[]
    for obj in objects:
        geometry=obj.geometry
        allowed_keys={'source','snapshot_id','coordinate_frame','half_extents','observed_point_count',
            'category','hidden_geometry','origin_semantics'}
        if set(geometry)-allowed_keys or geometry.get('hidden_geometry')!='unknown':raise ValueError('unapproved visual geometry metadata')
        if (geometry.get('source') not in ('rgbd_visible_aabb_proxy','rgbd_observed_voxel','rgbd_observed_point_bounds')
                or geometry.get('snapshot_id')!=snapshot or geometry.get('coordinate_frame')!='robot_base'
                or obj.mesh_path is not None):raise ValueError('nonvisual geometry is forbidden in visual cuTAMP world')
        # No min-dimension clamps, hidden parts, inferred names, default table or collision exclusions.
        half=np.asarray(obj.half_extents,float);pos=np.asarray(obj.pos,float);quat=np.asarray(obj.quat,float)
        if (half.shape!=(3,) or pos.shape!=(3,) or quat.shape!=(4,) or not np.isfinite(np.r_[half,pos,quat]).all()
                or np.any(half<=0) or not np.isclose(np.linalg.norm(quat),1,atol=1e-8)
                or not np.array_equal(half,np.asarray(geometry.get('half_extents'),float))):raise ValueError('invalid explicit visual cuboid')
        prefix='obj_' if obj.name.startswith('obj_') else 'rgbd_voxel_'
        if not obj.name.startswith(prefix) or not obj.name[len(prefix):].isdigit():raise ValueError('visual ID namespace required')
        converted[obj.name]=Cuboid(name=obj.name,dims=(2*half).tolist(),pose=[*pos.tolist(),*quat.tolist()],color=[180,180,180])
        debug.append(dict(name=obj.name,source=geometry['source'],collision_representation='explicit_rgbd_cuboid',
            dims=(2*half).tolist(),pose=[*pos.tolist(),*quat.tolist()],hidden_geometry='unknown'))
    fluents={f.name.lower():f for f in all_tamp_fluents};goals=set()
    movable_names={o.name for o in problem.movables};surface_names={o.name for o in problem.surfaces}
    for atom in problem.goal_atoms:
        if atom.predicate!='on' or len(atom.args)!=2 or atom.args[0] not in movable_names or atom.args[1] not in surface_names:
            raise ValueError('unsupported visual recovery goal')
        goals.add(fluents['on'].ground(*atom.args))
    if not goals:raise ValueError('visual goal required')
    movables=[converted[o.name] for o in problem.movables];surfaces=[converted[o.name] for o in problem.surfaces]
    # Goal surfaces remain collision obstacles. Contact exceptions require explicit later constraints.
    statics=[converted[o.name] for o in problem.surfaces+problem.statics]
    env=TAMPEnvironment(name='rgbd_cutamp_adapter',movables=movables,statics=statics,
        type_to_objects={'Movable':movables,'Surface':surfaces},goal_state=frozenset(goals))
    return env,{name:name for name in names},[],dict(source='rgbd',objects=debug,
        default_table_added=False,default_dummy_added=False,goal_surface_collision_excluded=False,unknown_space='unverified')
