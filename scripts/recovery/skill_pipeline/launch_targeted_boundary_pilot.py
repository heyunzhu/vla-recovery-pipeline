"""Scoped supervisor for small physical skill-boundary pilots, frozen C4 runtime."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
C=R/'logs/continual_skill_core60_pilot_20261006'
O=R/'logs/skill_boundary_pilot_20261010'
PY=R/'envs/rlinf-openpi/bin/python'


def command(job, directory, trials):
    args=[str(PY),str(O/'targeted_boundary_entrypoint.py'),
        '--pretrained_path',str(R/'models/pi0_libero_openpi'),'--config_name','pi0_libero',
        '--task_suite_name','libero_object_task','--task_ids',str(job['task']),
        '--num_trials_per_task',str(trials),'--episode_seed_start','1','--seed','90',
        '--policy_in_process','--save_video','--openvla_repo_root',str(C/'runtime_repo'),
        '--task_language_source','bddl','--engine_language_source','bddl',
        '--max_recovery_calls','1' if job['panel']=='grasp' else '2',
        '--max_recovery_steps','200','--max_replans','1','--log_dir',str(directory),'--exp_name','run',
        '--enable_mining_skills','--skill_pack',str(C/'checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918'),
        '--use_real_cutamp_backend','--real_cutamp_require_feasible','--real_cutamp_curobo_plan',
        '--real_cutamp_serialize_trajectories','--prefer_real_cutamp_executable_plan',
        '--require_real_cutamp_executable_plan','--real_cutamp_grasp_dof','6',
        '--real_cutamp_runner_python',str(R/'logs/pro_object_batch_20261004_mrs200/cutamp_flock.sh'),
        '--real_cutamp_runner_timeout_sec','900','--real_cutamp_debug_dir',str(directory/'cutamp_debug')]
    if job['panel']=='grasp':
        args += ['--force_recovery_query','0']
    return args


def run(job, directory, trials):
    directory.mkdir(parents=True,exist_ok=True)
    if (directory/'.done').exists():
        return
    if (directory/'run').exists():
        raise RuntimeError('refusing to overwrite existing episode logs: '+str(directory))
    cfg=directory/'boundary_config.json'
    cfg.write_text(json.dumps(job['config'],indent=2))
    env=dict(os.environ,ROOT=str(R),CUDA_VISIBLE_DEVICES='0',MUJOCO_GL='egl',PYOPENGL_PLATFORM='egl',
        LIBERO_CONFIG_PATH=str(C/'libero_config'),XLA_PYTHON_CLIENT_PREALLOCATE='false',
        XLA_PYTHON_CLIENT_MEM_FRACTION='0.20',PYTHONPATH=str(C/'runtime_repo')+':'+str(R/'third_party/LIBERO-PRO'),
        OMP_NUM_THREADS='2',CUTAMP_FLOCK_LOCK=str(O/'cutamp.lock'),
        CUTAMP_REAL_RUNNER=str(C/'runtime_repo/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh'),
        BOUNDARY_CONFIG=str(cfg),BOUNDARY_AUDIT=str(directory/'init_audit.jsonl'))
    argv=command(job,directory,trials)
    source_hash=hashlib.sha256((O/'targeted_boundary_entrypoint.py').read_bytes()).hexdigest()
    (directory/'command.json').write_text(json.dumps(dict(argv=argv,entrypoint_sha256=source_hash,env={k:env[k] for k in ['ROOT','LIBERO_CONFIG_PATH','PYTHONPATH','CUTAMP_FLOCK_LOCK','CUTAMP_REAL_RUNNER','BOUNDARY_CONFIG','BOUNDARY_AUDIT']}),indent=2))
    with (directory/'driver.log').open('w') as handle:
        process=subprocess.Popen(argv,env=env,cwd=str(C/'runtime_repo'),stdout=handle,stderr=subprocess.STDOUT)
        (directory/'eval.pid').write_text(str(process.pid))
        rc=process.wait()
    (directory/'exit_code').write_text(str(rc))
    if rc:
        (directory/'.failed').write_text(str(rc))
        raise RuntimeError('job failed: '+job['id'])
    eps=list((directory/'run').glob('task*/ep*/episode.json'))
    assert len(eps)==trials,(job['id'],len(eps),trials)
    for ep in eps:
        trace=ep.parent/'recovery_trace.jsonl'
        if trace.exists():
            for line in trace.read_text().splitlines():
                row=json.loads(line)
                error=str(row.get('error') or '')
                if any(s in error for s in ('runner_failed:','No such file or directory','ModuleNotFoundError','Traceback')):
                    (directory/'.infrastructure_invalid').write_text(error)
                    raise RuntimeError('infrastructure invalid: '+job['id']+': '+error[:400])
    (directory/'.done').write_text('completed\n')


def plan():
    jobs=[]
    for task,target,blocker in [(1,'cream_cheese_1','milk_1'),(7,'butter_1','milk_1'),(8,'chocolate_pudding_1','orange_juice_1')]:
        variants=[('original',{}),('thin075',{'thickness_factor':.75}),('thick125',{'thickness_factor':1.25}),
                  ('gap015',{'blocker':blocker,'side_gap_m':.015}),('gap050',{'blocker':blocker,'side_gap_m':.05})]
        for variant,extra in variants:
            for arm in ('specialized','generic'):
                jobs.append(dict(id=f'A_t{task:02d}_{variant}_{arm}',panel='grasp',task=task,config=dict(target=target,profile_arm=arm,**extra)))
    for task,target in [(1,'cream_cheese_1'),(9,'tomato_sauce_1')]:
        for shift in (-.04,0.,.04):
            cfg=dict(target=target)
            if shift:
                cfg.update(blocker='milk_1',blocker_radial_shift_m=shift)
            jobs.append(dict(id=f'B_t{task:02d}_shift{shift:+.2f}',panel='trigger',task=task,config=cfg))
    return jobs


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['prepare','canary','lane','start'])
    p.add_argument('--lane',type=int,default=0)
    p.add_argument('--lanes',type=int,default=2)
    a=p.parse_args()
    O.mkdir(parents=True,exist_ok=True)
    if a.mode=='prepare':
        head=subprocess.check_output(['git','-C',str(C/'runtime_repo'),'rev-parse','HEAD'],text=True).strip()
        assert head=='7128c1ea6280c227e48561e621fe9da8604c5a6d'
        files={str(f.relative_to(O)):hashlib.sha256(f.read_bytes()).hexdigest() for f in O.glob('*.py')}
        pack=C/'checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918'
        hashes={str(f.relative_to(pack)):hashlib.sha256(f.read_bytes()).hexdigest() for f in pack.rglob('*') if f.is_file()}
        (O/'manifest.json').write_text(json.dumps(dict(code_head=head,pack=str(pack),pack_sha256=hashes,overlay_sha256=files,
            jobs=plan(),trials_per_job=5,pilot_episodes=180,trigger_forced_replay='not yet implemented; natural arm first'),indent=2))
        print('prepared',len(plan()),'jobs,180 episodes')
    elif a.mode=='canary':
        for job in (plan()[0],plan()[2]):
            run(job,O/'canary_v2'/job['id'],1)
        (O/'canary_v2.done').write_text('2 original/thickness startup episodes completed\n')
    elif a.mode=='lane':
        assert (O/'canary_v2.done').exists()
        jobs=json.loads((O/'manifest.json').read_text())['jobs']
        for i,job in enumerate(jobs):
            if i%a.lanes==a.lane:
                run(job,O/'jobs'/job['id'],5)
        (O/f'lane{a.lane}.done').write_text('completed\n')
    else:
        assert (O/'canary_v2.done').exists()
        for lane in range(a.lanes):
            pid=O/f'lane{lane}.pid'
            if pid.exists():
                raise RuntimeError('lane already started; inspect before retry')
            with (O/f'lane{lane}.log').open('w') as log:
                process=subprocess.Popen([str(PY),str(O/'launch_targeted_boundary_pilot.py'),'lane','--lane',str(lane),'--lanes',str(a.lanes)],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            pid.write_text(str(process.pid))
            print('lane',lane,'pid',process.pid)


if __name__=='__main__':
    main()
