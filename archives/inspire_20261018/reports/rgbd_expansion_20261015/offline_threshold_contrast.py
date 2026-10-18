from pathlib import Path
import os,json,subprocess
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');b=root/'logs/rgbd_expansion_20261015';code=b/'expansion_code'
e=dict(os.environ,PYTHONPATH=str(root/'logs/rgbd_exact_box_20261008/pydeps')+':'+str(code),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',OMP_NUM_THREADS='2')
for case in ['goal_bottle_bowl','swap_bowl_plate']:
 p=b/case/'visual';out=p/'threshold025_nomination'
 cmd=[str(root/'envs/tiptop-planning-py310/bin/python'),str(code/'scripts/recovery/skill_pipeline/inspect_recovery_rgbd_capture.py'),str(p/'snapshots'),'--out-dir',str(out),'--camera','agentview','--phase','pre_solver_attempt01','--device','cpu','--text-threshold','0.25','--grounding-model-dir',str(root/'logs/rgbd_exact_box_20261008/models/grounding-dino-tiny'),'--sam2-model-dir',str(root/'logs/rgbd_exact_box_20261008/models/sam2.1-hiera-tiny'),'--distractor-prompts-json',str(p/'distractor_prompts.json')]
 with (p/'threshold025.log').open('wb') as f:rc=subprocess.run(cmd,env=e,stdout=f,stderr=subprocess.STDOUT).returncode
 (p/'threshold025_command.json').write_text(json.dumps(dict(command=cmd,exitcode=rc,scope='offline_sensor_only_no_solver_no_actions'),indent=2))
(b/'threshold_contrast_finished.txt').write_text('finished')
