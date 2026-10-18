"""Opt-in recovery hook for observed cuboids and measured rack release regions.

Simulation supplies sensors/robot proprioception only. No object assets, named
sites, truth poses, or historical geometry hints enter this hook.
"""
from pathlib import Path
import copy,json,os,runpy,sys
import numpy as np

RUN=Path(os.environ['ANCHOR_CAPTURE_DIR']).parent
CODE=Path(os.environ['ANCHOR_VISUAL_CODE'])
sys.path.append(str(CODE))
original=runpy.run_path(str(CODE/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py'))
ctx=original['read_scene'].__globals__
from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as controller
from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState
from experiments.robot.libero.tiptop_repro.task_parser import ParsedTask
from experiments.robot.libero.tiptop_repro import tamp_scene,real_cutamp_adapter
from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation,RGBDObservation,unproject_world
from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
from experiments.robot.libero.skill_pipeline.visual_observed_geometry import cuboid_geometry
from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base
from experiments.robot.libero.skill_pipeline.visual_inclined_support import observed_place_check
config=json.loads(Path(os.environ['ANCHOR_OBSERVED_PLACEMENT_CONFIG']).read_text())
plane=config['plane'];target_model=None;target_name='rgbd_cheese_obj_002';goal_name='rgbd_rack_obj_003'
target_category=config.get('target_category','cheese');goal_category=config.get('goal_category','rack')
if config.get('generic_task'):
    target_name='rgbd_'+target_category+'_obj_002';goal_name='rgbd_'+goal_category+'_obj_003'
scene_history=[]
parsed_task=None


def parse_task(language,object_names,env=None):
    global plane,target_model,parsed_task
    if parsed_task is not None:return parsed_task
    key=(id(env),env._anchor_control_steps)
    if key in ctx['visual_id_task_cache']:
        return ctx['visual_id_task_cache'][key]
    from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
    from experiments.robot.libero.skill_pipeline.robot_surface_ownership import augment_robot_surface_ownership
    from experiments.robot.libero.skill_pipeline.visual_anchor_obstacles import observed_anchor_obstacles
    frame=load_observation(RUN/'snapshots/recovery01/pre_solver_attempt01/agentview')
    from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import ResidentSegmentation
    from experiments.robot.libero.skill_pipeline.visual_observed_geometry import observed_points,fit_observed_cuboid
    from experiments.robot.libero.skill_pipeline.visual_inclined_support import canonical_box,support_candidates
    from experiments.robot.libero.skill_pipeline.rgbd_scene import VisualDetection
    from PIL import Image
    segmenter=ResidentSegmentation(config['vision'],RUN/'resident_vision')
    env._anchor_close_vision=segmenter.close
    masks,reply=segmenter(frame)
    detections=[VisualDetection(mask=m,category=c,raw_score=None,source='text_guided_segmentation')
        for m,c in zip(masks,reply['categories'])]
    def selected_mask(masks,reply,category):
        indices=[i for i,c in enumerate(reply['categories']) if c==category]
        if len(indices)!=1:raise ValueError('current visual '+category+' ambiguous or missing')
        return masks[indices[0]]
    if config.get('generic_task'):
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
        from experiments.robot.libero.skill_pipeline.visual_task_binding import bind_visual_pick_place,require_geometry_binding
        visual_scene=RGBDSceneProvider(lambda _:detections,detector_id='current_resident_DINO_SAM',camera_id=frame.camera_id).get_scene(frame)
        binding=bind_visual_pick_place(language,visual_scene)
        selected_target,selected_goal=require_geometry_binding(visual_scene,binding)
        from dataclasses import asdict
        (RUN/'visual_binding.json').write_text(json.dumps(asdict(binding),indent=2))
        if target_category==goal_category:raise ValueError('same-category target and support need a separate geometry adapter')
        mask=masks[selected_target.detection_index];goal_mask=masks[selected_goal.detection_index]
    else:
        mask=selected_mask(masks,reply,target_category);goal_mask=selected_mask(masks,reply,goal_category)
    target_points,_=observed_points(frame,mask,world_from_base=infer_world_from_base(frame))
    rack_points,_=observed_points(frame,goal_mask,world_from_base=infer_world_from_base(frame))
    wrist=load_observation(RUN/'snapshots/recovery01/pre_solver_attempt01/robot0_eye_in_hand')
    wdir=RUN/'initial_wrist';wdir.mkdir();Image.fromarray(wrist.rgb).save(wdir/'rgb.png')
    wr=segmenter.worker.request(dict(rgb=str(wdir/'rgb.png'),output=str(wdir/'masks.npz')))
    (wdir/'result.json').write_text(json.dumps(wr,indent=2));wm=np.load(wdir/'masks.npz')['masks']
    from scipy.spatial import cKDTree
    for category in [target_category,goal_category]:
        if wr['categories'].count(category)!=1:continue
        cloud,_=observed_points(wrist,selected_mask(wm,wr,category),world_from_base=infer_world_from_base(wrist))
        reference=target_points if category==target_category else rack_points
        if len(cloud) and np.mean(cKDTree(reference).query(cloud)[0]<.004)>=.2:
            if category==target_category:target_points=np.concatenate([target_points,cloud])
            else:rack_points=np.concatenate([rack_points,cloud])
    target_model=fit_observed_cuboid(target_points)
    (RUN/'current_target_model.json').write_text(json.dumps(target_model,indent=2))
    if not target_model['planning_allowed']:raise ValueError('current target geometry unresolved: '+str(target_model['reasons']))
    target_model=canonical_box(target_model)
    candidates=support_candidates(rack_points,target_model)
    (RUN/'current_target_model.json').write_text(json.dumps(target_model,indent=2))
    (RUN/'current_plane_candidates.json').write_text(json.dumps(candidates,indent=2))
    if not candidates:raise ValueError('no observed support candidate accommodates the target footprint')
    if config.get('rack_skill') or config.get('generic_task'):
        select=min if config.get('goal_relation')=='inside' else max
        plane=select(candidates,key=lambda p:p['centroid_height_world_m'])
    else:plane=next(p for p in candidates if p['id']==config['plane']['id'])
    world=np.full((*frame.depth_m.shape,3),np.nan);world[frame.depth_valid]=unproject_world(frame)
    model=target_model
    r=np.array(model['rotation_world_from_object']);center=np.array(model['center_world_m'])
    half=np.array(model['collision_half_extents_m'])
    from scipy.ndimage import binary_dilation
    boundary=binary_dilation(mask,iterations=2)
    ownership=np.all(np.abs((world-center)@r)<=half+.001,axis=-1)
    excluded=mask|(boundary&ownership&frame.depth_valid)
    if config.get('generic_task'):
        # Permit target support contact only at the measured selected plane;
        # keep observed container walls and other labeled geometry as obstacles.
        distance=world@np.asarray(plane['normal_world'])-plane['offset_world_m']
        excluded|=goal_mask&frame.depth_valid&(np.abs(distance)<.004)
    robotdir=Path(os.environ['ROOT'])/'logs/rgbd_bottle_geometry_recovery_20261009/static_panda_model'
    robot=project_static_arm_gripper(frame,robotdir,depth_tolerance_m=.005)
    robot=augment_robot_surface_ownership(frame,robot,robotdir)
    labeled=np.logical_or.reduce([d.mask for d in detections if d.category])
    baseline=observed_anchor_obstacles(frame,excluded,robot,labeled_mask=labeled)
    from experiments.robot.libero.skill_pipeline.visual_collision_policy import hard_obstacle_mask
    hard_labeled,contact_pixels,policy_report=hard_obstacle_mask(masks,reply['categories'],
        policy=config.get('collision_policy','strict'),goal_category=goal_category)
    obstacles=baseline if policy_report['policy']=='strict' else observed_anchor_obstacles(frame,excluded,robot,labeled_mask=hard_labeled)
    policy_report.update(baseline_obstacle_boxes=len(baseline['centres']),hard_obstacle_boxes=len(obstacles['centres']),
        baseline_obstacle_points=baseline['residual_point_count'],hard_obstacle_points=obstacles['residual_point_count'],
        placement_candidates_changed=False)
    (RUN/'collision_policy.json').write_text(json.dumps(policy_report,indent=2))
    (RUN/'strict_obstacles_before_policy.json').write_text(json.dumps(baseline,indent=2))
    np.savez_compressed(RUN/'collision_policy_masks.npz',hard_labeled=hard_labeled,contact_excluded=contact_pixels)
    obstacles['collision_policy']=policy_report
    ctx['obstacle_cache'].update(current=obstacles,target_name=target_name,goal_name=goal_name)
    (RUN/'observed_obstacles.json').write_text(json.dumps(obstacles,indent=2))
    scene=ctx['scene_cache'][id(env)]
    first=plane['release_candidates'][0];position=np.array(first['position_world_m'])
    top=float(position[2]-half[2])
    # Semantic sampling surrogate uses the observed envelope; the opt-in
    # release constraint below checks candidate pose proximity, not this box.
    basis=np.array(plane['basis_world']);origin=np.array(plane['origin_world_m'])
    bounds=np.array(plane['uv_bounds_m'])
    xy=np.array([origin+basis[:,0]*a+basis[:,1]*b for a in bounds[:,0] for b in bounds[:,1]])[:,:2]
    patch_center=(xy.min(0)+xy.max(0))/2;patch_half=(xy.max(0)-xy.min(0))/2
    goalgeom=dict(source='rgbd_observed_release_region',geoms=[dict(name='rgbd_release_sampling_patch',
        shape='box',type=6,size=[*patch_half.tolist(),.001],pos=[*patch_center.tolist(),top-.001],
        quat=[1,0,0,0],collision_active=True,contype=1,conaffinity=1)])
    if config.get('rack_skill') or config.get('generic_task'):
        # Executor clearance uses the whole observed rack, separately from the
        # skill's region descriptor. No named simulation site is queried.
        lower=rack_points.min(axis=0);upper=rack_points.max(axis=0)
        goalgeom=dict(source='rgbd_observed_rack_envelope',geoms=[dict(name='rgbd_rack_envelope',
            shape='box',type=6,size=((upper-lower)/2).tolist(),pos=((upper+lower)/2).tolist(),
            quat=[1,0,0,0],collision_active=True,contype=1,conaffinity=1)])
        if config.get('rack_skill'):
            from experiments.robot.libero.skill_pipeline.visual_rack_skill import resolve_observed_skill_surface
            hint=config['rack_skill']['params']['geometry_hints']['placement_region']
            adapter=tamp_scene._load_geometry_runtime_adapter(hint['geometry_profile_adapter_path'])
            descriptor,_=resolve_observed_skill_surface(adapter.resolve_surface_descriptor,hint,plane,np.eye(4),goal_name)
            goalgeom['metadata']=copy.deepcopy(descriptor['metadata'])
        else:
            lo=xy.min(0);hi=xy.max(0)
            goalgeom['metadata']=dict(inner_bounds=dict(x_min=float(lo[0]),x_max=float(hi[0]),
                y_min=float(lo[1]),y_max=float(hi[1]),support_z=top),
                observed_plane=plane['id'],goal_relation=config.get('goal_relation','on'))
        goalgeom['metadata']['coordinate_frame']='world'
        goalgeom['metadata']['inner_bounds_coordinate_frame']='world'
    scene.objects={target_name:ObjectState(target_name,center,np.array(model['quat_world_wxyz']),geometry=cuboid_geometry(model)),
        goal_name:ObjectState(goal_name,np.array([position[0],position[1],top-.001]),np.array([1.,0,0,0]),geometry=goalgeom)}
    install_executor(env,scene,frame,mask,segmenter)
    parsed_task=ParsedTask(language=language,target_hint=target_name,goal_hint=goal_name,operation='place',
        diagnostics=dict(bddl_init_atoms=[],target_source='visual_instance_id',goal_source='visual_instance_id',
            bddl_target=target_name,bddl_goal=goal_name,
            bddl_goal_atoms=[dict(predicate='on',args=[target_name,goal_name])],bddl_goal_surfaces=[goal_name],
            geometry_source='RGBD_cuboid_observed_planes_and_labeled_depth',
            selected_plane=plane['id'],oracle_object_state_used=False,
            release_strategy='upright_hover_release; gravity_settling; not_6DOF_plane_alignment'))
    return parsed_task


ctx['parse_task']=parse_task
controller.parse_task=parse_task
original_build=controller.build_tamp_problem


def build(*args,**kwargs):
    problem=original_build(*args,**kwargs)
    if config.get('rack_skill'):
        from experiments.robot.libero.skill_pipeline.visual_rack_skill import resolve_observed_skill_surface
        hint=config['rack_skill']['params']['geometry_hints']['placement_region']
        adapter=tamp_scene._load_geometry_runtime_adapter(hint['geometry_profile_adapter_path'])
        descriptor,audit=resolve_observed_skill_surface(adapter.resolve_surface_descriptor,hint,plane,
            ctx['obstacle_cache']['world_from_base'],goal_name)
        audit['hint_sources']=config['rack_skill']['params'].get('hint_sources',[])
        (RUN/'rack_skill_binding.json').write_text(json.dumps(audit,indent=2))
        problem.surfaces=[tamp_scene._virtual_surface_from_descriptor(goal_name,descriptor)
                          if obj.name==goal_name else obj for obj in problem.surfaces]
        bounds=descriptor['inner_bounds'];metadata=descriptor['metadata']
        problem.place_candidates[goal_name]=tamp_scene._inner_floor_place_candidates(
            bounds['x_min'],bounds['x_max'],bounds['y_min'],bounds['y_max'],
            bounds['support_z']+metadata['place_z_offset_m'],metadata)
        return problem
    t=np.linalg.inv(ctx['obstacle_cache']['world_from_base'])
    candidates=[]
    for row in plane['release_candidates']:
        pos=t[:3,:3]@np.array(row['position_world_m'])+t[:3,3]
        # Only a tiny calibration yaw is removed; the current planner has
        # XYZ+yaw placements. There is no claim of normal-aligned rotation.
        yaw=row['yaw_rad']-np.arctan2(ctx['obstacle_cache']['world_from_base'][1,0],ctx['obstacle_cache']['world_from_base'][0,0])
        candidates.append([*pos.tolist(),float(yaw)])
    for obj in problem.surfaces:
        if obj.name==goal_name:
            obj.geometry['source']='rgbd_observed_release_region'
            obj.geometry.setdefault('metadata',{})['rgbd_release_candidates']=candidates
            obj.geometry['metadata']['visual_collision_policy']=config.get('collision_policy','strict')
            if config.get('release_pose_constraint',False):
                obj.geometry['metadata']['rgbd_release_constraint']='candidate_pose_v1'
                # This box expresses a release domain, not observed solid material.
                # The backend's existing placement-region semantics exclude it
                # from hard collisions while preserving placement constraints.
                affordances=obj.geometry['metadata'].setdefault('affordances',[])
                if 'placement_region' not in affordances:
                    affordances.append('placement_region')
    (RUN/'measured_release_candidates_base.json').write_text(json.dumps(candidates,indent=2))
    return problem


controller.build_tamp_problem=build
real_cutamp_adapter.build_tamp_problem=build


def install_executor(env,initial_scene,frame,mask,segmenter):
    from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import FramewiseRGBDTracker,ResidentSegmentation,transform
    from anchor_sensor.libero_rgbd_sensor import capture_libero_rgbd
    from experiments.robot.libero.tiptop_repro import libero_tiptop_executor,optimized_executor,executor
    active_current=[None]
    def wrist_observation(primary):
        raw=capture_libero_rgbd(env,active_current[0],episode_id=os.environ['ANCHOR_EPISODE_ID'],
            env_step=primary.env_step,camera_id='robot0_eye_in_hand')
        return RGBDObservation(**raw.__dict__)
    tracker=FramewiseRGBDTracker(frame,mask,target_model,segmenter,category=target_category,output_dir=RUN/'framewise_tracking',
        occlusion_aware=config.get('occlusion_aware_tracking',False),
        fallback_frame_provider=wrist_observation if config.get('wrist_fallback',False) else None,
        **config.get('tracking_short_gap',{}))
    template=copy.deepcopy(initial_scene)
    if config.get('rack_skill') or config.get('generic_task'):
        # Legacy geometry estimation rebuilds metadata from geoms. Keep the
        # skill opening explicit, rather than silently falling back to the
        # whole-rack AABB as a placement opening.
        original_opening_bounds=libero_tiptop_executor._opening_bounds
        def skill_opening_bounds(scene,surface_name):
            if surface_name!=goal_name:return original_opening_bounds(scene,surface_name)
            metadata=scene.objects[goal_name].geometry['metadata']
            bounds=metadata['inner_bounds']
            source='rgbd_saved_skill_inner_bounds' if config.get('rack_skill') else 'rgbd_measured_support_inner_bounds'
            return dict(bounds,source=source,coordinate_frame='world')
        libero_tiptop_executor._opening_bounds=skill_opening_bounds
    original_goal_check=optimized_executor._scene_on_or_inside
    def read_scene(env,current):
        active_current[0]=current
        raw=capture_libero_rgbd(env,current,episode_id=os.environ['ANCHOR_EPISODE_ID'],env_step=env._anchor_control_steps,camera_id='agentview')
        observed=RGBDObservation(**raw.__dict__)
        model,report=tracker.update(observed)
        state=copy.deepcopy(template)
        state.ee_pos=np.array(current['robot0_eef_pos']);state.ee_quat=np.array(current['robot0_eef_quat'])
        state.gripper_qpos=np.array(current['robot0_gripper_qpos']);state.robot_qpos=np.array(current['robot0_joint_pos'])
        state.robot_joint_debug=ctx['proprio_frame_debug'](observed)
        state.holding_evidence=dict(status='unknown',object_name=None,source='proprioception_and_observed_pose')
        obj=state.objects[target_name];obj.pos=np.array(model['center_world_m']);obj.quat=np.array(model['quat_world_wxyz'])
        obj.geometry['model']=model
        pose=np.array(model.get('T_world_from_initial',np.eye(4)))
        from scipy.spatial.transform import Rotation
        for geom in obj.geometry['geoms']:
            geom['pos']=transform(np.array(geom['pos'])[None],pose)[0].tolist()
            q=geom['quat'];rot=Rotation.from_matrix(pose[:3,:3])*Rotation.from_quat([*q[1:],q[0]])
            q=rot.as_quat();geom['quat']=np.r_[q[3],q[:3]].tolist()
        if report.get('status')=='predicted':scene_history.clear()
        elif not scene_history or scene_history[-1][0]!=observed.env_step:
            scene_history.append((observed.env_step,obj.pos.copy()))
        (RUN/'current_visual_state.json').write_text(json.dumps(dict(env_step=observed.env_step,
            center_world_m=obj.pos.tolist(),quat_world_wxyz=obj.quat.tolist(),
            corners_world_m=model['corners_world_m'],gripper_qpos=state.gripper_qpos.tolist(),
            tracking_status=report.get('status'),tracking_observed=model.get('tracking_observed',True)),indent=2))
        return state
    def goal_check(scene,obj_name,surface_name):
        if obj_name!=target_name or surface_name!=goal_name:
            return original_goal_check(scene,obj_name,surface_name)
        obj=scene.objects[obj_name]
        if not obj.geometry['model'].get('tracking_observed',True):
            return optimized_executor.GoalSatisfactionResult(False,'short_gap_pose_is_not_visual_goal_evidence',{})
        result=observed_place_check(obj.geometry['model']['corners_world_m'],plane,scene.gripper_qpos,
            [p for _,p in scene_history])
        if config.get('visual_goal_diagnostic_only'):
            return optimized_executor.GoalSatisfactionResult(False,'visual_goal_diagnostic_only',result)
        return optimized_executor.GoalSatisfactionResult(**result)
    optimized_executor._scene_on_or_inside=goal_check
    original_object_z=libero_tiptop_executor._object_world_z
    def measured_object_z(scene,obj_name):
        obj=scene.objects.get(obj_name)
        if obj is not None and not obj.geometry.get('model',{}).get('tracking_observed',True):return None
        return original_object_z(scene,obj_name)
    libero_tiptop_executor._object_world_z=measured_object_z
    for module in [libero_tiptop_executor,optimized_executor,executor,controller]:module.read_scene=read_scene
    env._anchor_framewise_observe=lambda current:read_scene(env,current)
    env._anchor_close_vision=segmenter.close
