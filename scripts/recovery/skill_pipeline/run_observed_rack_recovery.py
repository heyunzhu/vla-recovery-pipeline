"""Isolated three-candidate RGB-D rack recovery experiment."""
import argparse,json,os,shutil,subprocess,signal,time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);p.add_argument('--run',type=Path,required=True)
    p.add_argument('--collision-policy',choices=['strict','oracle_cheese_rack_contacts_v1'],default='strict')
    p.add_argument('--tracking-gap-steps',type=int,default=0)
    p.add_argument('--release-pose-constraint',action='store_true')
    p.add_argument('--wrist-fallback',action='store_true')
    p.add_argument('--rack-skill',action='store_true',help='Bind saved rack placement skill to the current RGB-D upper plane')
    p.add_argument('--occlusion-aware-tracking',action='store_true')
    p.add_argument('--plane-ids',nargs='+')
    p.add_argument('--tracking-gap-seconds',type=float,default=.5);args=p.parse_args()
    root,run=args.root,args.run;code=run/'code';overlay=run/'runtime_overlay'
    import sys
    sys.path.insert(0,str(code))
    import numpy as np
    from experiments.robot.libero.skill_pipeline.visual_inclined_support import canonical_box,support_candidates
    audit=root/'logs/rgbd_box_geometry_20261016/audit'
    target=canonical_box(json.loads((audit/'fused_target.json').read_text()))
    planes=support_candidates(np.load(audit/'observed_points.npz')['support_world'],target)
    if args.plane_ids:
        planes=[plane for plane in planes if plane['id'] in args.plane_ids]
        if {plane['id'] for plane in planes}!=set(args.plane_ids):raise ValueError('unknown requested observed plane')
    (run/'visual_candidates.json').write_text(json.dumps(planes,indent=2))
    original=root/'logs/rgbd_ten_tasks_20261015/03_goal_cheese_rack/oracle/replay_fixture'
    fixture=run/'fixture';fixture.mkdir()
    shutil.copy2(original/'initial_physics_state.npy',fixture/'initial_physics_state.npy')
    meta=json.loads((original/'config.json').read_text());hints=meta['recovery_hints']
    meta['recovery_hints']=dict(params=dict(executor=hints['params']['executor'],
        _grasp_profile_adapter_path=hints['params']['_grasp_profile_adapter_path']),
        grasp_profile=hints['grasp_profile'],target='target')
    meta['controller_config']['real_cutamp_cfg']['apply_simulator_truth_initial_state']=False
    meta['controller_config']['max_replans']=0
    (fixture/'config.json').write_text(json.dumps(meta,indent=2))
    preflight=("import sys,json;import experiments.robot.libero.skill_pipeline as p;"
        "p.__path__.insert(0,"+repr(str(code/'experiments/robot/libero/skill_pipeline'))+");"
        "from experiments.robot.libero.tiptop_repro.scene_reader import ObjectState;"
        "from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackendConfig;"
        "RealCuTAMPBackendConfig(**json.load(open("+repr(str(fixture/'config.json'))+"))['controller_config']['real_cutamp_cfg']);"
        "from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper;"
        "from experiments.robot.libero.skill_pipeline.robot_surface_ownership import augment_robot_surface_ownership;"
        "from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import FramewiseRGBDTracker;"
        "print('Frozen runtime and sensor-hook imports passed')")
    with (run/'runtime_contract.log').open('wb') as log:
        check=subprocess.run([str(root/'envs/rlinf-openpi/bin/python'),'-c',preflight],
            cwd=overlay,env=dict(os.environ,PYTHONPATH=str(overlay)+':'+str(code)),
            stdout=log,stderr=subprocess.STDOUT,timeout=120)
    if check.returncode:
        raise RuntimeError('runtime contract check failed: '+(run/'runtime_contract.log').read_text())
    base=json.loads((root/'logs/rgbd_framewise_20261016_replay03/bowl/command.json').read_text())
    vision=json.loads((root/'logs/rgbd_framewise_20261016_replay03/bowl_vision_config.json').read_text());vision['prompts']=dict(cheese='cream cheese',rack='rack')
    vision['prompts'].update(json.loads((root/'logs/rgbd_ten_tasks_20261015/03_goal_cheese_rack/visual/distractor_prompts.json').read_text()))
    bddl=root/'logs/continual_skill_core60_pilot_20261006/bddl_files/libero_goal_task/put_the_wine_bottle_on_the_rack.bddl'
    def replay(plane):
        case=run/plane['id'];case.mkdir()
        support=root/'logs/rgbd_framewise_20261016_replay03/bowl/capture_support'
        shutil.copytree(support,case/'capture_support')
        shutil.copy2(code/'scripts/recovery/skill_pipeline/observed_geometry_recovery_hook.py',case/'capture_support/observed_geometry_recovery_hook.py')
        cfg=dict(plane=dict(id=plane['id']),vision=vision,collision_policy=args.collision_policy,
                 rack_skill=hints if args.rack_skill else None,
                 occlusion_aware_tracking=args.occlusion_aware_tracking,
                 release_pose_constraint=args.release_pose_constraint,wrist_fallback=args.wrist_fallback,
                 tracking_short_gap=dict(max_missing_steps=args.tracking_gap_steps,max_missing_seconds=args.tracking_gap_seconds),
                 geometry_source='fresh_RGBD_after_entry; saved_audit_only_enumerates_candidate_ranks')
        (case/'observed_config.json').write_text(json.dumps(cfg,indent=2))
        e=base['env'].copy();old=e['ANCHOR_VISUAL_CODE']
        for k in ['DINO_INFERENCE_PYTHONPATH','ANCHOR_SEGMENTATION_PYTHONPATH']:e[k]=e[k].replace(old,str(code))
        e.update(ANCHOR_VISUAL_CODE=str(code),OVERLAY_ROOT=str(overlay),
            PYTHONPATH=str(overlay)+':'+str(root/'third_party/LIBERO-PRO')+':'+str(code),
            ANCHOR_DIAGNOSTIC_HOOK=str(case/'capture_support/observed_geometry_recovery_hook.py'),
            ANCHOR_CAPTURE_DIR=str(case/'snapshots'),ANCHOR_EPISODE_ID=meta['episode_id'],
            ANCHOR_OBSERVED_PLACEMENT_CONFIG=str(case/'observed_config.json'),
            CUTAMP_FLOCK_LOCK=str(run/'planner.lock'),OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1')
        argv=[str(root/'envs/rlinf-openpi/bin/python'),str(code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py'),
            '--fixture',str(fixture),'--bddl',str(bddl),'--run-dir',str(case),'--capture-every','5',
            '--camera-resolution','640','--restore-open-gripper-command','--evaluation-done-only','--settle-steps','60']
        (case/'command.json').write_text(json.dumps(dict(argv=argv,env=e),indent=2))
        start=time.time()
        with (case/'driver.log').open('wb') as log:
            proc=subprocess.Popen(argv,env=dict(os.environ,**e),cwd=overlay,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            (case/'launch.json').write_text(json.dumps(dict(pid=proc.pid,started=start)))
            try:rc=proc.wait(timeout=900)
            except subprocess.TimeoutExpired:rc=124
            finally:
                try:os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError:pass
                proc.wait()
        result=dict(plane=plane['id'],exit_code=rc,elapsed=time.time()-start)
        for name in ['replay_result.json','failure_result.json']:
            if (case/name).exists():result[name]=json.loads((case/name).read_text())
        (case/'finished.json').write_text(json.dumps(result,indent=2));return result
    results=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for future in as_completed([pool.submit(replay,plane) for plane in planes]):
            results.append(future.result());(run/'progress.json').write_text(json.dumps(results,indent=2));print('FINISHED',results[-1]['plane'],results[-1]['exit_code'],flush=True)
    (run/'finished.json').write_text(json.dumps(results,indent=2))

if __name__=='__main__':main()
