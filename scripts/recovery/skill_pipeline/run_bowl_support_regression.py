"""Reproduce the frozen plate anchor, then test bowl geometry on its frozen case.

Run with the simulation environment's Python on xinghanbo-eval after copying the
three geometry/hook source files into a NEW code snapshot. Never edits baselines.
"""
import hashlib
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bowl-only', action='store_true', help='Retry bowl after an independently successful plate regression')
    parser.add_argument('--bowl-name', help='Unused output subdirectory name for a documented retry')
    args = parser.parse_args()
    root = Path(os.environ['ROOT'])
    previous = root/'logs/rgbd_dino_integration_20261016'
    run = Path(os.environ['BOWL_EXPERIMENT'])
    code = run/'code'
    runtime = root/'logs/continual_skill_core60_pilot_20261006/runtime_repo'
    baseline = json.loads((previous/'anchor_ownership8_640/command.json').read_text())
    manifest = dict(baseline=baseline, baseline_result=json.loads(
        (previous/'anchor_ownership8_640/replay_result.json').read_text()),
        runtime_head=subprocess.check_output(['git','-C',str(runtime),'rev-parse','HEAD'],text=True).strip(),
        source_sha256={str(p.relative_to(code)):hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in code.rglob('*.py') if '__pycache__' not in str(p)})
    (run/'baseline_and_source_manifest.json').write_text(json.dumps(manifest,indent=2))
    results = []
    cases = [('bowl_attempt02', True)] if args.bowl_only else [('plate_regression', False), ('bowl_attempt01', True)]
    if args.bowl_name:
        if Path(args.bowl_name).name != args.bowl_name or args.bowl_name in ('.','..'):
            raise ValueError('bowl name must be a single directory name')
        cases = [(args.bowl_name if bowl else name, bowl) for name,bowl in cases]
    for name, bowl in cases:
        out = run/name
        out.mkdir(exist_ok=False)
        shutil.copytree(previous/'anchor_ownership8_640/capture_support', out/'capture_support')
        shutil.copy2(code/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py',
                     out/'capture_support/visual_selection_oracle_geometry_hook.py')
        prompt_source = previous/('recovery/02_goal_bottle_bowl_640' if bowl else 'anchor_ownership8_640')
        shutil.copy2(prompt_source/'distractor_prompts.json',out/'distractor_prompts.json')
        env = dict(os.environ)
        env.update(MUJOCO_GL='egl',PYOPENGL_PLATFORM='egl',CUDA_VISIBLE_DEVICES='0',OMP_NUM_THREADS='2',
            XLA_PYTHON_CLIENT_MEM_FRACTION='0.50',XLA_PYTHON_CLIENT_PREALLOCATE='false',
            LIBERO_CONFIG_PATH=str(runtime.parent/'libero_config'),
            ORACLE_ENTRYPOINT=str(runtime.parent/'core60_entrypoint.py'),
            PYTHONPATH=f'{runtime}:{root}/third_party/LIBERO-PRO')
        env.update(baseline['env'])
        old_code = env['ANCHOR_VISUAL_CODE']
        env.update(ANCHOR_CAPTURE_DIR=str(out/'snapshots'),
            ANCHOR_DIAGNOSTIC_HOOK=str(out/'capture_support/visual_selection_oracle_geometry_hook.py'),
            ANCHOR_VISUAL_CODE=str(code), CUTAMP_FLOCK_LOCK=str(out/'cutamp.lock'),
            DINO_INFERENCE_PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'].replace(old_code,str(code)))
        argv = list(baseline['argv'])
        argv[1] = str(code/'scripts/recovery/skill_pipeline/replay_anchor_recovery.py')
        argv[argv.index('--run-dir')+1] = str(out)
        if bowl:
            old = json.loads((previous/'recovery/02_goal_bottle_bowl_640/command.json').read_text())
            for option in ('--fixture','--bddl'):
                argv[argv.index(option)+1] = old['argv'][old['argv'].index(option)+1]
            env['ANCHOR_EPISODE_ID'] = old['env_overrides']['ANCHOR_EPISODE_ID']
            env['ANCHOR_REPLACE_PLATE_GEOMETRY'] = '0'
            env['ANCHOR_REPLACE_GOAL_GEOMETRY'] = '1'
        (out/'command.json').write_text(json.dumps(dict(argv=argv,env={k:v for k,v in env.items()
            if k in baseline['env'] or k in ('ROOT','PYTHONPATH','LIBERO_CONFIG_PATH','ORACLE_ENTRYPOINT',
            'MUJOCO_GL','PYOPENGL_PLATFORM','CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS',
            'XLA_PYTHON_CLIENT_MEM_FRACTION','XLA_PYTHON_CLIENT_PREALLOCATE','ANCHOR_REPLACE_GOAL_GEOMETRY')}),indent=2))
        with (out/'driver.log').open('wb') as log:
            proc = subprocess.run(argv,cwd=runtime,env=env,stdout=log,stderr=subprocess.STDOUT)
        result = dict(case=name,exit_code=proc.returncode)
        for filename in ('replay_result.json','failure_result.json'):
            if (out/filename).exists():
                result[filename] = json.loads((out/filename).read_text())
        results.append(result)
        (run/'progress.json').write_text(json.dumps(results,indent=2))
    (run/'finished.json').write_text(json.dumps(results,indent=2))


if __name__ == '__main__':
    main()
