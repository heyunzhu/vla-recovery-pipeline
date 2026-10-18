"""Replay a frozen recovery initial state, without loading the VLA policy.

The simulator checkpoint is only an episode initial condition. Perception
receives current sensor frames. Final simulator success is an evaluation label.
"""
import argparse
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--bddl',type=Path,required=True)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--capture-every',type=int,default=10)
    parser.add_argument('--camera-resolution',type=int,choices=(256,640),default=256,
                        help='Render synchronized native RGB and depth; calibration follows this size')
    parser.add_argument('--restore-open-gripper-command',action='store_true',
                        help='Reconstruct the open motor command; physics state alone omits it')
    parser.add_argument('--evaluation-done-only',action='store_true',
                        help='Keep simulator reward/done out of the recovery control loop')
    parser.add_argument('--settle-steps',type=int,default=0,
                        help='After recovery, hold measured hand state and observe settling; never force release')
    args=parser.parse_args()
    import numpy as np
    from libero.libero.envs import OffScreenRenderEnv
    from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as ctl
    from experiments.robot.libero.tiptop_repro.cutamp_like import ParticleOptimizationConfig
    from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackendConfig
    sys.path.insert(0,str(args.run_dir/'capture_support'))
    from anchor_sensor.libero_rgbd_sensor import capture_libero_rgbd
    from anchor_sensor.rgbd_observation import save_observation
    meta=json.loads((args.fixture/'config.json').read_text())
    raw=meta['controller_config']
    raw['particle_cfg']=ParticleOptimizationConfig(**raw['particle_cfg'])
    raw['real_cutamp_cfg']=RealCuTAMPBackendConfig(**raw['real_cutamp_cfg'])
    raw['real_cutamp_cfg']=replace(raw['real_cutamp_cfg'],debug_dir=str(args.run_dir/'cutamp_debug'))
    cfg=ctl.CuTAMPV2Config(**raw)
    env=OffScreenRenderEnv(bddl_file_name=str(args.bddl),camera_heights=args.camera_resolution,
                           camera_widths=args.camera_resolution,camera_depths=True)
    env.seed(meta.get('episode_seed', 1));env.reset()
    initial=np.load(args.fixture/'initial_physics_state.npy')
    obs=env.set_init_state(initial)
    restored=env.sim.get_state().flatten()
    if not np.array_equal(initial,restored):
        raise RuntimeError('benchmark initial physics checkpoint did not restore exactly')
    if args.restore_open_gripper_command:
        q=np.asarray(obs['robot0_gripper_qpos'])
        if not (q[0]>=.035 and q[1]<=-.035):
            raise RuntimeError('open gripper command reconstruction requires measured open fingers')
        env.env.robots[0].gripper.current_action=np.array([1.,-1.])
    env._anchor_control_steps=meta['control_steps']
    out=args.run_dir/'snapshots/recovery01'
    out.mkdir(parents=True,exist_ok=False)

    def capture(current,phase):
        directory=out/phase;directory.mkdir()
        before=hashlib.sha256(env.sim.get_state().flatten().tobytes()).hexdigest()
        for camera in ('agentview','robot0_eye_in_hand'):
            f=capture_libero_rgbd(env,current,episode_id=meta.get('episode_id', 'task04_ep00'),
                                  env_step=env._anchor_control_steps,camera_id=camera)
            save_observation(f,directory/camera)
        after=hashlib.sha256(env.sim.get_state().flatten().tobytes()).hexdigest()
        if before!=after:raise RuntimeError('sensor capture changed physics')
        (directory/'capture_audit.json').write_text(json.dumps(dict(phase=phase,
            control_steps=env._anchor_control_steps,language=meta['language'],
            physics_unchanged=True,physics_state_before=before,physics_state_after=after),indent=2))

    original_step=env.step
    latest_obs=[obs]
    last_gripper_action=[-1.]
    def step(*a,**kw):
        action=np.asarray(a[0] if a else kw.get('action',[])).reshape(-1)
        if action.size==7:last_gripper_action[0]=float(action[-1])
        result=original_step(*a,**kw);env._anchor_control_steps+=1
        latest_obs[0]=result[0]
        if hasattr(env,'_anchor_framewise_observe'):
            env._anchor_framewise_observe(result[0])
        if args.capture_every>0 and env._anchor_control_steps%args.capture_every==0:
            capture(result[0],f'execution_step{env._anchor_control_steps:04d}')
        if args.evaluation_done_only:
            result=(result[0],0.,False,{})
        return result
    env.step=step
    original_perceive=ctl.CuTAMPV2OraclePerceiver.perceive
    attempt=0
    def perceive(self,env_arg,current,language,*a,**kw):
        nonlocal attempt
        attempt+=1;capture(current,f'pre_solver_attempt{attempt:02d}')
        return original_perceive(self,env_arg,current,language,*a,**kw)
    ctl.CuTAMPV2OraclePerceiver.perceive=perceive
    runpy.run_path(os.environ['ANCHOR_DIAGNOSTIC_HOOK'],run_name='anchor_diagnostic_hook')
    capture(obs,'entry')
    events=[]
    def callback(current,event):events.append(dict(event))
    try:
        result=ctl.CuTAMPV2TipTopController(cfg).recover(env,obs,meta['language'],
                       step_callback=callback,recovery_hints=meta['recovery_hints'])
    except Exception as error:
        capture(latest_obs[0],'failure')
        report=dict(recovery_success=False,error_type=type(error).__name__,error=str(error),
            control_steps=env._anchor_control_steps,
            simulator_reward_done_hidden_from_recovery=args.evaluation_done_only,
            final_simulator_success_for_evaluation=bool(env.check_success()))
        (args.run_dir/'failure_result.json').write_text(json.dumps(report,indent=2))
        (args.run_dir/'execution_events.json').write_text(json.dumps(events,indent=2))
        if hasattr(env,'_anchor_close_vision'):env._anchor_close_vision()
        env.close()
        raise
    capture(result.obs,'final')
    report=dict(recovery_success=result.success,total_env_steps=result.total_env_steps,
        abort_episode=result.abort_episode,abort_reason=result.abort_reason,
        attempts=[a.to_dict() for a in result.attempts],
        initial_state_exactly_restored=True,policy_loaded=False,
        gripper_command_reconstructed=args.restore_open_gripper_command,
        full_controller_checkpoint_restored=False,
        simulator_reward_done_hidden_from_recovery=args.evaluation_done_only,
        final_simulator_success_for_evaluation=bool(env.check_success()))
    (args.run_dir/'replay_result.json').write_text(json.dumps(report,indent=2))
    (args.run_dir/'execution_events.json').write_text(json.dumps(events,indent=2))
    if args.settle_steps:
        report['before_settling_simulator_success_for_evaluation']=report['final_simulator_success_for_evaluation']
        settling=[]
        for index in range(args.settle_steps):
            action=np.zeros(7);action[-1]=last_gripper_action[0]
            current=env.step(action)[0]
            if index%10==0 or index==args.settle_steps-1:
                settling.append(dict(step=env._anchor_control_steps,
                    finger_qpos=current['robot0_gripper_qpos'].tolist(),
                    simulator_success_for_evaluation=bool(env.check_success())))
        capture(current,'after_settling')
        report['settling_observations']=settling
        report['settling_steps']=args.settle_steps
        report['final_simulator_success_for_evaluation']=bool(env.check_success())
        (args.run_dir/'replay_result.json').write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k!='attempts'}),flush=True)
    if hasattr(env,'_anchor_close_vision'):env._anchor_close_vision()
    env.close()


if __name__=='__main__':main()
