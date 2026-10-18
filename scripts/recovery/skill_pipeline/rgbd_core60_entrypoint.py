"""Full VLA/skill rollout with RGB-D geometry inside recovery only.

Skill triggering retains the frozen C4 benchmark protocol. Simulator success
ends the episode externally; unsupported visual recoveries return to VLA and
never fall back to an oracle recovery controller.
"""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import runpy
import sys
import traceback

ROOT=Path(os.environ['ROOT']);CASE=Path(os.environ['RGBD_CASE_DIR']);CODE=Path(os.environ['ANCHOR_VISUAL_CODE'])
sys.path.insert(0,str(CODE))
sys.path.insert(0,os.environ['OVERLAY_ROOT'])
from experiments.robot.libero import skill_pipeline
from experiments.robot.libero.skill_pipeline import runner
skill_pipeline.__path__.append(str(CODE/'experiments/robot/libero/skill_pipeline'))
from scripts.recovery.skill_pipeline.shared_benchmark_policy import SharedBenchmarkPolicy
runner.JaxOpenPIUncertaintyPolicyAdapter=SharedBenchmarkPolicy
runner.SubprocessOpenPIUncertaintyPolicyAdapter=SharedBenchmarkPolicy
from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as ctl
from experiments.robot.libero.tiptop_repro import libero_tiptop_executor as le,optimized_executor as oe,executor as ex
from experiments.robot.libero.tiptop_repro import real_cutamp_adapter as adapter,scene_graph,real_cutamp_backend as backend
from anchor_sensor.libero_rgbd_sensor import capture_libero_rgbd
from anchor_sensor.rgbd_observation import save_observation

original_recover=ctl.CuTAMPV2TipTopController.recover
original_perceive=ctl.CuTAMPV2OraclePerceiver.perceive
saved=[]
for module,names in [(ctl,['read_scene','parse_task','build_tamp_problem']),
 (le,['read_scene','_joint_path_to_ee_pose_waypoints','_joint_path_to_ee_waypoints','_object_world_z','_opening_bounds']),
 (oe,['read_scene','_scene_on_or_inside']),(ex,['read_scene']),
 (adapter,['build_tamp_problem']),(scene_graph,['make_handempty_atoms']),
 (backend.RealCuTAMPBackend,['solve'])]:
    for name in names:saved.append((module,name,getattr(module,name)))


class BenchmarkSuccess(Exception):pass


def capture(env,current,directory,phase,language):
    target=directory/'snapshots/recovery01'/phase
    for camera in ['agentview','robot0_eye_in_hand']:
        frame=capture_libero_rgbd(env,current,episode_id=os.environ['ANCHOR_EPISODE_ID'],
            env_step=env._anchor_control_steps,camera_id=camera)
        save_observation(frame,target/camera)
    (target/'capture_audit.json').write_text(json.dumps(dict(language=language,phase=phase,
        control_steps=env._anchor_control_steps,source='current_sensors'),indent=2))


def get_env(task,resolution,seed):
    from libero.libero.envs import OffScreenRenderEnv
    env=OffScreenRenderEnv(bddl_file_name=str(task.bddl_path),camera_heights=640,camera_widths=640,camera_depths=True)
    env.seed(seed);env._anchor_control_steps=0;env._rgbd_active=False;env._rgbd_latest=None
    step=env.step
    def measured_step(action,*args,**kwargs):
        result=step(action,*args,**kwargs);env._anchor_control_steps+=1;env._rgbd_latest=result[0]
        if env._rgbd_active:
            # This is the benchmark termination boundary, before perception.
            # No success signal is supplied to RGB-D tracking or planning.
            if env.check_success():raise BenchmarkSuccess()
            observe=getattr(env,'_anchor_framewise_observe',None)
            if observe is not None:observe(result[0])
            if env._anchor_control_steps%20==0:
                capture(env,result[0],env._rgbd_directory,f'execution_step{env._anchor_control_steps:05d}',env._rgbd_language)
        return result
    env.step=measured_step
    return env,task.language


def recover(self,env,obs,language,*args,**kwargs):
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import parse_visual_pick_place_language,prompts_from_task_language,category_for_phrase
    calls=getattr(env,'_rgbd_calls',0)+1;env._rgbd_calls=calls
    directory=CASE/f'recovery{calls:02d}';directory.mkdir(exist_ok=False)
    for module,name,function in saved:setattr(module,name,function)
    entry_step=env.step;start=env._anchor_control_steps;attempt=[0];events=[]
    original_hints=copy.deepcopy(kwargs.get('recovery_hints') or {})
    (directory/'original_recovery_hints.json').write_text(json.dumps(original_hints,indent=2))
    capture(env,obs,directory,'entry',language)
    env._rgbd_latest=obs;env._rgbd_directory=directory;env._rgbd_language=language
    result=None;error=None;completion=None
    try:
        task=parse_visual_pick_place_language(language)
        target_category=category_for_phrase(task.target_phrase);goal_category=category_for_phrase(task.goal_phrase)
        vision=json.loads(Path(os.environ['RGBD_VISION_CONFIG']).read_text())
        vision['prompts']=prompts_from_task_language(language)
        for category,prompt in dict(bowl='bowl',rack='rack',carton='carton',cabinet='cabinet',stove='stove').items():
            vision['prompts'].setdefault(category,prompt)
        rack_skill=(original_hints if target_category=='cheese' and goal_category=='rack'
                    and original_hints.get('params',{}).get('geometry_hints',{}).get('placement_region',{}).get('geometry_profile')=='wine_rack_top_region_surface_v1' else None)
        config=dict(plane=dict(id='plane_00'),vision=vision,target_category=target_category,goal_category=goal_category,
            generic_task=not bool(rack_skill),goal_relation=task.goal_relation,rack_skill=rack_skill,
            release_pose_constraint=not bool(rack_skill),wrist_fallback=True,occlusion_aware_tracking=True,
            tracking_short_gap=dict(max_missing_steps=10,max_missing_seconds=.5),visual_goal_diagnostic_only=True,
            collision_policy='oracle_cheese_rack_contacts_v1' if rack_skill else 'strict')
        config_path=directory/'observed_config.json';config_path.write_text(json.dumps(config,indent=2))
        os.environ.update(ANCHOR_CAPTURE_DIR=str(directory/'snapshots'),ANCHOR_OBSERVED_PLACEMENT_CONFIG=str(config_path))
        support=directory/'capture_support';support.mkdir()
        source=Path(os.environ['RGBD_SENSOR_SUPPORT'])
        import shutil
        shutil.copytree(source/'anchor_sensor',support/'anchor_sensor')
        os.environ['ANCHOR_CAPTURE_DIR']=str(directory/'snapshots')
        runpy.run_path(str(CODE/'scripts/recovery/skill_pipeline/observed_geometry_recovery_hook.py'),run_name='live_rgbd_recovery')
        def perceive(perceiver,env_arg,current,description,*more,**kw):
            attempt[0]+=1
            capture(env_arg,current,directory,f'pre_solver_attempt{attempt[0]:02d}',description)
            return original_perceive(perceiver,env_arg,current,description,*more,**kw)
        ctl.CuTAMPV2OraclePerceiver.perceive=perceive
        params={k:v for k,v in original_hints.get('params',{}).items() if k not in ['geometry_hints','grounding_hints','geometry_profile','grounding_profile']}
        hints=dict(original_hints,params=params,target='target')
        kwargs['recovery_hints']=hints
        callback=kwargs.get('step_callback')
        def record(current,event):
            events.append(dict(event))
            if callback is not None:callback(current,event)
        kwargs['step_callback']=record
        self.cfg=replace(self.cfg,real_cutamp_cfg=replace(self.cfg.real_cutamp_cfg,
            apply_simulator_truth_initial_state=False,debug_dir=str(directory/'cutamp_debug')))
        env._rgbd_active=True
        result=original_recover(self,env,obs,language,*args,**kwargs)
        if env.check_success():result=replace(result,success=True);completion='benchmark_simulator_success'
    except BenchmarkSuccess:
        completion='benchmark_simulator_success'
        result=ctl.CuTAMPRecoveryResult(obs=env._rgbd_latest,success=True,total_env_steps=env._anchor_control_steps-start)
    except Exception:
        error=traceback.format_exc()
        result=ctl.CuTAMPRecoveryResult(obs=env._rgbd_latest,success=False,total_env_steps=env._anchor_control_steps-start)
    finally:
        env._rgbd_active=False
        try:capture(env,env._rgbd_latest,directory,'final',language)
        except Exception:(directory/'capture_error.txt').write_text(traceback.format_exc())
        if hasattr(env,'_anchor_close_vision'):
            try:env._anchor_close_vision()
            except Exception:pass
        for name in ['_anchor_framewise_observe','_anchor_close_vision','_anchor_robot_step_cached']:
            if hasattr(env,name):delattr(env,name)
        env.step=entry_step
        ctl.CuTAMPV2OraclePerceiver.perceive=original_perceive
        for module,name,function in saved:setattr(module,name,function)
    report=dict(success=result.success,completion_source=completion,error=error,
        start_control_step=start,end_control_step=env._anchor_control_steps,
        oracle_recovery_fallback=False,visual_goal_is_diagnostic=True,
        attempts=[a.to_dict() for a in result.attempts])
    (directory/'result.json').write_text(json.dumps(report,indent=2))
    (directory/'execution_events.json').write_text(json.dumps(events,indent=2))
    return result


runner._get_libero_env=get_env
ctl.CuTAMPV2TipTopController.recover=recover
runpy.run_path(os.environ['ORACLE_ENTRYPOINT'],run_name='__main__')
