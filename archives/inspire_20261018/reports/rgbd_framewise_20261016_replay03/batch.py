from pathlib import Path
import subprocess,os,json
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
run=root/'logs/rgbd_framewise_20261016_replay03'
records=[]
for mode in ['bowl','plate']:
 argv=[str(root/'envs/rlinf-openpi/bin/python'),str(run/'code/scripts/recovery/skill_pipeline/run_framewise_rgbd_experiment.py'),'--run-root',str(run),'--mode',mode]
 (run/(mode+'_launch_command.json')).write_text(json.dumps(argv,indent=2))
 with (run/(mode+'_launcher.log')).open('wb') as log:p=subprocess.run(argv,env=dict(os.environ,ROOT=str(root)),stdout=log,stderr=subprocess.STDOUT,timeout=1800)
 records.append(dict(mode=mode,exit_code=p.returncode))
 (run/'batch_progress.json').write_text(json.dumps(records,indent=2))
(run/'batch_finished.json').write_text(json.dumps(records,indent=2))
