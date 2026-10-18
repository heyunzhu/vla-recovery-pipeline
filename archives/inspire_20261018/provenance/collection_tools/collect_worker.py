from pathlib import Path
import os,sys,json,time,collections,subprocess,hashlib
import package_ssh_research_assets as p
from fast_jsonl_sanitize import install
install()
import audit_ssh_archive as audit
from restore_ssh_research_assets import verify
ROOT=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');OUT=ROOT/'logs/github_inspire_archive_20261018'
p.PRUNE |= {'analysis_outputs','cache','caches','build','dist','wandb','native_env','venv','.mypy_cache','.ruff_cache','wheelhouse','downloads','.ipynb_checkpoints'}
p.SOURCE |= {'.cpp','.cu','.h','.hpp','.c','.cuh','.mtl','.dae','.off','.usd','.usda','.cmake','.lock','.pth'}
orig_files=p.files
source_roots=[ROOT/x for x in ['vla-recovery-pipeline','vla-recovery-pipeline-bddl','vla-recovery-drawerfix-20260929','vla-recovery-pipeline-bddl.broken-20260919-0044','worktrees','code/RLinf','code/openvla-oft','code/openvla-oft.before_sync_20260903_2140','code/openvla-oft.before_sync_d53bca9_20260906_160337','third_party','libero_config','pro_object_batch_20261004_task','artifacts','assets/libero_assets']]
base=ROOT/'logs/continual_skill_core60_pilot_20261006'
frozen_roots=[base/x for x in ['runtime_repo','checkpoints','bddl_files','init_files','init_supplement','libero_config']]
rgbd_roots=[x for x in sorted((ROOT/'logs').iterdir()) if x.is_dir() and x.name.startswith(('rgbd_','hybrid_visual_','oracle_anchor_')) and not x.name.endswith('_staging')]
visual_exclude={'code','runtime_repo','runtime_overlay','runtime','frozen_runtime','native_assets','sensor_support','capture_support','finetune_sources_20261018','interrupted','startup_attempts','deployment_attempts','checkpoints'}
media={'.jpg','.jpeg','.png','.svg','.mp4','.webm','.npy','.npz','.pkl','.pickle','.obj','.stl','.ply','.pcd','.bin','.init','.primitives'}
# Repetitive native solve dumps are retained as one complete pair per episode/run.
def selected(root,roots,kind,excluded):
 if kind in {'source','frozen'}:
  prior=p.PRUNE;p.PRUNE=prior|{'datasets','models','checkpoints'}
  try:
   for q in orig_files(root,roots,'source',excluded):yield q
  finally:p.PRUNE=prior
  return
 seen=set();debug_done=set();video_counts=collections.Counter()
 for top in roots:
  if not top.exists():continue
  walk=[(str(top.parent),[],[top.name])] if top.is_file() else os.walk(top,followlinks=False)
  for b,dirs,names in walk:
   b=Path(b);dirs[:]=[x for x in sorted(dirs) if x not in p.PRUNE and x not in visual_exclude and not p.SECRET_NAME.search(x)]
   if kind in {'records','baseline'}:dirs[:]=[x for x in dirs if x not in {'frames','snapshots','resident_vision','images','point_clouds','pointclouds','models','recovery_models'}]
   debug=any(x in b.parts for x in ('cutamp_debug','solver_inputs','solver_outputs','native_debug'))
   if debug:
    dirs[:]=[];key=str(b.parent)
    if key in debug_done:continue
    problem=next((n for n in sorted(names) if n.endswith('.problem.json')),None)
    if not problem:continue
    stem=problem[:-len('.problem.json')];names=[problem]+([stem+'.result.json'] if stem+'.result.json' in names else []);debug_done.add(key)
   for name in sorted(names):
    q=b/name;rel=q.relative_to(root).as_posix();suffix=q.suffix.lower()
    if rel in seen:continue
    seen.add(rel)
    if '\\' in rel or p.SECRET_NAME.search(name):excluded.append(dict(path=rel,reason='credential_or_unsafe_path'));continue
    if suffix in {'.pth','.pt','.safetensors','.zip','.gz','.tgz','.tar','.whl','.so','.pyc','.lock'}:continue
    if suffix not in p.TEXT|media and name not in {'LICENSE','Dockerfile','.done'}:continue
    if kind in {'records','baseline'}:
     if suffix in media and suffix!='.mp4' and not (suffix in {'.png','.svg'} and len(q.relative_to(top).parts)<=3):continue
     if suffix=='.mp4' and kind=='records':
      if video_counts[str(top)]>=2:continue
      video_counts[str(top)]+=1
    try:
     if q.is_symlink() and not q.resolve().is_relative_to(root):excluded.append(dict(path=rel,reason='external_symlink'));continue
     if not q.is_file():continue
     size=q.stat().st_size
     cap=64*1024**2 if kind in {'records','baseline'} else 256*1024**2
     if size>cap:excluded.append(dict(path=rel,reason='selected_file_over_cap',bytes=size));continue
     yield q
    except OSError as e:excluded.append(dict(path=rel,reason='read_error',error=type(e).__name__))
p.files=selected
jobs=[('frozen-baseline',frozen_roots,'frozen'),('inspire-source',source_roots,'source')]
jobs.append(('visual-runtime',[x/name for x in rgbd_roots for name in ['code','runtime_overlay','sensor_support','capture_support','runtime_repo','native_assets'] if (x/name).exists()],'source'))
jobs.append(('core60-results',[base],'baseline'))
for top in rgbd_roots:jobs.append((top.name,[top],'visual'))
remaining=[x for x in sorted((ROOT/'logs').iterdir()) if x!=OUT and x!=base and x not in rgbd_roots and not x.name.endswith('_staging')]
remaining += [ROOT/'eval_runs',ROOT/'_eval_archive']
jobs += [('historical-records',remaining,'records')]
plan=dict(source_root=str(ROOT),jobs=[dict(label=l,roots=[str(x.relative_to(ROOT)) for x in roots],kind=k) for l,roots,k in jobs],policy=dict(visual='all allowed image/depth/mask/point-cloud/video and text files in visual runs, excluding runtime duplicates, caches, setup attempts and interruption copies',baseline_history='text results/traces, selected shallow plots, all frozen Core60 videos, otherwise first 2 lexicographic videos per top-level run; frames and raw recovery snapshots omitted',native_solves='first available problem/result pair per cutamp_debug parent',source='allowed source/static asset types, <=32MiB',records_cap_MiB=64,visual_cap_MiB=256,official_weights='referenced existing Git LFS model or public base; not duplicated'))
(OUT/'archive_plan.json').write_text(json.dumps(plan,ensure_ascii=False,indent=2))
progress=OUT/'archive_progress.json';completed=[]
if len(sys.argv)>1:jobs=[x for x in jobs if x[0]==sys.argv[1]]
assert len(jobs)==1
for label,roots,kind in jobs:
 if (OUT/(label+'.verification.json')).exists():continue
 progress.write_text(json.dumps(dict(stage='packaging',current=label,completed=completed,total=len(jobs),unix=time.time())))
 m=p.package(ROOT,OUT,label,roots,kind)
 if not (OUT/(label+'.security_audit.json')).exists():audit.audit(OUT,label)
 # Audit validates tar members; independent verifier checks every part and file again.
 ar=OUT/'verify_layout';(ar/'manifests').mkdir(parents=True,exist_ok=True)
 # The verifier expects assets/ and manifests/; links only our generated output.
 if not (ar/'assets').exists():(ar/'assets').symlink_to(OUT,target_is_directory=True)
 import shutil
 shutil.copyfile(OUT/(label+'.manifest.json'),ar/'manifests'/(label+'.manifest.json'))
 proof=verify(ar,label);(OUT/(label+'.verification.json')).write_text(json.dumps(proof))
 completed.append(label);progress.write_text(json.dumps(dict(stage='verified',current=label,completed=completed,total=len(jobs),unix=time.time())))
 print('VERIFIED',label,proof['files'],proof['archive_bytes'],flush=True)
(OUT/('worker_finished_'+sys.argv[1]+'.json')).write_text(json.dumps(dict(completed=completed,unix=time.time())))
