"""Anchor-only staged migration from oracle state to RGB-D recovery.

Nomination receives only sensor frames. By default this diagnostic associates
visual IDs to oracle bodies; geometry, obstacles and execution have separate
replacement switches. ANCHOR_VISUAL_IDS additionally removes body association
and uses static robot FK with proprioception. All switches must be enabled for
the full visual anchor; its replay also hides simulator reward/done. This
controlled bottle/plate case does not establish general benchmark readiness.
"""
from pathlib import Path
import json
import os
import subprocess

import numpy as np
from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as controller
from experiments.robot.libero.tiptop_repro.task_parser import ParsedTask

RUN = Path(os.environ["ANCHOR_CAPTURE_DIR"]).parent
ROOT = Path(os.environ["ROOT"])
CODE = Path(os.environ["ANCHOR_VISUAL_CODE"])
original_read_scene = controller.read_scene
original_parse_task = controller.parse_task
scene_cache = {}
obstacle_cache = {}
visual_id_task_cache = {}


def read_scene(env, obs):
    if os.environ.get('ANCHOR_VISUAL_IDS') == '1':
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        cache_robot_steps(env)
        frame=load_observation(RUN/'snapshots/recovery01/pre_solver_attempt01/agentview')
        if frame.env_step != env._anchor_control_steps:
            raise RuntimeError('anchor visual ID scene requires a current nomination snapshot')
        scene=robot_only_scene(obs,frame)
        from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base
        obstacle_cache['world_from_base']=infer_world_from_base(frame)
        scene_cache[id(env)]=scene
        audit=json.loads((RUN/'snapshots/recovery01/pre_solver_attempt01/capture_audit.json').read_text())
        parsed=parse_task(audit['language'],[],env=env)
        visual_id_task_cache[(id(env),env._anchor_control_steps)]=parsed
        return scene
    scene = original_read_scene(env, obs)
    if os.environ.get('ANCHOR_PROPRIO_HAND_STATE') == '1':
        import runpy
        infer_panda_hand_state = runpy.run_path(str(CODE / 'experiments/robot/libero/skill_pipeline/proprio_hand_state.py'))['infer_panda_hand_state']
        report = infer_panda_hand_state(obs, snapshot_id=f'step{env._anchor_control_steps}')
        scene.contacts = []
        scene.holding_evidence = dict(report, object_name=None, candidates=[])
        (RUN / f'proprio_hand_state_step{env._anchor_control_steps}.json').write_text(json.dumps(report, indent=2))
        if not report['initial_atoms']:
            raise RuntimeError('anchor initial hand state unresolved by proprioception')
    scene_cache[id(env)] = scene
    return scene


def parse_task(language, object_names, env=None):
    cache_key=(id(env),env._anchor_control_steps) if env is not None else None
    if os.environ.get('ANCHOR_VISUAL_IDS') == '1' and cache_key in visual_id_task_cache:
        return visual_id_task_cache[cache_key]
    if env is None or id(env) not in scene_cache:
        raise RuntimeError("hybrid association requires the current oracle scene")
    step = env._anchor_control_steps
    out = RUN / f"visual_nomination_step{step}"
    assets = ROOT / "logs/rgbd_exact_box_20261008/models"
    process_env = dict(os.environ)
    process_env["PYTHONPATH"] = str(ROOT / "logs/rgbd_exact_box_20261008/pydeps") + ":" + str(CODE)
    process_env.update(HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    command = [str(ROOT / "envs/tiptop-planning-py310/bin/python"),
        str(CODE / "scripts/recovery/skill_pipeline/inspect_recovery_rgbd_capture.py"),
        str(RUN / "snapshots"), "--out-dir", str(out), "--camera", "agentview",
        "--phase", "pre_solver_attempt01", "--device", "cpu", "--text-threshold", "0.35",
        "--grounding-model-dir", str(assets / "grounding-dino-tiny"),
        "--sam2-model-dir", str(assets / "sam2.1-hiera-tiny"),
        "--distractor-prompts-json", str(RUN / "distractor_prompts.json")]
    if os.environ.get("ANCHOR_REPLACE_BOTTLE_GEOMETRY") == "1":
        command.append("--fit-target-bottle")
    if os.environ.get("ANCHOR_REPLACE_PLATE_GEOMETRY") == "1":
        command.append("--fit-goal-plate")
    if os.environ.get('ANCHOR_RGBD_OBSTACLES') == '1':
        command.extend(['--obstacle-robot-model-dir', str(ROOT / 'logs/rgbd_bottle_geometry_recovery_20261009/static_panda_model')])
    with (RUN / f"visual_nomination_step{step}.log").open("wb") as log:
        subprocess.run(command, env=process_env, stdout=log, stderr=subprocess.STDOUT,
                       timeout=300, check=True)
    candidates = list(out.glob("recovery*/pre_solver_attempt01/agentview"))
    if len(candidates) != 1:
        raise RuntimeError("hybrid diagnostic requires one current nomination frame")
    directory = candidates[0]
    visual = json.loads((directory / "visual_scene.json").read_text())
    binding = json.loads((directory / "binding.json").read_text())
    if visual["env_step"] != step or binding["status"] not in ("bound_ids", "candidate_requires_attribute_check"):
        raise RuntimeError("current visual nomination was refused")
    if binding["unverified_descriptors"] not in ([], ["wine bottle"]):
        raise RuntimeError("unexpected descriptor in anchor diagnostic")
    objects = {item["id"]: item for item in visual["objects"]}
    mapped = {}
    scene = scene_cache[id(env)]
    if os.environ.get('ANCHOR_RGBD_OBSTACLES') == '1':
        obstacle_cache['current'] = json.loads((directory / 'obstacles.json').read_text())
    rows = []
    for role in ("target", "goal"):
        visual_id = binding[role + "_id"]
        if os.environ.get('ANCHOR_VISUAL_IDS') == '1':
            from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState
            category=objects[visual_id]['category']
            name=f'rgbd_{category}_{visual_id}'
            mapped[role]=name
            scene.objects[name]=ObjectState(name,np.asarray(objects[visual_id]['visible_centroid_world_m'],dtype=np.float32),
                                           np.asarray([1.,0.,0.,0.],dtype=np.float32))
            rows.append(dict(role=role,visual_id=visual_id,planning_id=name,source='visual_instance_id'))
            continue
        point = np.asarray(objects[visual_id]["visible_centroid_world_m"][:2])
        ranked = sorted((float(np.linalg.norm(point - obj.pos[:2])), name)
                        for name, obj in scene.objects.items())
        if ranked[0][0] > .08 or (len(ranked) > 1 and ranked[1][0] - ranked[0][0] < .03):
            raise RuntimeError("visual to oracle diagnostic association is ambiguous")
        mapped[role] = ranked[0][1]
        rows.append(dict(role=role, visual_id=visual_id, oracle_body=mapped[role],
                         xy_distance_m=ranked[0][0], nearest_candidates=ranked[:3]))
    if mapped["target"] == mapped["goal"]:
        raise RuntimeError("hybrid target and goal are identical")
    obstacle_cache['target_name'] = mapped['target']
    obstacle_cache['goal_name'] = mapped['goal']
    if os.environ.get("ANCHOR_REPLACE_BOTTLE_GEOMETRY") == "1":
        model = json.loads((directory / "bottle_model.json").read_text())
        target = scene.objects[mapped["target"]]
        target.pos = np.asarray([*model["axis_xy_world_m"], model["bottom_z_world_m"]], dtype=np.float32)
        target.quat = np.asarray([1., 0., 0., 0.], dtype=np.float32)
        geoms = []
        for i, part in enumerate(model["parts"]):
            geoms.append(dict(name=f"rgbd_bottle_part_{i}", body_name=target.name,
                shape="cylinder", type=5, size=[part["radius_m"], (part["z_max_m"] - part["z_min_m"]) / 2],
                pos=[*model["axis_xy_world_m"], (part["z_max_m"] + part["z_min_m"]) / 2],
                quat=[1., 0., 0., 0.], contype=1, conaffinity=1, collision_active=True))
        target.geometry = dict(source="rgbd_upright_bottle_fit", geoms=geoms, model=model)
        from dataclasses import replace
        from experiments.robot.libero.tiptop_repro import tamp_scene
        original_geometry = tamp_scene.estimate_object_geometry

        def geometry_with_source(obj, state):
            geometry = original_geometry(obj, state)
            if obj.geometry.get("source") == "rgbd_upright_bottle_fit":
                geometry = replace(geometry, source="rgbd_upright_bottle_fit",
                    metadata={**geometry.metadata, "rgbd_model": obj.geometry["model"]})
            return geometry

        tamp_scene.estimate_object_geometry = geometry_with_source
        (RUN / f"bottle_geometry_replacement_step{step}.json").write_text(json.dumps(model, indent=2))
    if os.environ.get("ANCHOR_REPLACE_PLATE_GEOMETRY") == "1":
        plate_model = json.loads((directory / "plate_model.json").read_text())
        goal = scene.objects[mapped["goal"]]
        z = plate_model["support_z_world_m"]
        xy = plate_model["center_xy_world_m"]
        goal.pos = np.asarray([*xy, z-.001], dtype=np.float32)
        goal.quat = np.asarray([1., 0., 0., 0.], dtype=np.float32)
        goal.geometry = dict(source="rgbd_plate_support_patch", model=plate_model, geoms=[dict(
            name="rgbd_plate_support", body_name=goal.name, shape="cylinder", type=5,
            size=[plate_model["support_radius_m"], .001], pos=[*xy, z-.001],
            quat=[1., 0., 0., 0.], contype=1, conaffinity=1, collision_active=True)])
        from dataclasses import replace
        from experiments.robot.libero.tiptop_repro import tamp_scene
        previous_geometry = tamp_scene.estimate_object_geometry

        def geometry_with_plate(obj, state):
            geometry = previous_geometry(obj, state)
            if obj.geometry.get("source") == "rgbd_plate_support_patch":
                # Bounds must follow the transformed collision part, not the
                # model's original world coordinates after frame conversion.
                centre = np.asarray(geometry.center)
                half = obj.geometry["model"]["support_radius_m"] / np.sqrt(2)
                top = float(centre[2] + .001)
                bounds = dict(x_min=float(centre[0]-half), x_max=float(centre[0]+half),
                    y_min=float(centre[1]-half), y_max=float(centre[1]+half),
                    z_min=top, z_max=top+.002, support_z=top,
                    source="rgbd_fitted_interior_support_patch")
                geometry = replace(geometry, source="rgbd_plate_support_patch",
                    metadata={**geometry.metadata, "inner_bounds": bounds,
                              "rgbd_model": obj.geometry["model"]})
            return geometry

        tamp_scene.estimate_object_geometry = geometry_with_plate
        (RUN / f"plate_geometry_replacement_step{step}.json").write_text(json.dumps(plate_model, indent=2))
    if os.environ.get('ANCHOR_VISUAL_EXECUTOR') == '1':
        install_visual_executor(scene, directory, mapped)
    # Preserve the baseline's static initial facts and region definitions. The
    # goal and selected bodies below come from the visual nomination, not BDDL.
    baseline = (ParsedTask(language=language,target_hint=mapped['target'],goal_hint=mapped['goal'],
                           operation='place',diagnostics=dict(bddl_init_atoms=[]))
                if os.environ.get('ANCHOR_VISUAL_IDS') == '1'
                else original_parse_task(language, object_names, env=env))
    diagnostics = dict(baseline.diagnostics or {})
    diagnostics.update(target_source="visual_rgbd_with_oracle_body_association",
                       goal_source="visual_rgbd_with_oracle_body_association",
                       hybrid_diagnostic=True, geometry_source="oracle",
                       descriptor_validation="anchor_RGB_manually_inspected; not automated",
                       visual_binding=binding, associations=rows,
                       bddl_target=mapped["target"], bddl_goal=mapped["goal"],
                       bddl_goal_atoms=[dict(predicate=binding["goal_relation"],
                                             args=[mapped["target"], mapped["goal"]])],
                       bddl_goal_surfaces=[mapped["goal"]])
    if os.environ.get("ANCHOR_REPLACE_BOTTLE_GEOMETRY") == "1":
        diagnostics["geometry_source"] = "target_RGBD_fit; other_objects_oracle"
        diagnostics["execution_state_and_guards"] = "historical_oracle_executor"
    if os.environ.get("ANCHOR_REPLACE_PLATE_GEOMETRY") == "1":
        diagnostics["geometry_source"] = "target_and_goal_RGBD_fit; other_objects_oracle"
    if os.environ.get('ANCHOR_RGBD_OBSTACLES') == '1':
        diagnostics['geometry_source']='RGBD_target_goal_table_and_observed_obstacles'
    if os.environ.get('ANCHOR_VISUAL_EXECUTOR') == '1':
        diagnostics['execution_state_and_guards']='RGBD_bottle_pose; initial_RGBD_stationary_plate; proprioception'
    if os.environ.get('ANCHOR_VISUAL_IDS') == '1':
        diagnostics.update(target_source='visual_instance_id',goal_source='visual_instance_id',
                           oracle_body_association_used=False,hybrid_diagnostic=False)
    (RUN / f"hybrid_association_step{step}.json").write_text(json.dumps(diagnostics, indent=2))
    return ParsedTask(language=language, target_hint=mapped["target"],
                      goal_hint=mapped["goal"], operation="place", diagnostics=diagnostics)


controller.read_scene = read_scene
controller.parse_task = parse_task


def install_visual_executor(initial_scene, directory, mapped):
    """Replace runtime object-state acquisition with current RGB-D measurements."""
    import copy
    from experiments.robot.libero import skill_pipeline
    skill_pipeline.__path__.insert(0,str(CODE/'experiments/robot/libero/skill_pipeline'))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation, RGBDObservation
    from experiments.robot.libero.skill_pipeline.visual_bottle_tracker import BottleColorDepthTracker
    from anchor_sensor.libero_rgbd_sensor import capture_libero_rgbd
    from experiments.robot.libero.tiptop_repro import libero_tiptop_executor, optimized_executor, executor
    frame=load_observation(RUN/'snapshots/recovery01/pre_solver_attempt01/agentview')
    visual=json.loads((directory/'visual_scene.json').read_text())
    binding=json.loads((directory/'binding.json').read_text())
    index=next(o['detection_index'] for o in visual['objects'] if o['id']==binding['target_id'])
    mask=np.load(directory/'detections.npz')['masks'][index]
    model=json.loads((directory/'bottle_model.json').read_text())
    tracker=BottleColorDepthTracker(frame,mask,model)
    template=copy.deepcopy(initial_scene)
    template.objects={name:template.objects[name] for name in (mapped['target'],mapped['goal'])}
    template.contacts=[];template.joints={}
    output=RUN/'visual_execution';output.mkdir(exist_ok=False)

    def visual_runtime_scene(env, obs):
        sensor=capture_libero_rgbd(env,obs,episode_id='task04_ep00',
                                 env_step=env._anchor_control_steps,camera_id='agentview')
        current=RGBDObservation(**sensor.__dict__)
        model,report=tracker.update(current)
        state=copy.deepcopy(template)
        state.ee_pos=np.asarray(obs['robot0_eef_pos'],dtype=np.float32)
        state.ee_quat=np.asarray(obs['robot0_eef_quat'],dtype=np.float32)
        state.gripper_qpos=np.asarray(obs['robot0_gripper_qpos'],dtype=np.float32)
        state.robot_qpos=np.asarray(obs['robot0_joint_pos'],dtype=np.float32)
        state.holding_evidence=dict(status='unknown',object_name=None,
                                   source='proprioception_and_visual_pose; requires_lift_probe')
        state.robot_joint_debug=proprio_frame_debug(current)
        target=state.objects[mapped['target']]
        target.pos=np.asarray([*model['axis_xy_world_m'],model['bottom_z_world_m']],dtype=np.float32)
        target.quat=np.asarray([1.,0.,0.,0.],dtype=np.float32)
        target.geometry['model']=model
        for geom,part in zip(target.geometry['geoms'],model['parts']):
            geom['pos']=[*model['axis_xy_world_m'],(part['z_min_m']+part['z_max_m'])/2]
        path=output/f'step{env._anchor_control_steps:04d}.json'
        if not path.exists():path.write_text(json.dumps(dict(report,
            target_name=mapped['target'],goal_name=mapped['goal'],
            runtime_object_pose_source='RGBD',runtime_contacts_used=False,
            plate_pose_source='initial_RGBD_support_fit; stationary_plate_assumption'),indent=2))
        return state

    for module in (libero_tiptop_executor,optimized_executor,executor):
        module.read_scene=visual_runtime_scene


def proprio_frame_debug(frame):
    from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base
    from experiments.robot.libero.tiptop_repro.libero_panda_frames import matrix_to_quat_wxyz
    base=infer_world_from_base(frame)
    return dict(source='current_proprioception',q_init_source='obs_robot0_joint_pos',
        frame_candidates=[dict(name='robot0_base',pos_world=base[:3,3].tolist(),
                               quat_world_wxyz=matrix_to_quat_wxyz(base[:3,:3]).tolist(),
                               source='static_panda_fk_and_current_proprioception')])


def robot_only_scene(obs, frame=None):
    import runpy
    from experiments.robot.libero.tiptop_repro.scene_reader import SceneState
    infer=runpy.run_path(str(CODE/'experiments/robot/libero/skill_pipeline/proprio_hand_state.py'))['infer_panda_hand_state']
    hand=infer(obs)
    obstacle_cache['robot_qpos']=np.asarray(obs['robot0_joint_pos'],dtype=np.float64).copy()
    return SceneState(ee_pos=np.asarray(obs['robot0_eef_pos'],dtype=np.float32),
        ee_quat=np.asarray(obs['robot0_eef_quat'],dtype=np.float32),
        gripper_qpos=np.asarray(obs['robot0_gripper_qpos'],dtype=np.float32),
        robot_qpos=np.asarray(obs['robot0_joint_pos'],dtype=np.float32),
        holding_evidence=dict(hand,object_name=None,candidates=[]),
        robot_joint_debug=proprio_frame_debug(frame) if frame is not None else dict(source='proprioception'))


if os.environ.get('ANCHOR_VISUAL_IDS') == '1':
    from experiments.robot.libero import skill_pipeline
    skill_pipeline.__path__.insert(0,str(CODE/'experiments/robot/libero/skill_pipeline'))
    from experiments.robot.libero.tiptop_repro import libero_tiptop_executor, optimized_executor, executor
    # Entry lift only needs proprioception. Runtime object scenes replace this
    # function after nomination, without ever querying simulator object bodies.
    for module in (libero_tiptop_executor,optimized_executor,executor):
        module.read_scene=lambda env,obs:robot_only_scene(obs)

    def cache_robot_steps(env):
        """Keep the current measured joints without accessing simulator FK."""
        if getattr(env, '_anchor_robot_step_cached', False):
            return
        step = env.step
        def measured_step(*args, **kwargs):
            result = step(*args, **kwargs)
            obstacle_cache['robot_qpos'] = np.asarray(result[0]['robot0_joint_pos'],dtype=np.float64).copy()
            return result
        env.step = measured_step
        env._anchor_robot_step_cached = True

    def static_pose_waypoints(env,joint_confs,reference_quat_xyzw=None,*,calibrate_at_current_state=False):
        from experiments.robot.libero.skill_pipeline.visual_robot_frames import panda_base_from_hand
        from experiments.robot.libero.tiptop_repro.libero_panda_frames import matrix_to_quat_wxyz
        from experiments.robot.libero.skill_pipeline.visual_rim_grasp import rotation_xyzw
        base=obstacle_cache['world_from_base']
        transforms=[base @ panda_base_from_hand(q) for q in np.asarray(joint_confs)]
        correction=np.eye(3)
        if reference_quat_xyzw is not None:
            if calibrate_at_current_state:
                current=base @ panda_base_from_hand(obstacle_cache['robot_qpos'])
                correction=current[:3,:3].T @ rotation_xyzw(reference_quat_xyzw)
            else:
                correction=rotation_xyzw(reference_quat_xyzw) @ transforms[0][:3,:3].T
        result=[]
        for t in transforms:
            position=t[:3,3]+t[:3,:3] @ np.array([0.,0.,.097])
            quat=matrix_to_quat_wxyz(t[:3,:3] @ correction if calibrate_at_current_state else correction @ t[:3,:3])
            result.append(dict(position=position.tolist(),quat_xyzw=[*quat[1:],quat[0]]))
        return result

    libero_tiptop_executor._joint_path_to_ee_pose_waypoints=static_pose_waypoints
    libero_tiptop_executor._joint_path_to_ee_waypoints=lambda env,qs:[tuple(row['position']) for row in static_pose_waypoints(env,qs)]

if os.environ.get('ANCHOR_PROPRIO_HAND_STATE') == '1':
    from experiments.robot.libero.tiptop_repro import scene_graph

    def proprio_handempty_atoms(scene, source=None):
        report = scene.holding_evidence
        if report.get('status') != 'handempty_inferred_from_proprioception':
            return []
        return [dict(atom, args=['gripper'], confidence=1.0,
                     confidence_definition='deterministic_rule_under_explicit_pinch_assumptions')
                for atom in report['initial_atoms']]

    scene_graph.make_handempty_atoms = proprio_handempty_atoms

if os.environ.get('ANCHOR_RGBD_OBSTACLES') == '1':
    original_build_problem = controller.build_tamp_problem

    def build_observed_problem(*args, **kwargs):
        from dataclasses import replace
        from experiments.robot.libero.tiptop_repro.tamp_scene import TAMPObject
        problem = original_build_problem(*args, **kwargs)
        obs = obstacle_cache['current']
        target = obstacle_cache['target_name']
        goal = obstacle_cache['goal_name']
        statics = []
        for i, (centre, half) in enumerate(zip(obs['centres'], obs['half_extents'])):
            statics.append(TAMPObject(name=f'rgbd_obstacle_{i:04d}', pos=centre,
                radius=float(np.linalg.norm(half[:2])), height=2*half[2], role='static',
                half_extents=half, geometry=dict(source=obs['source'], half_extents=half)))
        lo, hi = np.asarray(obs['table_xy_min']), np.asarray(obs['table_xy_max'])
        centre = [*((lo+hi)/2), obs['table_z']]
        half = [*((hi-lo)/2), .01]
        table_geometry = dict(source='rgbd_horizontal_table_patch', center=centre,
            half_extents=half, bounds=dict(x_min=float(lo[0]), x_max=float(hi[0]),
                y_min=float(lo[1]), y_max=float(hi[1]), z=obs['table_z']))
        table = TAMPObject(name='table', pos=centre, radius=float(np.linalg.norm(half[:2])),
                          height=.02, role='surface', half_extents=half, geometry=table_geometry)
        mapping = json.loads(json.dumps(problem.fluent_mapping))
        allowed = {target, goal, 'table', 'gripper'}
        for section in mapping.values():
            if 'fluents' in section:
                section['fluents'] = [atom for atom in section['fluents'] if set(atom.get('args', [])) <= allowed]
        problem = replace(problem, movables=[o for o in problem.movables if o.name==target],
            surfaces=[table]+[o for o in problem.surfaces if o.name==goal], statics=statics,
            table_z=obs['table_z'], table_geometry=table_geometry, fluent_mapping=mapping,
            init_atoms=[a for a in problem.init_atoms if set(a.get('args', []))<=allowed])
        (RUN / 'obstacle_problem_audit.json').write_text(json.dumps(dict(
            observed_box_count=len(statics), removed_oracle_obstacles=True,
            table_geometry=table_geometry, hidden_geometry='unobserved'), indent=2))
        return problem

    controller.build_tamp_problem = build_observed_problem
    # Recovery goal search rebuilds the problem independently of the perceiver.
    from experiments.robot.libero.tiptop_repro import real_cutamp_adapter
    real_cutamp_adapter.build_tamp_problem = build_observed_problem
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackend
    original_solve = RealCuTAMPBackend.solve

    def solve_observed(self, problem, *args, **kwargs):
        objects = problem.movables + problem.surfaces + problem.statics
        if not all(str(obj.geometry.get('source', '')).startswith('rgbd_') for obj in objects):
            raise RuntimeError('oracle collision geometry reintroduced before native solve')
        return original_solve(self, problem, *args, **kwargs)

    RealCuTAMPBackend.solve = solve_observed
