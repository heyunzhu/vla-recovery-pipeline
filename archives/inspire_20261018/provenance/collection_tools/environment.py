from pathlib import Path
import json,sys,subprocess,importlib.metadata,os
r=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');o=r/'logs/github_inspire_archive_20261018';d=dict(python=sys.version,environments=[],base_models=[],old_backups=[])
for env in sorted((r/'envs').iterdir()):
 if not env.is_dir():continue
 row=dict(path=str(env.relative_to(r)),packages=[],pth=[])
 for sp in env.glob('lib/python*/site-packages'):
  for dist in importlib.metadata.distributions(path=[str(sp)]):
   try:row['packages'].append(dict(name=dist.metadata.get('Name'),version=dist.version))
   except Exception:pass
  for p in sp.glob('*.pth'):
   if p.stat().st_size<65536:row['pth'].append(dict(path=str(p.relative_to(r)),content=p.read_text(errors='replace')))
 d['environments'].append(row)
for model in sorted((r/'models').iterdir()):
 row=dict(path=str(model.relative_to(r)),children=[dict(name=x.name,bytes=x.stat().st_size if x.is_file() else None) for x in sorted(model.iterdir())]);d['base_models'].append(row)
for p in (r/'_archive').rglob('*'):
 if p.is_file():d['old_backups'].append(dict(path=str(p.relative_to(r)),bytes=p.stat().st_size))
(o/'environment_inventory.json').write_text(json.dumps(d,indent=2))
print(json.dumps(dict(environments=[(x['path'],len(x['packages'])) for x in d['environments']],old_backups=d['old_backups'])))
