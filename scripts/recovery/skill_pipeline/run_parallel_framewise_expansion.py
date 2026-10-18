"""Unattended parallel expansion of the frozen framewise RGB-D pipeline.

Uses saved recovery fixtures from the prior ten-task sample. Geometry support
is deliberately unchanged: unsupported categories are recorded as failures.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback


def dump(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def media(case):
    """Export available sensor frames, including failures before execution."""
    import numpy as np
    from PIL import Image
    frames = {}
    for path in (case/'snapshots').glob('recovery*/*/agentview/rgbd.npz'):
        meta = json.loads((path.parent/'metadata.json').read_text())
        with np.load(path) as data:
            frames[int(meta['env_step'])] = data['rgb'].copy()
    for path in (case/'resident_vision').glob('step*/rgb.png'):
        frames[int(path.parent.name[4:])] = np.asarray(Image.open(path).convert('RGB'))
    if not frames:
        return dict(status='no_sensor_frames')
    ordered = sorted(frames)
    Image.fromarray(frames[ordered[-1]]).save(case/'final_rgb.png')
    height, width = frames[ordered[0]].shape[:2]
    video = case/'recovery.mp4'
    with (case/'video_export.log').open('wb') as log:
        proc = subprocess.Popen(['/usr/bin/ffmpeg', '-y', '-loglevel', 'error',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{width}x{height}',
            '-r', '20', '-i', '-', '-an', '-c:v', 'libx264', '-threads', '1',
            '-preset', 'fast', '-crf', '21', '-pix_fmt', 'yuv420p',
            '-movflags', '+faststart', str(video)], stdin=subprocess.PIPE, stderr=log)
        try:
            for i, step in enumerate(ordered):
                count = ordered[i+1]-step if i+1 < len(ordered) else 20
                for _ in range(max(1, min(count, 200))):
                    proc.stdin.write(frames[step].tobytes())
            proc.stdin.close()
            rc = proc.wait(timeout=60)
        finally:
            if proc.poll() is None:
                proc.kill(); proc.wait()
    return dict(status='exported' if rc == 0 else 'export_failed',
        frames=len(ordered), first_step=ordered[0], last_step=ordered[-1],
        playback='20Hz simulation time; sparse gaps held; inference waits omitted',
        video=str(video), sha256=sha(video) if rc == 0 else None)


def classify(case, report, rc):
    if rc == 124:
        return 'timeout'
    if report.get('final_simulator_success_for_evaluation'):
        return 'simulator_success'
    logs = '\n'.join(p.read_text(errors='replace')[-16000:] for p in
        [case/'driver.log', *case.glob('visual_nomination_step*.log')] if p.exists())
    rules = [
        ('resource_oom', ['out of memory', 'CUDA error: out of memory']),
        ('language_unsupported', ['unsupported object phrase', 'unsupported task language', 'conflicting descriptions']),
        ('target_shape_unsupported', ['bottle fitting requires a visually nominated bottle']),
        ('support_shape_unsupported', ['goal fitting requires', 'plate fitting requires', 'support fitting requires']),
        ('binding_or_detection', ['current visual nomination was refused', 'no_target', 'missing_target', 'no_goal', 'missing_goal']),
        ('tracking', ['registration', 'identity gate', 'tracking lost']),
    ]
    for stage, terms in rules:
        if any(term.lower() in logs.lower() for term in terms):
            return stage
    if list((case/'cutamp_debug').glob('*.problem.json')):
        return 'planning_or_execution'
    return 'nomination_or_setup' if rc else 'recovery_unsuccessful'


def run_case(rec, batch, code, root, baseline, args):
    case = batch/rec['label']
    case.mkdir()
    started = time.time()
    record = dict(rec, state='preparing', started_unix=started)
    dump(case/'status.json', record)
    try:
        source = root/'logs/rgbd_ten_tasks_20261015'/rec['label']
        fixture = source/'oracle/replay_fixture'
        overlay = root/'logs/rgbd_static_box_fix_20261016/runtime_overlay'
        support = root/'logs/rgbd_framewise_20261016_replay03/bowl/capture_support'
        shutil.copytree(support, case/'capture_support')
        shutil.copy2(code/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py',
            case/'capture_support/visual_selection_oracle_geometry_hook.py')
        # Reuse the exact case-specific distractor selection, preserving the
        # detector protocol of the last batch rather than hiding hard objects.
        shutil.copy2(source/'visual/distractor_prompts.json', case/'distractor_prompts.json')
        from experiments.robot.libero.skill_pipeline.visual_language_prompts import prompts_from_task_language
        config = json.loads((root/'logs/rgbd_framewise_20261016_replay03/bowl_vision_config.json').read_text())
        try:
            config['prompts'] = prompts_from_task_language(rec['language'])
        except ValueError as error:
            config['prompts'] = {}
            record['language_preflight_error'] = str(error)
        dump(case/'vision_config.json', config)
        command = json.loads(json.dumps(baseline))
        env = command['env']
        old_code = env['ANCHOR_VISUAL_CODE']
        for key in ['DINO_INFERENCE_PYTHONPATH', 'ANCHOR_SEGMENTATION_PYTHONPATH']:
            env[key] = env[key].replace(old_code, str(code))
        env.update(ANCHOR_VISUAL_CODE=str(code), ANCHOR_CAPTURE_DIR=str(case/'snapshots'),
            ANCHOR_DIAGNOSTIC_HOOK=str(case/'capture_support/visual_selection_oracle_geometry_hook.py'),
            ANCHOR_FRAMEWISE_CONFIG=str(case/'vision_config.json'),
            ANCHOR_EPISODE_ID=f"{rec['suite']}:task{rec['task_1based']:02d}:ep{rec['episode_idx']:02d}",
            CUTAMP_FLOCK_LOCK=str(batch/'shared_planner.lock'), OMP_NUM_THREADS='1',
            OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1', NUMEXPR_NUM_THREADS='1',
            HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
        argv = command['argv']
        argv[1] = str(code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py')
        for flag, value in [('--fixture', fixture), ('--bddl', rec['bddl']), ('--run-dir', case)]:
            argv[argv.index(flag)+1] = str(value)
        dump(case/'command.json', command)
        inputs = [fixture/'config.json', fixture/'initial_physics_state.npy', Path(rec['bddl'])]
        dump(case/'input_manifest.json', dict(sha256={str(p):sha(p) for p in inputs},
            fixture=str(fixture), source=str(code), geometry_support_unchanged=True))
        with (case/'driver.log').open('wb') as log:
            proc = subprocess.Popen(argv, env=dict(os.environ, **env), cwd=overlay,
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            record.update(state='running', pid=proc.pid)
            dump(case/'status.json', record)
            try:
                rc = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                rc = 124
            finally:
                # Each case owns a session; clean only its workers, never
                # external simulations or other users' processes.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait()
        report = {}
        for name in ['replay_result.json', 'failure_result.json']:
            if (case/name).exists():
                report = json.loads((case/name).read_text())
                break
        record.update(state='finished', exit_code=rc, result=report,
            failure_stage=classify(case, report, rc),
            tracking_frames=len(list((case/'framewise_tracking').glob('step*.json'))))
        try:
            record['media'] = media(case)
        except Exception:
            record['media_error'] = traceback.format_exc()
    except Exception:
        record.update(state='launcher_error', error=traceback.format_exc())
    record['elapsed_sec'] = time.time()-started
    dump(case/'status.json', record)
    dump(case/'finished.json', record)
    return record


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, required=True)
    ap.add_argument('--batch', type=Path, required=True)
    ap.add_argument('--workers', type=int, default=4)
    ap.add_argument('--timeout', type=int, default=1800)
    args = ap.parse_args()
    root, batch = args.root, args.batch
    code = batch/'code'
    sys.path.insert(0, str(code))
    cases = json.loads((root/'logs/rgbd_ten_tasks_20261015/batch_manifest.json').read_text())['cases'][2:]
    baseline = json.loads((root/'logs/rgbd_framewise_20261016_replay03/bowl/command.json').read_text())
    for rec in cases:
        old = root/'logs/rgbd_ten_tasks_20261015'/rec['label']
        for p in [old/'oracle/replay_fixture/config.json', old/'oracle/replay_fixture/initial_physics_state.npy',
                  old/'visual/distractor_prompts.json', Path(rec['bddl'])]:
            assert p.is_file(), str(p)
    dump(batch/'batch_manifest.json', dict(cases=cases, workers=args.workers, timeout_sec=args.timeout,
        source=str(code), initial_shape_support='bottle; support plate/bowl; unchanged',
        planning_concurrency=1, evidence_scope='saved recovery-state replay; no policy reload; no truth geometry fallback',
        note='historically successful sample, not benchmark success rate'))
    results = []
    dump(batch/'batch_results.json', results)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(run_case, r, batch, code, root, baseline, args):r for r in cases}
        for future in as_completed(futures):
            rec = future.result()
            results.append(rec)
            dump(batch/'batch_results.json', results)
            with (batch/'summary.csv').open('w', newline='') as stream:
                writer = csv.writer(stream)
                writer.writerow(['label','language','exit_code','failure_stage','simulator_success','tracking_frames','elapsed_sec'])
                for r in results:
                    writer.writerow([r['label'],r['language'],r.get('exit_code'),r.get('failure_stage'),
                        r.get('result',{}).get('final_simulator_success_for_evaluation'),r.get('tracking_frames'),r['elapsed_sec']])
            print('FINISHED', rec['label'], rec.get('failure_stage',rec['state']), flush=True)
    dump(batch/'batch_finished.json', dict(finished_unix=time.time(), cases=len(results),
        simulator_success=sum(bool(r.get('result',{}).get('final_simulator_success_for_evaluation')) for r in results)))


if __name__ == '__main__':
    main()
