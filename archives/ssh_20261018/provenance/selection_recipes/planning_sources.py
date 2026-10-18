from pathlib import Path
import sys,json,subprocess
root=Path('/mnt/nas/gezuhao/xinghanbo');out=root/'logs/github_ssh_archive_20261018';sys.path.insert(0,str(out))
import package_ssh_research_assets as p
extra={'.c','.cc','.cpp','.cxx','.h','.hpp','.cu','.cuh','.cmake','.dae','.ply','.off','.mtl','.sdf','.xacro','.lock',''};p.SOURCE.update(extra);p.TEXT.update({'.c','.cc','.cpp','.cxx','.h','.hpp','.cu','.cuh','.cmake','.lock',''})
roots=[root/'third_party/cuTAMP',root/'third_party/curobo'];states=[]
for repo in roots:
 def git(args):
  v=subprocess.run(['git','-c','safe.directory='+str(repo),'-C',str(repo),*args],capture_output=True,text=True,timeout=30);return dict(returncode=v.returncode,output=v.stdout,error=v.stderr[:300])
 states.append(dict(path=str(repo),head=git(['rev-parse','HEAD']),status=git(['status','--porcelain','--untracked-files=normal'])))
meta=out/'planning_source_states.json';meta.write_text(json.dumps(states,indent=2));roots.append(meta)
p.package(root,out,'planning-dependencies',roots,'source')
