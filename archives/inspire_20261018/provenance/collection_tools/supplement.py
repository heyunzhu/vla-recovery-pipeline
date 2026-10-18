from pathlib import Path,PurePosixPath
import json,os,sys,tarfile,hashlib,shutil,time
R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');O=R/'logs/github_inspire_archive_20261018';sys.path.insert(0,str(O))
import package_ssh_research_assets as p
import audit_ssh_archive as au
from restore_ssh_research_assets import verify
p.SOURCE |= {'.cpp','.cu','.h','.hpp','.c','.cuh','.mtl','.dae','.off','.cmake','.lock','.pth'}
backup=R/'_archive/cuTAMP_before_5476_sync_20260905/cuTAMP_before.tgz';dest=O/'legacy_cutamp_20260905';dest.mkdir(exist_ok=True);ex=[];count=0
with tarfile.open(backup,'r:gz') as t:
 for m in t:
  rel=PurePosixPath(m.name)
  if not m.isfile() or rel.is_absolute() or '..' in rel.parts or '\\' in m.name:continue
  if any(x in p.PRUNE or p.SECRET_NAME.search(x) for x in rel.parts):continue
  if Path(m.name).suffix.lower() not in p.SOURCE and rel.name not in {'LICENSE','Dockerfile','CMakeLists.txt'}:continue
  if m.size>32*1024**2:ex.append(m.name);continue
  q=(dest/Path(*rel.parts)).resolve();assert q.is_relative_to(dest.resolve());q.parent.mkdir(parents=True,exist_ok=True)
  if not q.exists():
   with t.extractfile(m) as f,q.open('xb') as g:shutil.copyfileobj(f,g)
  count+=1
h=hashlib.sha256(backup.read_bytes()).hexdigest();(O/'legacy_cutamp_source.json').write_text(json.dumps(dict(source=str(backup.relative_to(R)),sha256=h,selected_regular_files=count,over_cap=ex)))
roots=[O/'environment_inventory.json',O/'inventory.json',O/'legacy_cutamp_source.json']
for model in (R/'models').iterdir():
 for name in ['README.md','config.json','norm_stats.json','params.json','model_config.json','checkpoint_metadata.json']:
  if (model/name).is_file():roots.append(model/name)
for name in ['norm_stats.json','assets']:
 for model in (R/'models').iterdir():
  q=model/name
  if q.is_dir():roots.append(q)
jobs=[('environment-contracts',roots),('legacy-cutamp',[dest,R/'_archive/cuTAMP_before_5476_sync_20260905/head.txt',R/'_archive/cuTAMP_before_5476_sync_20260905/status.txt'])]
(O/'supplemental_plan.json').write_text(json.dumps([dict(label=l,roots=[str(q.relative_to(R)) for q in qs]) for l,qs in jobs],indent=2))
for label,rs in jobs:
 p.package(R,O,label,rs,'source');au.audit(O,label)
 ar=O/'verify_layout';(ar/'manifests').mkdir(parents=True,exist_ok=True)
 if not (ar/'assets').exists():(ar/'assets').symlink_to(O,target_is_directory=True)
 shutil.copyfile(O/(label+'.manifest.json'),ar/'manifests'/(label+'.manifest.json'))
 v=verify(ar,label);(O/(label+'.verification.json')).write_text(json.dumps(v));print('VERIFIED',label,v['files'],v['archive_bytes'],flush=True)
(O/'supplemental_finished.json').write_text(json.dumps(dict(completed=[x[0] for x in jobs],unix=time.time())))
