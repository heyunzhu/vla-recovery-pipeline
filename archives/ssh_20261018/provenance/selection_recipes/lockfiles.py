from pathlib import Path
import sys,json
root=Path('/mnt/nas/gezuhao/xinghanbo');out=root/'logs/github_ssh_archive_20261018';sys.path.insert(0,str(out))
import package_ssh_research_assets as p
parents=[root,root/'code_snapshots',root/'overlays'];sources=[]
for parent in parents:
 for d in parent.iterdir():
  if not d.is_dir() or (parent==root and not (d.name.startswith('openvla-oft') or d.name in ['openpi','ASPIRE','LIBERO-PRO','LIBERO_src'])):continue
  for name in ['uv.lock','poetry.lock','Pipfile.lock','requirements.lock','.gitmodules']:
   q=d/name
   if q.is_file():sources.append(q)
p.TEXT.add('.lock');p.TEXT.add('')
p.package(root,out,'repro-lockfiles',sources,'dataset')
