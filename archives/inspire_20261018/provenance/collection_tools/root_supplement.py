from pathlib import Path
import sys,json,shutil,time
R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');O=R/'logs/github_inspire_archive_20261018';sys.path.insert(0,str(O))
import package_ssh_research_assets as p
import audit_ssh_archive as au
from restore_ssh_research_assets import verify
p.PRUNE |= {'cache','caches','envs','home','.codex','.roborsi','tmp','native_env','venv','build','dist','analysis_outputs'}
source=[x for x in sorted(R.iterdir()) if x.is_file() and x.suffix.lower() in p.SOURCE]
source += [R/'roborsi_repro'/x for x in ['code','patches','scripts','activate_roborsi.sh']]
history=[R/'roborsi_repro/logs'];original=p.files
(O/'root_supplement_scope.json').write_text(json.dumps(dict(source=[str(x.relative_to(R)) for x in source],history=[str(x.relative_to(R)) for x in history],explicitly_omitted=['roborsi_repro/home','roborsi_repro/cache','roborsi_repro/envs','raw Git bundles and nested tar/zip containers']),indent=2))
def selected(root,roots,kind,excluded):
 yield from original(root,source,'source',excluded)
 yield from original(root,history,'history',excluded)
p.files=selected;label='root-scripts-and-roborsi';p.package(R,O,label,source+history,'source');au.audit(O,label)
ar=O/'verify_layout';shutil.copyfile(O/(label+'.manifest.json'),ar/'manifests'/(label+'.manifest.json'));v=verify(ar,label);(O/(label+'.verification.json')).write_text(json.dumps(v));print('VERIFIED',label,v['files'],v['archive_bytes'],flush=True)
(O/'root_supplement_finished.json').write_text(json.dumps(dict(completed=True,unix=time.time())))
