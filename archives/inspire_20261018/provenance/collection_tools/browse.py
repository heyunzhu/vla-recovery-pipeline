from pathlib import Path
import os,sys,json,shutil,hashlib,time
R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');O=R/'logs/github_inspire_archive_20261018';sys.path.insert(0,str(O))
import package_ssh_research_assets as p
import audit_ssh_archive as au
from restore_ssh_research_assets import verify
B=O/'browse';B.mkdir(exist_ok=True);mapping=[]
def copy(q,dest):
 if not q.is_file() or q.is_symlink() or q.stat().st_size>8*1024**2 or p.SECRET_NAME.search(q.name):return
 data,n=p.sanitize(q.read_bytes(),q.suffix.lower())
 if data is None:return
 dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data);mapping.append(dict(path=str(dest.relative_to(B)),source=str(q.relative_to(R)),original_sha256=hashlib.sha256(q.read_bytes()).hexdigest(),redactions=n))
roots=[x for x in (R/'logs').iterdir() if x.is_dir() and x.name.startswith(('rgbd_','hybrid_visual','oracle_anchor','continual_skill_core60')) and not x.name.endswith('_staging')]
for top in sorted(roots):
 for q in sorted(top.iterdir()):
  if q.is_file() and q.suffix.lower() in p.TEXT|{'.png','.svg','.jpg'}:copy(q,B/'reports'/top.name/q.name)
 for name in ['offline_audit','adapter_preflight']:
  sub=top/name
  if sub.exists():
   for q in sub.rglob('*'):
    if q.is_file() and q.suffix.lower() in p.TEXT|{'.png','.svg','.jpg'}:copy(q,B/'reports'/top.name/q.relative_to(top))
packmap=[];packs=R/'logs/continual_skill_core60_pilot_20261006/checkpoints'
for i,pack in enumerate(sorted(packs.iterdir())):
 if not pack.is_dir():continue
 alias=f'pack{i:02d}';packmap.append(dict(alias=alias,source=str(pack.relative_to(R))))
 for b,dirs,names in os.walk(pack):
  dirs[:]=[d for d in sorted(dirs) if d not in p.PRUNE]
  for name in sorted(names):
   q=Path(b)/name
   if q.suffix.lower() in p.TEXT:copy(q,B/'view/packs'/alias/q.relative_to(pack))
(B/'view/packs/pack_mapping.json').write_text(json.dumps(packmap,indent=2));(B/'browse_mapping.json').write_text(json.dumps(mapping,indent=2))
label='readable-index';p.package(B,O,label,[B],'source');au.audit(O,label)
ar=O/'verify_layout';(ar/'manifests').mkdir(parents=True,exist_ok=True)
if not (ar/'assets').exists():(ar/'assets').symlink_to(O,target_is_directory=True)
shutil.copyfile(O/(label+'.manifest.json'),ar/'manifests'/(label+'.manifest.json'))
v=verify(ar,label);(O/(label+'.verification.json')).write_text(json.dumps(v));print('VERIFIED',label,v['files'],v['archive_bytes'],flush=True)
(O/'browse_finished.json').write_text(json.dumps(dict(completed=True,unix=time.time())))
