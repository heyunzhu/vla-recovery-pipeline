from pathlib import Path
import os,sys,json,re
root=Path('/mnt/nas/gezuhao/xinghanbo');out=root/'logs/github_ssh_archive_20261018';sys.path.insert(0,str(out))
import package_ssh_research_assets as p
prune=p.PRUNE|{'frames','snapshots','resident_vision','images','images640','images256','instance_masks640','instance_masks256','states','point_clouds','pointclouds','dino','sam2','runtime','runtime_repo','runtime_overlay','runtime_snapshot','frozen_runtime','code','code_snapshot','code_snapshots','third_party','checkpoints','datasets','collection','interrupted','startup_attempts','deployment_attempts','outputs','rollouts'}
important=re.compile(r'episode|summary|result|metric|config|manifest|command|protocol|taxonomy|calibration|audit|launch|checkpoint|coverage|binding|grounding|source|split|scalars|report|status|progress',re.I)
roots=[x for x in sorted((root/'logs').iterdir()) if x.is_dir() and x!=out];roots += [root/'models/rgbd_dino_finetune_20261015',root/'models/rgbd_dino_full_20261018'];source_runs=[x.name for x in roots if x.parent.name=='logs']
policy=dict(source_runs=source_runs,maximum_depth=8,keep='contracts, scripts/configs/docs, per-episode outcomes, metrics/audits and first native solve pair per run',raw_debug_intermediates='not exhaustively archived; originals retained',max_file_bytes=16*1024**2)
policy_path=out/'history_selection_policy.json';policy_path.write_text(json.dumps(policy,indent=2))
def selected(root,roots,kind,excluded):
 seen=set();debug_selected=set()
 for top in roots:
  if not top.exists():continue
  for base,dirs,names in os.walk(top,followlinks=False):
   b=Path(base);depth=len(b.relative_to(top).parts)
   dirs[:]=[d for d in sorted(dirs) if d not in prune and not d.startswith(('runtime_','code_snapshot'))]
   if depth>=8:dirs[:]=[]
   debug=any(x in b.parts for x in ('cutamp_debug','solver_inputs','solver_outputs','native_debug'))
   if debug:
    dirs[:]=[]
    if str(top) in debug_selected:continue
    problem=next((n for n in sorted(names) if n.endswith('.problem.json')),None)
    if problem:
     stem=problem[:-len('.problem.json')];names=[problem]+([stem+'.result.json'] if stem+'.result.json' in names else []);debug_selected.add(str(top))
    else:continue
   for name in sorted(names):
    q=b/name;rel=q.relative_to(root).as_posix()
    if rel in seen:continue
    seen.add(rel)
    if '\\' in rel or p.SECRET_NAME.search(name):excluded.append(dict(path=rel,reason='credential_or_nonportable_path'));continue
    suffix=q.suffix.lower()
    if suffix not in p.TEXT|{'.png','.svg'}:continue
    if suffix=='.log' and 'rgbd_dino_' not in rel:continue
    if suffix in ('.png','.svg') and depth>3:continue
    if suffix=='.json' and not debug and depth>2 and not important.search(name):continue
    if suffix=='.jsonl' and depth>3 and not re.search(r'prompt|record|episode|pair|corpus|skill|audit',name,re.I):continue
    if not q.is_file():continue
    if q.is_symlink() and not q.resolve().is_relative_to(root):excluded.append(dict(path=rel,reason='external_symlink'));continue
    size=q.stat().st_size
    if size>16*1024**2:excluded.append(dict(path=rel,reason='selected_record_over_16MiB',bytes=size));continue
    yield q
 yield policy_path
p.files=selected
p.package(root,out,'experiment-records',roots,'history')
(out/'selected-history.finished.json').write_text('{"complete":true}')
