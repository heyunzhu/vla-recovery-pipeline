"""Resume-safe full Core-60 sweep: six panels, ten tasks, five episodes."""
import argparse
from concurrent.futures import ThreadPoolExecutor,as_completed
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import traceback
from collections import Counter


def dump(path,data):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(data,indent=2));temporary.replace(path)


def failure_stage(error):
    text=str(error).lower()
    for label,terms in [
        ('resource_oom',['out of memory','cuda error: memory']),
        ('unsupported_language',['unsupported task language','unsupported object phrase','conflicting descriptions']),
        ('binding_detection',['visual binding refused','ambiguous or missing','same-category target']),
        ('target_geometry',['target geometry unresolved','observed cuboid','segmented target depth']),
        ('support_geometry',['no observed support candidate','no observed near_horizontal']),
        ('tracking',['registration','reacquisition','identity ambiguous']),
        ('infrastructure',['modulenotfounderror','importerror','shared policy','vision worker exited','vision worker response timed out','traceback'])]:
        if any(term in text for term in terms):return label
    return 'planning_or_execution'


def run_case(record,root,run,timeout):
    try:return _run_case(record,root,run,timeout)
    except Exception:
        case=run/'cases'/record['case_id'];case.mkdir(parents=True,exist_ok=True)
        outcome=dict(record=record,case_id=record['case_id'],valid_episode=False,success=None,
            recoveries=[],launcher_error=traceback.format_exc(),exit_code=-1)
        dump(case/'finished.json',outcome);dump(case/'status.json',dict(state='finished',**outcome))
        return outcome


def _run_case(record,root,run,timeout):
    case=run/'cases'/record['case_id']
    if (case/'finished.json').exists():return json.loads((case/'finished.json').read_text())
    if case.exists():
        archive=run/'interrupted'/f"{record['case_id']}_{time.time_ns()}";archive.parent.mkdir(exist_ok=True)
        case.rename(archive)
    case.mkdir(parents=True)
    code=run/'code';overlay=run/'runtime_overlay';hist=root/'logs/continual_skill_core60_pilot_20261006'
    base=json.loads((root/'logs/rgbd_partial_tracking_20261017/plane_00/command.json').read_text())['env']
    env={k:v for k,v in base.items() if not k.startswith('ANCHOR_')}
    env.update(ROOT=str(root),OVERLAY_ROOT=str(overlay),ANCHOR_VISUAL_CODE=str(code),
        PYTHONPATH=':'.join(map(str,[overlay,root/'third_party/LIBERO-PRO',code,run/'sensor_support'])),
        LIBERO_CONFIG_PATH=str(hist/'libero_config'),ORACLE_ENTRYPOINT=str(hist/'core60_entrypoint.py'),
        RGBD_CASE_DIR=str(case),RGBD_SENSOR_SUPPORT=str(run/'sensor_support'),RGBD_VISION_CONFIG=str(run/'vision_config.json'),
        RGBD_POLICY_ENDPOINT=str(run/'policy_endpoint.json'),RGBD_EPISODE_SEED=str(record['policy_seed']),
        ANCHOR_EPISODE_ID=record['case_id'],ANCHOR_VISUAL_IDS='1',ANCHOR_RGBD_OBSTACLES='1',
        ANCHOR_PROPRIO_HAND_STATE='1',ANCHOR_VISUAL_EXECUTOR='1',
        ANCHOR_SEGMENTATION_PYTHON=str(root/'envs/tiptop-planning-py310/bin/python'),
        ANCHOR_SEGMENTATION_PYTHONPATH=str(root/'logs/rgbd_exact_box_20261008/pydeps')+':'+str(code),
        CUTAMP_FLOCK_LOCK=str(run/'native_planner.lock'),
        CUTAMP_REAL_RUNNER=str(overlay/'scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh'),
        CUDA_VISIBLE_DEVICES='0',MUJOCO_GL='egl',PYOPENGL_PLATFORM='egl',
        XLA_PYTHON_CLIENT_PREALLOCATE='false',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',
        HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
    old=base.get('DINO_INFERENCE_PYTHONPATH','')
    if old:env['DINO_INFERENCE_PYTHONPATH']=old.replace(base['ANCHOR_VISUAL_CODE'],str(code))
    overrides=run/'worker_env.json'
    if overrides.exists():env.update(json.loads(overrides.read_text()))
    pack=hist/'checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918'
    argv=[str(root/'envs/rlinf-openpi/bin/python'),str(code/'scripts/recovery/skill_pipeline/rgbd_core60_entrypoint.py'),
        '--pretrained_path',str(root/'models/pi0_libero_openpi'),'--config_name','pi0_libero',
        '--task_suite_name',record['suite'],'--task_ids',str(record['task_1based']),
        '--num_trials_per_task','1','--episode_index_start',str(record['episode_idx']),
        '--episode_seed_start','1','--seed','90','--policy_in_process','--save_video',
        '--openvla_repo_root',str(overlay),'--task_language_source','bddl','--engine_language_source','bddl',
        '--max_recovery_calls','2','--max_recovery_steps','200','--max_replans','1',
        '--log_dir',str(case),'--exp_name','run','--enable_mining_skills','--skill_pack',str(pack),
        '--use_real_cutamp_backend','--real_cutamp_require_feasible','--real_cutamp_curobo_plan',
        '--real_cutamp_serialize_trajectories','--prefer_real_cutamp_executable_plan',
        '--require_real_cutamp_executable_plan','--real_cutamp_grasp_dof','6',
        '--real_cutamp_runner_python',str(hist/'cutamp_flock.sh'),'--real_cutamp_runner_timeout_sec','900',
        '--real_cutamp_debug_dir',str(case/'cutamp_debug')]
    dump(case/'command.json',dict(argv=argv,env=env))
    started=time.time();dump(case/'status.json',dict(state='starting',record=record))
    with (case/'driver.log').open('wb') as log:
        process=subprocess.Popen(argv,env=dict(os.environ,**env),cwd=overlay,
            stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        dump(case/'status.json',dict(state='running',pid=process.pid,started_unix=started,record=record))
        try:rc=process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:rc=124
        finally:
            try:os.killpg(process.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            process.wait()
    episodes=list((case/'run').glob('task*/ep*/episode.json'))
    episode=json.loads(episodes[0].read_text()) if episodes else None
    recoveries=[]
    for p in sorted(case.glob('recovery*/result.json')):
        r=json.loads(p.read_text());recoveries.append(dict(path=str(p),success=r['success'],
            completion_source=r.get('completion_source'),error=r.get('error'),
            failure_stage=failure_stage(r['error']) if r.get('error') else ('success' if r['success'] else 'planning_or_execution'),
            control_steps=r.get('end_control_step',0)-r.get('start_control_step',0)))
    outcome=dict(record=record,exit_code=rc,elapsed_sec=time.time()-started,
        valid_episode=episode is not None,success=episode.get('success') if episode else None,
        episode_path=str(episodes[0]) if episodes else None,recovery_calls=episode.get('recovery_calls') if episode else None,
        recoveries=recoveries,case_id=record['case_id'])
    if not episode:outcome['launcher_error']=(case/'driver.log').read_text(errors='replace')[-5000:]
    dump(case/'finished.json',outcome);dump(case/'status.json',dict(state='finished',**outcome))
    return outcome


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--run',type=Path,required=True)
    ap.add_argument('--workers',type=int,default=2);ap.add_argument('--timeout',type=int,default=2400)
    ap.add_argument('--expected-cases',type=int,default=300)
    args=ap.parse_args();run=args.run;records=json.loads((run/'requested_cases.json').read_text())
    assert len(records)==args.expected_cases and len({r['case_id'] for r in records})==args.expected_cases
    results={p.parent.name:json.loads(p.read_text()) for p in (run/'cases').glob('*/finished.json')}
    def save():
        panels={suite:dict(requested=count,completed=0,valid=0,successes=0) for suite,count in Counter(r['suite'] for r in records).items()}
        for r in results.values():
            panel=panels[r['record']['suite']];panel['completed']+=1
            panel['valid']+=bool(r['valid_episode']);panel['successes']+=bool(r['success'])
        dump(run/'progress.json',dict(requested=len(records),completed=len(results),workers=args.workers,panels=panels,
            running=[json.loads(p.read_text()) for p in (run/'cases').glob('*/status.json') if json.loads(p.read_text()).get('state')=='running']))
        dump(run/'batch_results.json',list(results.values()))
    # Two startup cases exercise a known recovery and a different suite before
    # allowing the remaining queue to consume GPU time.
    probes=['libero_goal_task_task08_ep00','libero_object_task_task01_ep00']
    config=run/'batch_config.json'
    if config.exists():probes=json.loads(config.read_text()).get('startup_cases',probes)
    ordered=sorted(records,key=lambda r:(0 if r['case_id'] in probes else 1,r['episode_idx'],r['task_1based'],r['suite']))
    pending=[r for r in ordered if r['case_id'] not in results]
    save()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        gate=[r for r in pending if r['case_id'] in probes]
        if gate:
            futures=[pool.submit(run_case,r,args.root,run,args.timeout) for r in gate]
            for future in as_completed(futures):
                r=future.result();results[r['case_id']]=r;save();print('PROBE_FINISHED',r['case_id'],r['valid_episode'],flush=True)
                if not r['valid_episode'] or any(x['failure_stage'] in ('resource_oom','infrastructure') for x in r['recoveries']):
                    dump(run/'startup_blocked.json',r);return
        dump(run/'startup_gate_passed.json',dict(cases=probes))
        remaining=[r for r in pending if r['case_id'] not in results]
        futures={pool.submit(run_case,r,args.root,run,args.timeout):r for r in remaining}
        for future in as_completed(futures):
            r=future.result();results[r['case_id']]=r;save();print('FINISHED',r['case_id'],r['success'],flush=True)
    save();dump(run/'finished.json',dict(completed=len(results),successes=sum(bool(r['success']) for r in results.values())))
    launch=json.loads((run/'policy_launch.json').read_text())
    try:os.killpg(launch['pid'],signal.SIGTERM)
    except ProcessLookupError:pass


if __name__=='__main__':main()
