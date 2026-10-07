"""Single-variable closed-gripper waiting-time contrast."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--close-steps',type=int,choices=(16,40),default=40)
    p.add_argument('--timeout-s',type=int,default=1800)
    p.add_argument('--max-control-steps',type=int,default=160)
    args=p.parse_args()
    if not 1<=args.max_control_steps<=200 or not 1<=args.timeout_s<=3600:raise ValueError('invalid budget')
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    args.out_dir.mkdir(parents=True,exist_ok=False)
    env=None
    with OracleImportGuard() as guard:
        try:
            import numpy as np
            from libero.libero import benchmark,get_libero_path
            from libero.libero.envs import OffScreenRenderEnv
            from experiments.robot.libero.skill_pipeline.libero_rgbd_sensor import capture_libero_rgbd
            from experiments.robot.libero.skill_pipeline.rgbd_observation import save_observation
            from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
            from experiments.robot.libero.skill_pipeline.visual_pregrasp_control import make_pregrasp_plan,translation_action
            from experiments.robot.libero.skill_pipeline.visual_rim_grasp import make_visible_rim_candidate
            suite=benchmark.get_benchmark_dict()['libero_spatial']();task=suite.get_task(0)
            bddl=Path(get_libero_path('bddl_files'))/task.problem_folder/task.bddl_file
            env=OffScreenRenderEnv(bddl_file_name=str(bddl),camera_names=['agentview','robot0_eye_in_hand'],camera_heights=512,camera_widths=512,camera_depths=True,camera_segmentations=None)
            env.seed(11);env.reset();obs=env.set_init_state(suite.get_task_init_states(0)[1])
            episode='visual_grasp_close_wait_'+uuid.uuid4().hex;step=0
            for _ in range(10):obs,_,_,_=env.step([0,0,0,0,0,0,-1]);step+=1
            def capture(obs,step,label):
                frames=[]
                for camera in ('agentview','robot0_eye_in_hand'):
                    f=capture_libero_rgbd(env,obs,episode_id=episode,env_step=step,camera_id=camera)
                    save_observation(f,args.out_dir/label/camera);frames.append(f)
                return frames[0]
            initial=capture(obs,step,'initial')
            (args.out_dir/'request.json').write_text(json.dumps(dict(episode_id=episode,env_step=step,language=str(task.language),task_suite='libero_spatial',task_id_zero_based=0,init_index=1,seed=11,rgb_sha256=rgb_sha256(initial)),indent=2)+'\n')
            print('PREGRASP_FRAME_READY '+str(args.out_dir),flush=True)
            deadline=time.monotonic()+args.timeout_s
            while not (args.out_dir/'selection/READY').is_file():
                if time.monotonic()>deadline:raise TimeoutError('current visual selection timed out')
                time.sleep(.5)
            selection=json.loads((args.out_dir/'selection/selection.json').read_text())
            if (selection['episode_id']!=episode or selection['env_step']!=step or selection['rgb_sha256']!=rgb_sha256(initial)
                    or selection['selection_source']!='assistant_explicit_visual_candidate' or selection.get('human_reviewed') is not False):raise ValueError('selection provenance mismatch')
            with np.load(args.out_dir/'selection/mask.npz',allow_pickle=False) as z:mask=z['mask']
            plan=make_pregrasp_plan(initial,mask)
            (args.out_dir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
            controller=env.env.robots[0].controller
            if (controller.name!='OSC_POSE' or not np.allclose(controller.output_max[:3],.05)
                    or not np.allclose(controller.output_min[:3],-.05) or not controller.use_delta):raise ValueError('unverified OSC configuration')
            trace=[];used=0;terminal_seen=False;reached=[]
            for index,goal in enumerate(plan['waypoints_world_m']):
                ok=False
                while used<args.max_control_steps:
                    action,distance=translation_action(obs['robot0_eef_pos'],goal)
                    if action is None:ok=True;break
                    prior=np.asarray(obs['robot0_eef_pos']).tolist()
                    obs,_,done,_=env.step(action.tolist());used+=1;step+=1;terminal_seen|=bool(done)
                    row=dict(control_step=used,env_step=step,phase='pregrasp',waypoint_index=index,action=action.tolist(),eef_before_m=prior,eef_after_m=np.asarray(obs['robot0_eef_pos']).tolist(),error_before_m=distance,error_after_m=float(np.linalg.norm(np.asarray(goal)-obs['robot0_eef_pos'])))
                    trace.append(row)
                    print(json.dumps(row),flush=True)
                ok=bool(np.linalg.norm(np.asarray(goal)-obs['robot0_eef_pos'])<=.008)
                reached.append(ok)
                capture(obs,step,'waypoint'+str(index))
                if not ok:break
            if reached!=[True,True,True]:raise RuntimeError('pregrasp did not reach its waypoints')
            pregrasp=capture(obs,step,'pregrasp')
            (args.out_dir/'grasp_request.json').write_text(json.dumps(dict(episode_id=episode,env_step=step,rgb_sha256=rgb_sha256(pregrasp)),indent=2)+'\n')
            print('GRASP_FRAME_READY '+str(args.out_dir),flush=True)
            deadline=time.monotonic()+args.timeout_s
            while not (args.out_dir/'grasp_selection/READY').is_file():
                if time.monotonic()>deadline:raise TimeoutError('current grasp mask selection timed out')
                time.sleep(.5)
            grasp_selection=json.loads((args.out_dir/'grasp_selection/selection.json').read_text())
            if (grasp_selection['episode_id']!=episode or grasp_selection['env_step']!=step or grasp_selection['rgb_sha256']!=rgb_sha256(pregrasp)
                    or grasp_selection['selection_source']!='assistant_explicit_visual_candidate' or grasp_selection.get('human_reviewed') is not False):raise ValueError('grasp selection provenance mismatch')
            with np.load(args.out_dir/'grasp_selection/mask.npz',allow_pickle=False) as z:grasp_mask=z['mask']
            rim=make_visible_rim_candidate(pregrasp,grasp_mask)
            (args.out_dir/'rim_plan.json').write_text(json.dumps(rim,indent=2)+'\n')
            pregrasp_actions=used;motion_steps=0;phase_results=[]
            def execute(action,phase,goal=None):
                nonlocal obs,used,step,terminal_seen
                prior=np.asarray(obs['robot0_eef_pos']).tolist()
                obs,_,done,_=env.step(action.tolist());used+=1;step+=1;terminal_seen|=bool(done)
                row=dict(control_step=used,env_step=step,phase=phase,action=action.tolist(),eef_before_m=prior,eef_after_m=np.asarray(obs['robot0_eef_pos']).tolist(),gripper_qpos=np.asarray(obs['robot0_gripper_qpos']).tolist())
                if goal is not None:row.update(goal_world_m=np.asarray(goal).tolist(),error_after_m=float(np.linalg.norm(np.asarray(goal)-obs['robot0_eef_pos'])))
                trace.append(row);print(json.dumps(row),flush=True)
            def move(goal,phase,gripper):
                nonlocal motion_steps
                while motion_steps<180:
                    action,distance=translation_action(obs['robot0_eef_pos'],goal,tolerance_m=.003)
                    if action is None:break
                    action[6]=gripper;execute(action,phase,goal);motion_steps+=1
                ok=bool(np.linalg.norm(np.asarray(goal)-obs['robot0_eef_pos'])<=.003)
                phase_results.append(dict(phase=phase,position_reached=ok,error_m=float(np.linalg.norm(np.asarray(goal)-obs['robot0_eef_pos']))))
                capture(obs,step,phase)
                return ok
            descent_ok=move(rim['align_goal_world_m'],'rim_align',-1) and move(rim['pinch_goal_world_m'],'before_close',-1)
            grasp_attempted=False
            if descent_ok:
                grasp_attempted=True
                close=np.array([0.,0.,0.,0.,0.,0.,1.])
                for _ in range(args.close_steps):execute(close,'close')
                capture(obs,step,'after_close');lift_start=np.asarray(obs['robot0_eef_pos']).copy()
                for lift in (.005,.020,.040):
                    goal=lift_start+np.array([0.,0.,lift])
                    if not move(goal,'lift'+str(int(lift*1000))+'mm',1):break
                for _ in range(8):execute(close,'hold')
                capture(obs,step,'after_hold')
                observation_start=np.asarray(obs['robot0_eef_pos']).copy()
                jog_ok=move(observation_start+np.array([0.,.010,0.]),'observation_jog',1)
                if jog_ok:move(observation_start,'observation_return',1)
                for _ in range(40):execute(close,'observation_hold')
                capture(obs,step,'after_observation')
            final=capture(obs,step,'final')
            result=dict(scope='assistant_selected_rgbd_grasp_observation_attempt',episode_id=episode,selection=selection,plan=plan,rim_plan=rim,grasp_selection=grasp_selection,
                        experimental_close_steps=args.close_steps,control_actions=used,pregrasp_actions=pregrasp_actions,grasp_motion_actions=motion_steps,settle_actions=10,policy_actions=0,waypoints_reached=reached,
                        pregrasp_position_reached=True,grasp_phase_results=phase_results,final_gripper_qpos=np.asarray(obs['robot0_gripper_qpos']).tolist(),
                        benchmark_terminal_seen=terminal_seen,benchmark_terminal_used_for_control=False,final_rgb_sha256=rgb_sha256(final),
                        identity_verified=False,grasp_attempted=grasp_attempted,holding_verified=False,task_success_verified=False,
                        cutamp_used=False,production_recovery_integrated=False,blocked_oracle_import_attempts=guard.blocked_import_attempts)
            (args.out_dir/'control_trace.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in trace))
            (args.out_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
        except Exception as exc:
            if 'trace' in locals():(args.out_dir/'control_trace.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in trace))
            (args.out_dir/'abort.json').write_text(json.dumps(dict(error=str(exc),oracle_fallback=False),indent=2)+'\n');raise
        finally:
            if env is not None:env.close()


if __name__=='__main__':main()
