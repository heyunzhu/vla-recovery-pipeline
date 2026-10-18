"""Paired C3/C4 spatial-task evaluation; frozen runtime, independent artifacts."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

R = Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
H = R / 'logs/continual_skill_core60_pilot_20261006'
O = R / 'logs/continual_skill_spatial50_20261011'
REPO = H / 'runtime_repo'
PY = R / 'envs/rlinf-openpi/bin/python'
COMMIT = '7128c1ea6280c227e48561e621fe9da8604c5a6d'
PACKS = {'C3': 'libero_spatial_swap_from_goal_task_mining_base_20260916',
         'C4': 'libero_object_task_from_spatial_swap_mining_base_20260918'}
INFRA = ('runner_failed:', 'No such file or directory', 'ModuleNotFoundError', 'Traceback')


def digest(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def frozen_hashes():
    assert subprocess.check_output(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
    hashes = {}
    for line in (H / 'checkpoint_sha256.txt').read_text().splitlines():
        expected, name = line.split(None, 1)
        p = Path(name.strip())
        if any(pack in p.parts for pack in PACKS.values()):
            assert digest(p) == expected, f'Frozen pack mismatch: {p}'
            hashes[str(p)] = expected
    assert len(hashes) == 94
    for p in [H / 'core60_entrypoint.py', H / 'cutamp_flock.sh', H / 'libero_config/config.yaml']:
        hashes[str(p)] = digest(p)
    for p in sorted(REPO.rglob('*.py')):
        if '.git' not in p.parts and '__pycache__' not in p.parts:
            hashes[str(p)] = digest(p)
    for p in sorted((H / 'init_files/libero_spatial_task').glob('*.pruned_init')):
        hashes[str(p)] = digest(p)
    for p in sorted((H / 'bddl_files/libero_spatial_task').glob('*.bddl')):
        hashes[str(p)] = digest(p)
    return hashes


def verify():
    m = json.loads((O / 'manifest.json').read_text())
    assert frozen_hashes() == m['frozen_hashes'], 'Frozen assets changed'
    assert digest(__file__) == m['launcher_sha256'], 'Launcher changed'
    assert digest(O / 'libero_config/config.yaml') == m['config_sha256']
    return m


def prepare():
    import torch
    import yaml
    hashes = frozen_hashes()
    c = yaml.safe_load((H / 'libero_config/config.yaml').read_text())
    tasks = []
    for i, p in enumerate(sorted((Path(c['bddl_files']) / 'libero_spatial_task').glob('*.bddl')), 1):
        initial = Path(c['init_states']) / 'libero_spatial_task' / (p.stem + '.pruned_init')
        count = len(torch.load(initial, map_location='cpu', weights_only=False))
        assert count == 50, (i, count)
        tasks.append({'task': i, 'name': p.stem, 'init_count': count,
                      'initial_file': str(initial), 'initial_sha256': digest(initial),
                      'bddl_file': str(p), 'bddl_sha256': digest(p)})
    assert len(tasks) == 10
    jobs = [{'id': f'{condition}_t{task:02d}', 'condition': condition, 'task': task,
             'pack': str(H / 'checkpoints' / PACKS[condition]), 'lane': (2 * (task - 1) + k) % 4}
            for task in range(1, 11) for k, condition in enumerate(PACKS)]
    m = {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
         'runtime_commit': COMMIT, 'frozen_hashes': hashes,
         'launcher_sha256': digest(__file__), 'config_sha256': digest(H / 'libero_config/config.yaml'),
         'jobs': jobs, 'tasks': tasks, 'episodes_per_task': 50, 'total_episodes': 1000,
         'episode_seed_start': 1, 'policy_seed': 90,
         'sample_pairs': [{'episode_idx': i, 'seed': i + 1, 'init_state_idx': i} for i in range(50)],
         'protocol': 'Natural mining trigger; 2 recovery calls, 200 recovery steps, 1 replan; no training or skill edits. Expanded paired evaluation, not fixed-state execution-only variance.'}
    if (O / 'manifest.json').exists():
        return verify()
    (O / 'libero_config').mkdir(parents=True, exist_ok=True)
    with (O / 'libero_config/config.yaml').open('x') as f:
        f.write((H / 'libero_config/config.yaml').read_text())
    with (O / 'manifest.json').open('x') as f:
        json.dump(m, f, indent=2)
    return m


def completed(job):
    found = {}
    for attempt in sorted((O / 'attempts' / job['id']).glob('*')):
        cmdfile = attempt / 'command.json'
        if not cmdfile.exists():
            continue
        record = json.loads(cmdfile.read_text())
        assert record['launcher_sha256'] == digest(__file__)
        for p in sorted(attempt.glob(f"run/task{job['task']:02d}/ep*/episode.json")):
            try:
                e = json.loads(p.read_text())
                qs = [json.loads(l) for l in (p.parent / 'query_trace.jsonl').read_text().splitlines()]
                rs = [json.loads(l) for l in (p.parent / 'recovery_trace.jsonl').read_text().splitlines()]
            except json.JSONDecodeError:
                continue
            i = int(p.parent.name[2:])
            assert 0 <= i < 50 and e.get('seed') == i + 1 and e.get('init_state_idx') == i
            assert isinstance(e.get('success'), bool)
            assert (p.parent / 'video.mp4').stat().st_size > 0
            assert not any(any(s in str(r.get('error') or '') for s in INFRA) for r in rs), f'Infrastructure invalid: {p}'
            assert qs, f'Missing query trace: {p}'
            found.setdefault(i, str(p))
    return found


def command(job, attempt, start, count):
    return [str(PY), str(H / 'core60_entrypoint.py'),
            '--pretrained_path', str(R / 'models/pi0_libero_openpi'), '--config_name', 'pi0_libero',
            '--task_suite_name', 'libero_spatial_task', '--task_ids', str(job['task']),
            '--num_trials_per_task', str(count), '--episode_seed_start', '1',
            '--episode_index_start', str(start), '--seed', '90', '--policy_in_process', '--save_video',
            '--openvla_repo_root', str(REPO), '--task_language_source', 'bddl', '--engine_language_source', 'bddl',
            '--max_recovery_calls', '2', '--max_recovery_steps', '200', '--max_replans', '1',
            '--log_dir', str(attempt), '--exp_name', 'run', '--enable_mining_skills', '--skill_pack', job['pack'],
            '--use_real_cutamp_backend', '--real_cutamp_require_feasible', '--real_cutamp_curobo_plan',
            '--real_cutamp_serialize_trajectories', '--prefer_real_cutamp_executable_plan',
            '--require_real_cutamp_executable_plan', '--real_cutamp_grasp_dof', '6',
            '--real_cutamp_runner_python', str(H / 'cutamp_flock.sh'), '--real_cutamp_runner_timeout_sec', '900',
            '--real_cutamp_debug_dir', str(attempt / 'cutamp_debug')]


def lane(m, k, session):
    env = dict(os.environ, ROOT=str(R), CUDA_VISIBLE_DEVICES='0', MUJOCO_GL='egl', PYOPENGL_PLATFORM='egl',
               LIBERO_CONFIG_PATH=str(O / 'libero_config'), XLA_PYTHON_CLIENT_PREALLOCATE='false',
               XLA_PYTHON_CLIENT_MEM_FRACTION='0.50', PYTHONPATH=f'{REPO}:{R / "third_party/LIBERO-PRO"}',
               OMP_NUM_THREADS='2', CUTAMP_FLOCK_LOCK=str(O / 'cutamp.lock'),
               CUTAMP_REAL_RUNNER=str(REPO / 'scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh'))
    for job in m['jobs']:
        if job['lane'] != k:
            continue
        missing = [i for i in range(50) if i not in completed(job)]
        while missing:
            start = missing[0]
            end = start + 1
            while end in missing:
                end += 1
            d = O / 'attempts' / job['id'] / f'{session}_from{start:02d}'
            d.mkdir(parents=True)
            cmd = command(job, d, start, end - start)
            (d / 'command.json').write_text(json.dumps({'command': cmd, 'launcher_sha256': digest(__file__)}, indent=2))
            print('RUN', job['id'], start, end, flush=True)
            with (d / 'driver.log').open('w') as f:
                rc = subprocess.call(cmd, env=env, stdout=f, stderr=subprocess.STDOUT)
            (d / 'exit_code.json').write_text(json.dumps(rc))
            if rc:
                (d / '.failed').write_text(str(rc))
                raise RuntimeError(f'{job["id"]}: nonzero exit {rc}; no automatic retry')
            done = completed(job)
            assert all(i in done for i in range(start, end)), 'Incomplete successful attempt'
            missing = [i for i in range(50) if i not in done]
        print('DONE', job['id'], flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['prepare', 'start', 'lane', 'status'])
    p.add_argument('--lane', type=int)
    p.add_argument('--session')
    a = p.parse_args()
    if a.mode == 'prepare':
        m = prepare()
        print(json.dumps({'prepared': str(O), 'jobs': len(m['jobs']), 'episodes': 1000}))
        return
    m = verify()
    if a.mode == 'lane':
        lane(m, a.lane, a.session)
        return
    if a.mode == 'status':
        index = {j['id']: completed(j) for j in m['jobs']}
        print(json.dumps({'completed': sum(map(len, index.values())), 'expected': 1000,
                          'jobs': {k: len(v) for k, v in index.items()},
                          'all_done': (O / 'all.done').exists()}, indent=2))
        return
    with (O / 'master.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        session = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '_' + uuid.uuid4().hex[:6]
        d = O / 'sessions' / session
        d.mkdir(parents=True)
        (O / 'active_session.json').write_text(json.dumps({'session': session, 'pid': os.getpid()}))
        children = []
        handles = []
        for k in range(4):
            f = (d / f'lane{k}.log').open('w')
            handles.append(f)
            proc = subprocess.Popen([str(PY), str(O / 'launch_spatial50.py'), 'lane', '--lane', str(k), '--session', session], stdout=f, stderr=subprocess.STDOUT)
            children.append(proc)
            (d / f'lane{k}.pid').write_text(str(proc.pid))
            print('STARTED', k, proc.pid, flush=True)
        codes = [p.wait() for p in children]
        for f in handles:
            f.close()
        (d / 'exit_codes.json').write_text(json.dumps(codes))
        assert not any(codes), f'Lane error: {codes}'
        index = {j['id']: completed(j) for j in m['jobs']}
        assert all(len(v) == 50 for v in index.values())
        (O / 'completed_index.json').write_text(json.dumps(index, indent=2))
        (O / 'all.done').write_text('1000 validated episodes\n')


if __name__ == '__main__':
    main()
