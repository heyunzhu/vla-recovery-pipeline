from pathlib import Path
import sys,json
root=Path('/mnt/nas/gezuhao/xinghanbo');out=root/'logs/github_ssh_archive_20261018';sys.path.insert(0,str(out))
from package_ssh_research_assets import package
base=root/'logs/liberopro_6cell_baseline_seed51_55_n5_20260914';sources=[];selections=[];seen=set()
for suite in sorted(p for p in base.iterdir() if p.is_dir() and p.name.startswith('libero_')):
 for ep in sorted(suite.glob('task*/ep*/episode.json')):
  row=json.loads(ep.read_text());success=row.get('success');key=(suite.name,success)
  if key in seen:continue
  videos=sorted(ep.parent.glob('*.mp4'))
  videos=[p for p in videos if p.stat().st_size<64*1024**2]
  if not videos:continue
  chosen=videos[:1];sources.extend([ep,*chosen]);selections.append(dict(suite=suite.name,success=success,episode=str(ep.relative_to(root)),videos=[str(p.relative_to(root)) for p in chosen]));seen.add(key)
extra=root/'logs/pro_object_axis_20261003_object_pack_mrs200/pack'
if extra.exists():
 for ep in sorted(extra.rglob('episode.json')):
  row=json.loads(ep.read_text());key=('object_perturbation',row.get('success'))
  if key in seen:continue
  videos=[p for p in sorted(ep.parent.glob('*.mp4')) if p.stat().st_size<64*1024**2]
  if not videos:continue
  sources.extend([ep,videos[0]]);selections.append(dict(suite=key[0],success=key[1],episode=str(ep.relative_to(root)),videos=[str(videos[0].relative_to(root))]));seen.add(key)
p=out/'video_selection.json';p.write_text(json.dumps(dict(policy='first available success/failure video per suite in sorted historical paths; qualitative examples only',selections=selections),indent=2));sources.append(p)
package(root,out,'representative-videos',sources,'dataset');print('SELECTED_VIDEOS',len(selections))
