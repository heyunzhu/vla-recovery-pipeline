from pathlib import Path
import subprocess,base64,sys
ROOT='/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo'
REMOTE=ROOT+'/logs/github_inspire_archive_20261018'
CLI=['wsl','-d','Ubuntu','--','/home/dx/.local/bin/inspire','notebook']
TARGET=['xinghanbo-eval','--workspace','可上网GPU资源']
def run(args,timeout=300):
 r=subprocess.run(CLI+args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=timeout)
 if r.returncode:raise RuntimeError((r.stdout+r.stderr).decode('utf-8',errors='replace')[-3500:])
 return r.stdout.decode('utf-8',errors='replace')
def execute(code,timeout=300):
 cmd=ROOT+"/envs/rlinf-openpi/bin/python -c 'import base64;exec(base64.b64decode(\""+base64.b64encode(code.encode()).decode()+"\"))'"
 return run(['exec',*TARGET,cmd,'--timeout',str(timeout)],timeout+40)
def local(p):
 p=Path(p).resolve();return '/mnt/'+p.drive[0].lower()+p.as_posix()[2:]
def upload(p,target):return run(['scp',*TARGET,local(p),target,'--timeout','180'],220)
def download(source,p):return run(['scp',*TARGET,'--download',source,local(p),'--timeout','600'],660)
if __name__=='__main__':
 if sys.argv[1]=='exec':print(execute(Path(sys.argv[2]).read_text(encoding='utf-8-sig'),int(sys.argv[3]) if len(sys.argv)>3 else 300))
 elif sys.argv[1]=='upload':print(upload(sys.argv[2],sys.argv[3]))
 elif sys.argv[1]=='download':print(download(sys.argv[2],sys.argv[3]))
