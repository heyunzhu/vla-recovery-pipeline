from pathlib import Path
import zipfile,shutil,hashlib,json,subprocess,os
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
run=root/'logs/rgbd_framewise_20261016_replay03'
staging=root/'logs/rgbd_framewise_20261016_staging'
run.mkdir(exist_ok=False)
shutil.copytree(root/'logs/rgbd_static_box_fix_20261016/code_strict_bowl',run/'code',ignore=shutil.ignore_patterns('__pycache__'))
with zipfile.ZipFile(staging/'source_bundle.zip') as z:
 for name in z.namelist():
  assert (run/'code'/name).resolve().is_relative_to((run/'code').resolve())
 z.extractall(run/'code')
 manifest={n:hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist()}
(run/'source_manifest.json').write_text(json.dumps(manifest,indent=2))

env=dict(os.environ,PYTHONPATH=str(root/'logs/rgbd_exact_box_20261008/pydeps')+':'+str(run/'code'))
with (run/'vision_import_preflight.log').open('wb') as log:
 check=subprocess.run([str(root/'envs/tiptop-planning-py310/bin/python'),'-c','import experiments.robot.libero.skill_pipeline.grounded_sam2_backend as m;print(m.__file__)'],cwd=run/'code',env=env,stdout=log,stderr=subprocess.STDOUT)
assert check.returncode==0,'vision import preflight failed'

(run/"batch.py").write_text("from pathlib import Path\nimport subprocess,os,json\nroot=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')\nrun=root/'logs/rgbd_framewise_20261016_replay03'\nrecords=[]\nfor mode in ['bowl','plate']:\n argv=[str(root/'envs/rlinf-openpi/bin/python'),str(run/'code/scripts/recovery/skill_pipeline/run_framewise_rgbd_experiment.py'),'--run-root',str(run),'--mode',mode]\n (run/(mode+'_launch_command.json')).write_text(json.dumps(argv,indent=2))\n with (run/(mode+'_launcher.log')).open('wb') as log:p=subprocess.run(argv,env=dict(os.environ,ROOT=str(root)),stdout=log,stderr=subprocess.STDOUT,timeout=1800)\n records.append(dict(mode=mode,exit_code=p.returncode))\n (run/'batch_progress.json').write_text(json.dumps(records,indent=2))\n(run/'batch_finished.json').write_text(json.dumps(records,indent=2))\n")
with (run/"batch.log").open("wb") as log:p=subprocess.Popen([str(root/"envs/rlinf-openpi/bin/python"),str(run/"batch.py")],env=dict(os.environ,ROOT=str(root)),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
print(p.pid)
