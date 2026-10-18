from pathlib import Path
import json,os,subprocess,time
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');out=root/'logs/github_inspire_archive_20261018';out.mkdir(exist_ok=True)
d=dict(root=str(root),unix=time.time(),top=[],logs=[],models=[],repos=[],active=[])
for p in sorted(root.iterdir()):d['top'].append(dict(name=p.name,directory=p.is_dir(),symlink=p.is_symlink()))
for folder,key in [('logs','logs'),('models','models'),('artifacts','artifacts'),('assets','assets'),('eval_runs','eval_runs')]:
 d[key]=[dict(name=p.name,directory=p.is_dir(),symlink=p.is_symlink()) for p in sorted((root/folder).iterdir())] if (root/folder).exists() else []
for rel in ['vla-recovery-pipeline','vla-recovery-pipeline-bddl','vla-recovery-drawerfix-20260929','logs/continual_skill_core60_pilot_20261006/runtime_repo','third_party/LIBERO-PRO']:
 p=root/rel
 if not p.exists():continue
 def git(*args):return subprocess.run(['git','-c','safe.directory='+str(p),'-C',str(p),*args],capture_output=True,text=True).stdout
 d['repos'].append(dict(path=rel,head=git('rev-parse','HEAD').strip(),branch=git('branch','--show-current').strip(),status=git('status','--short','--untracked-files=normal')))
ps=subprocess.run(['ps','-eo','pid,etimes,args'],capture_output=True,text=True).stdout
for line in ps.splitlines():
 if str(root) in line and any(x in line for x in ['run_rgbd','run_known_model','run_core60','batch.py']):
  # Process argument strings may hold endpoints: only record executable/pid, not full argv.
  fields=line.strip().split(None,2);d['active'].append(dict(pid=fields[0],elapsed=fields[1],kind='research process'))
(out/'inventory.json').write_text(json.dumps(d,ensure_ascii=False,indent=2))
print(json.dumps(dict(logs=len(d['logs']),models=d['models'],active=d['active'])))
