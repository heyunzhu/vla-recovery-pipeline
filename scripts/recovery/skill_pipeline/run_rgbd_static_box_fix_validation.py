"""Validate measured occupancy-cell dimensions on frozen RGB-D recovery replays.

Creates isolated copies; never updates a historical runtime or reference run.
Uses the reference detector, simulator checkpoint and controller configuration.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import traceback


BACKEND = Path('experiments/robot/libero/tiptop_repro/real_cutamp_backend.py')
INSERT = '''    if obj.role == "static" and obj.geometry.get("source") == "rgbd_observed_anchor_obstacles":
        # These are measured occupancy cells, including their sensor padding.
        # The object proxy size floor would inflate walls into free space.
        return [2.0 * float(value) for value in he]
'''
ANCHOR = '''    he = _half_extents_xyz(obj)
    return [
        max(cfg.object_min_dim, 2.0 * float(he[0])),'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def patch_backend(path):
    source = path.read_text()
    assert source.count(ANCHOR) == 1, str(path)
    source = source.replace(ANCHOR, ANCHOR.replace('    return [\n', INSERT+'    return [\n', 1))
    compile(source, str(path), 'exec')
    path.write_text(source)


def replay(reference, destination, code, overlay):
    command = json.loads((reference/'command.json').read_text())
    destination.mkdir(exist_ok=False)
    shutil.copytree(reference/'capture_support', destination/'capture_support')
    shutil.copy2(reference/'distractor_prompts.json', destination/'distractor_prompts.json')
    env = dict(os.environ, **command['env'])
    old_code = env['ANCHOR_VISUAL_CODE']
    env.update(ANCHOR_VISUAL_CODE=str(code), OVERLAY_ROOT=str(overlay),
        ANCHOR_CAPTURE_DIR=str(destination/'snapshots'),
        ANCHOR_DIAGNOSTIC_HOOK=str(destination/'capture_support/visual_selection_oracle_geometry_hook.py'),
        CUTAMP_FLOCK_LOCK=str(destination/'cutamp.lock'),
        DINO_INFERENCE_PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'].replace(old_code,str(code)),
        PYTHONPATH=str(overlay)+':'+env['PYTHONPATH'])
    argv = list(command['argv'])
    argv[1] = str(code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py')
    argv[argv.index('--run-dir')+1] = str(destination)
    recorded = dict(argv=argv, env={k:env[k] for k in set(command['env'])|{'OVERLAY_ROOT'}})
    (destination/'command.json').write_text(json.dumps(recorded,indent=2))
    inputs = [Path(argv[argv.index('--bddl')+1])]
    fixture = Path(argv[argv.index('--fixture')+1])
    inputs += [fixture/'config.json',fixture/'initial_physics_state.npy']
    (destination/'input_manifest.json').write_text(json.dumps(dict(
        reference=str(reference),sha256={str(p):sha(p) for p in inputs},
        backend_sha256=sha(overlay/BACKEND),
        hook_sha256=sha(destination/'capture_support/visual_selection_oracle_geometry_hook.py')),indent=2))
    with (destination/'driver.log').open('wb') as log:
        proc = subprocess.run(argv,env=env,cwd=overlay,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
    result = dict(exit_code=proc.returncode)
    for name in ('replay_result.json','failure_result.json'):
        if (destination/name).exists():
            result[name] = json.loads((destination/name).read_text())
    (destination/'finished.json').write_text(json.dumps(result,indent=2))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--runtime-reference',type=Path,required=True)
    parser.add_argument('--visual-code-reference',type=Path,required=True)
    parser.add_argument('--bowl-reference',type=Path,required=True)
    parser.add_argument('--plate-reference',type=Path,required=True)
    parser.add_argument('--diagnostic-script',type=Path,required=True)
    parser.add_argument('--dimension-test',type=Path,required=True)
    args = parser.parse_args()
    args.run_dir.mkdir(exist_ok=False)
    manifest = dict(runtime_reference=str(args.runtime_reference),
        runtime_backend_sha256_before=sha(args.runtime_reference/BACKEND),
        launcher_sha256=sha(Path(__file__)),controlled_change='Measured RGB-D static cells bypass object_min_dim; no other planner changes')
    overlay, code = args.run_dir/'runtime_overlay',args.run_dir/'code'
    shutil.copytree(args.runtime_reference,overlay,ignore=shutil.ignore_patterns('.git','__pycache__'))
    shutil.copytree(args.visual_code_reference,code,ignore=shutil.ignore_patterns('.git','__pycache__'))
    patch_backend(overlay/BACKEND)
    patch_backend(code/BACKEND)
    manifest['patched_runtime_backend_sha256'] = sha(overlay/BACKEND)
    manifest['patched_visual_backend_sha256'] = sha(code/BACKEND)
    (args.run_dir/'manifest.json').write_text(json.dumps(manifest,indent=2))
    root = Path(os.environ['ROOT'])
    ref_command = json.loads((args.bowl_reference/'command.json').read_text())
    env = dict(os.environ,**ref_command['env'],OVERLAY_ROOT=str(overlay))
    env['PYTHONPATH'] = str(overlay)+':'+env['PYTHONPATH']
    results = {}
    with (args.run_dir/'dimension_test.log').open('wb') as log:
        check = subprocess.run([str(root/'envs/rlinf-openpi/bin/python'),str(args.dimension_test)],
            cwd=overlay,env=env,stdout=log,stderr=subprocess.STDOUT)
    assert check.returncode == 0, 'dimension unit checks failed'
    problem = args.bowl_reference/'cutamp_debug/solve_1792112151269_290884.problem.json'
    argv = [env['CUTAMP_REAL_RUNNER'],str(args.diagnostic_script),'--worker','--problem',str(problem),
        '--out-dir',str(args.run_dir/'saved_problem'),'--variant','baseline','--seed','0','--capture']
    env.update(REAL_CUTAMP_BACKEND_CHILD='1',CUTAMP_CONTACT_MODE_TARGET='1',
        CUTAMP_ALLOW_START_COLLISION_ESCAPE='1',CUTAMP_START_ESCAPE_Z='0.08')
    (args.run_dir/'saved_problem_command.json').write_text(json.dumps(dict(argv=argv,
        env={k:env[k] for k in set(ref_command['env'])|{'OVERLAY_ROOT','REAL_CUTAMP_BACKEND_CHILD',
            'CUTAMP_CONTACT_MODE_TARGET','CUTAMP_ALLOW_START_COLLISION_ESCAPE','CUTAMP_START_ESCAPE_Z'}}),indent=2))
    with (args.run_dir/'saved_problem.log').open('wb') as log:
        proc = subprocess.run(argv,cwd=overlay,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=300)
    results['saved_problem_exit_code'] = proc.returncode
    if (args.run_dir/'saved_problem/result.json').exists():
        results['saved_problem'] = json.loads((args.run_dir/'saved_problem/result.json').read_text())
    (args.run_dir/'progress.json').write_text(json.dumps(results,indent=2))
    for name,reference in [('bowl',args.bowl_reference),('plate_regression',args.plate_reference)]:
        try:
            results[name] = replay(reference,args.run_dir/name,code,overlay)
        except Exception:
            results[name] = dict(launcher_error=traceback.format_exc())
        (args.run_dir/'progress.json').write_text(json.dumps(results,indent=2))
    manifest['runtime_backend_sha256_after'] = sha(args.runtime_reference/BACKEND)
    assert manifest['runtime_backend_sha256_before'] == manifest['runtime_backend_sha256_after']
    (args.run_dir/'manifest.json').write_text(json.dumps(manifest,indent=2))
    (args.run_dir/'finished.json').write_text(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
