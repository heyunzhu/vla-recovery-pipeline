"""Replay one saved visual recovery with only labeled obstacle pixels.

Paths and the obstacle policy change; frozen inputs, detector and controller
parameters are copied from the reference command. Run on xinghanbo-eval.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--code', type=Path, required=True)
    args = parser.parse_args()
    reference = json.loads((args.reference/'command.json').read_text())
    args.run_dir.mkdir(exist_ok=False)
    shutil.copytree(args.reference/'capture_support', args.run_dir/'capture_support')
    shutil.copy2(args.code/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py',
                 args.run_dir/'capture_support/visual_selection_oracle_geometry_hook.py')
    shutil.copy2(args.reference/'distractor_prompts.json',args.run_dir/'distractor_prompts.json')
    env = dict(os.environ)
    env.update(reference['env'])
    old_code = env['ANCHOR_VISUAL_CODE']
    env.update(ANCHOR_CAPTURE_DIR=str(args.run_dir/'snapshots'),
        ANCHOR_DIAGNOSTIC_HOOK=str(args.run_dir/'capture_support/visual_selection_oracle_geometry_hook.py'),
        ANCHOR_VISUAL_CODE=str(args.code), CUTAMP_FLOCK_LOCK=str(args.run_dir/'cutamp.lock'),
        DINO_INFERENCE_PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'].replace(old_code,str(args.code)),
        ANCHOR_LABELED_OBSTACLES_ONLY='1')
    argv = list(reference['argv'])
    argv[1] = str(args.code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py')
    argv[argv.index('--run-dir')+1] = str(args.run_dir)
    command = dict(argv=argv, env={k:env[k] for k in set(reference['env'])|{'ANCHOR_LABELED_OBSTACLES_ONLY'}})
    (args.run_dir/'command.json').write_text(json.dumps(command,indent=2))
    inputs = {option: argv[argv.index(option)+1] for option in ('--fixture','--bddl')}
    input_files = [Path(inputs['--bddl']), Path(inputs['--fixture'])/'config.json',
                   Path(inputs['--fixture'])/'initial_physics_state.npy']
    manifest = dict(reference=str(args.reference),reference_command=reference,
        controlled_change='all_observed_depth -> labeled_detector_SAM_masks_only; table and fitted bowl walls retained',
        input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in input_files},
        code_sha256={str(p.relative_to(args.code)):hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in args.code.rglob('*.py') if '__pycache__' not in p.parts})
    (args.run_dir/'experiment_manifest.json').write_text(json.dumps(manifest,indent=2))
    runtime = Path(env['ROOT'])/'logs/continual_skill_core60_pilot_20261006/runtime_repo'
    with (args.run_dir/'driver.log').open('wb') as log:
        process = subprocess.run(argv, env=env, cwd=runtime, stdout=log, stderr=subprocess.STDOUT)
    result = dict(exit_code=process.returncode)
    for filename in ('replay_result.json','failure_result.json'):
        if (args.run_dir/filename).exists():
            result[filename] = json.loads((args.run_dir/filename).read_text())
    (args.run_dir/'finished.json').write_text(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
