"""Live simulation pregrasp canary with externally selected current RGB mask."""
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
            suite=benchmark.get_benchmark_dict()['libero_spatial']();task=suite.get_task(0)
            bddl=Path(get_libero_path('bddl_files'))/task.problem_folder/task.bddl_file
            env=OffScreenRenderEnv(bddl_file_name=str(bddl),camera_names=['agentview','robot0_eye_in_hand'],camera_heights=512,camera_widths=512,camera_depths=True,camera_segmentations=None)
            env.seed(11);env.reset();obs=env.set_init_state(suite.get_task_init_states(0)[1])
            episode='visual_pregrasp_'+uuid.uuid4().hex;step=0
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
                    row=dict(control_step=used,env_step=step,waypoint_index=index,action=action.tolist(),eef_before_m=prior,eef_after_m=np.asarray(obs['robot0_eef_pos']).tolist(),error_before_m=distance,error_after_m=float(np.linalg.norm(np.asarray(goal)-obs['robot0_eef_pos'])))
                    trace.append(row)
                    print(json.dumps(row),flush=True)
                reached.append(ok)
                capture(obs,step,'waypoint'+str(index))
                if not ok:break
            final=capture(obs,step,'final')
            result=dict(scope='assistant_selected_rgbd_pregrasp_control_canary',episode_id=episode,selection=selection,plan=plan,
                        control_actions=used,settle_actions=10,policy_actions=0,waypoints_reached=reached,
                        pregrasp_position_reached=bool(len(reached)==3 and all(reached)),final_position_error_m=float(np.linalg.norm(np.asarray(plan['goal_world_m'])-obs['robot0_eef_pos'])),
                        benchmark_terminal_seen=terminal_seen,benchmark_terminal_used_for_control=False,final_rgb_sha256=rgb_sha256(final),
                        identity_verified=False,grasp_attempted=False,holding_verified=False,task_success_verified=False,
                        cutamp_used=False,production_recovery_integrated=False,blocked_oracle_import_attempts=guard.blocked_import_attempts)
            (args.out_dir/'control_trace.jsonl').write_text(''.join(json.dumps(row)+'\n' for row in trace))
            (args.out_dir/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result),flush=True)
        except Exception as exc:
            (args.out_dir/'abort.json').write_text(json.dumps(dict(error=str(exc),oracle_fallback=False),indent=2)+'\n');raise
        finally:
            if env is not None:env.close()


if __name__=='__main__':main()
