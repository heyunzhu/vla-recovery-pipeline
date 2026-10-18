"""Saved-frame timing/pose audit and isolated framewise RGB-D replay launcher."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback


def environment(root,code,reference,config_path):
    command=json.loads((reference/'command.json').read_text())
    env=dict(os.environ,**command['env'])
    old=env['ANCHOR_VISUAL_CODE']
    env.update(ANCHOR_VISUAL_CODE=str(code),ANCHOR_FRAMEWISE_DETECTION='1',
        ANCHOR_FRAMEWISE_CONFIG=str(config_path),
        ANCHOR_SEGMENTATION_PYTHON=str(root/'envs/tiptop-planning-py310/bin/python'),
        ANCHOR_SEGMENTATION_PYTHONPATH=str(root/'logs/rgbd_exact_box_20261008/pydeps')+':'+str(code),
        DINO_INFERENCE_PYTHONPATH=env['DINO_INFERENCE_PYTHONPATH'].replace(old,str(code)))
    return env,command


def benchmark(root,run,code,reference,env,config):
    os.environ.update(env);sys.path.insert(0,str(code))
    import numpy as np
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.framewise_rgbd_tracker import ResidentSegmentation,FramewiseRGBDTracker
    output=run/'saved_frames';output.mkdir(exist_ok=False)
    initial=load_observation(reference/'snapshots/recovery01/pre_solver_attempt01/agentview')
    nomination=reference/'visual_nomination_step50/recovery01/pre_solver_attempt01/agentview'
    model=json.loads((nomination/'bottle_model.json').read_text())
    startup=time.perf_counter()
    segmenter=ResidentSegmentation(config,output/'resident_vision')
    records=[]
    try:
        masks,reply=segmenter(initial)
        indices=[i for i,c in enumerate(reply['categories']) if c=='bottle']
        assert len(indices)==1,reply
        tracker=FramewiseRGBDTracker(initial,masks[indices[0]],model,segmenter,output_dir=output/'tracking')
        (output/'warmup.json').write_text(json.dumps(dict(
            startup_and_first_frame_ms=(time.perf_counter()-startup)*1000,detection=reply),indent=2))
        phases={}
        for p in sorted((reference/'snapshots/recovery01').iterdir(),key=lambda p:p.name=='failure'):
            if not (p.name.startswith('execution_step') or p.name=='failure'):continue
            frame=load_observation(p/'agentview')
            if frame.env_step>initial.env_step:phases[frame.env_step]=(p,frame)
        for step,(path,frame) in sorted(phases.items()):
            start=time.perf_counter()
            try:
                model,report=tracker.update(frame)
                record=dict(env_step=step,accepted=True,report=report)
            except Exception:
                record=dict(env_step=step,accepted=False,error=traceback.format_exc())
            record['wall_ms']=(time.perf_counter()-start)*1000
            records.append(record)
            (output/'progress.json').write_text(json.dumps(records,indent=2))
        times=[r['wall_ms'] for r in records]
        result=dict(recorded_frames=len(records),accepted=sum(r['accepted'] for r in records),
            failed_steps=[r['env_step'] for r in records if not r['accepted']],
            frame125=next((r for r in records if r['env_step']==125),None),
            warmed_end_to_end_ms=dict(median=float(np.median(times)),p95=float(np.quantile(times,.95))),
            continuous_20hz_claim=False,records=records)
        (output/'finished.json').write_text(json.dumps(result,indent=2))
        print(json.dumps({k:v for k,v in result.items() if k not in ['records','frame125']}),flush=True)
    finally:segmenter.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-root',type=Path,required=True)
    p.add_argument('--mode',choices=['benchmark','bowl','plate'],required=True)
    args=p.parse_args()
    root=Path(os.environ['ROOT']);run=args.run_root;code=run/'code'
    base=root/'logs/rgbd_static_box_fix_20261016'
    reference=base/('plate_regression' if args.mode=='plate' else 'bowl_strict_acceptance')
    config=dict(grounding_model=str(root/'logs/rgbd_dino_integration_20261016/hf_export_best'),
        grounding_revision='a2bb814dd30d776dcf7e30523b00659f4f141c71',
        sam2_model=str(root/'logs/rgbd_exact_box_20261008/models/sam2.1-hiera-tiny'),
        sam2_revision='de431c4043854a71d8101e17995dfe596bf101a5',
        prompts=dict(bottle='wine bottle',**({'plate':'plate'} if args.mode=='plate' else {'bowl':'bowl'})),
        device='cuda',grounding_mode='joint',box_threshold=.25,text_threshold=.35,mmdet_export=True)
    config_path=run/(args.mode+'_vision_config.json');config_path.write_text(json.dumps(config,indent=2))
    env,command=environment(root,code,reference,config_path)
    if args.mode=='benchmark':return benchmark(root,run,code,reference,env,config)
    patched_reference=run/(args.mode+'_reference');patched_reference.mkdir(exist_ok=False)
    shutil.copytree(reference/'capture_support',patched_reference/'capture_support')
    shutil.copy2(code/'scripts/recovery/skill_pipeline/visual_selection_oracle_geometry_hook.py',
        patched_reference/'capture_support/visual_selection_oracle_geometry_hook.py')
    shutil.copy2(reference/'distractor_prompts.json',patched_reference/'distractor_prompts.json')
    command['env']={k:env[k] for k in set(command['env'])|{'ANCHOR_FRAMEWISE_DETECTION','ANCHOR_FRAMEWISE_CONFIG',
        'ANCHOR_SEGMENTATION_PYTHON','ANCHOR_SEGMENTATION_PYTHONPATH'}}
    (patched_reference/'command.json').write_text(json.dumps(command,indent=2))
    module_path=code/'scripts/recovery/skill_pipeline/run_rgbd_static_box_fix_validation.py'
    spec=importlib.util.spec_from_file_location('validation',module_path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    result=module.replay(patched_reference,run/args.mode,code,base/'runtime_overlay')
    (run/(args.mode+'_finished.json')).write_text(json.dumps(result,indent=2))


if __name__=='__main__':main()
