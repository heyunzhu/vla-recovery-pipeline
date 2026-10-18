from pathlib import Path
import os,sys,json,shutil,time
R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');O=R/'logs/github_inspire_archive_20261018';sys.path.insert(0,str(O))
import package_ssh_research_assets as p
import audit_ssh_archive as au
from restore_ssh_research_assets import verify
p.SOURCE |= {'.cpp','.cu','.h','.hpp','.c','.cuh','.lock'};p.PRUNE |= {'analysis_outputs','cache','caches','build','dist','venv','native_env','downloads','wheelhouse'}
plan=json.loads((O/'archive_plan.json').read_text());excluded={x['roots'][0] for x in plan['jobs'] if x['kind']=='visual'}|{'logs/continual_skill_core60_pilot_20261006','logs/github_inspire_archive_20261018'}
roots=[]
for top in sorted((R/'logs').iterdir()):
 if not top.is_dir() or str(top.relative_to(R)) in excluded or top.name.endswith('_staging'):continue
 for b,dirs,names in os.walk(top,followlinks=False):
  b=Path(b);depth=len(b.relative_to(top).parts)
  dirs[:]=[x for x in sorted(dirs) if x not in p.PRUNE and x not in {'frames','snapshots','resident_vision','cases','lanes','run','interrupted','cutamp_debug','models'}]
  if depth>=3:dirs[:]=[]
  selected=[]
  for d in dirs:
   if d in {'runtime_repo','runtime_overlay','code','frozen_runtime','checkpoints','skill_packs','skills','packs','pack','profiles','diagnostics'} or 'checkpoint' in d or d.startswith(('runtime_','exported_pack','draft_pack')):
    q=b/d
    if q.is_dir() and not q.is_symlink():roots.append(q);selected.append(d)
  dirs[:]=[x for x in dirs if x not in selected]
(O/'historical_skills_scope.json').write_text(json.dumps(dict(roots=[str(x.relative_to(R)) for x in roots],source_type_filter=True),indent=2));print('HISTORICAL_SKILL_ROOTS',len(roots),flush=True)
label='historical-runtime-and-skills';p.package(R,O,label,roots,'source');au.audit(O,label)
ar=O/'verify_layout';shutil.copyfile(O/(label+'.manifest.json'),ar/'manifests'/(label+'.manifest.json'));v=verify(ar,label);(O/(label+'.verification.json')).write_text(json.dumps(v));print('VERIFIED',label,v['files'],v['archive_bytes'],flush=True)
(O/'historical_skills_finished.json').write_text(json.dumps(dict(completed=True,unix=time.time())))
