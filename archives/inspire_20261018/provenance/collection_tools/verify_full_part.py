from pathlib import Path
import json,subprocess,base64,os,urllib.request,hashlib,time
w=Path(__file__).parent;r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018';m=json.loads((a/'manifests/rgbd_core60_20261017.manifest.json').read_text(encoding='utf-8'));part=next(x for x in m['parts'] if x['name'].endswith('part001'))
cred=subprocess.run(['git','credential','fill'],cwd=r,input='protocol=https\nhost=github.com\n\n',capture_output=True,text=True,env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),check=True).stdout;v=dict(l.split('=',1) for l in cred.splitlines() if '=' in l);auth=base64.b64encode((v['username']+':'+v['password']).encode()).decode()
body=json.dumps(dict(operation='download',transfers=['basic'],objects=[dict(oid=part['sha256'],size=part['bytes'])])).encode();req=urllib.request.Request('https://github.com/heyunzhu/vla-recovery-pipeline.git/info/lfs/objects/batch',data=body,headers={'Authorization':'Basic '+auth,'Content-Type':'application/vnd.git-lfs+json','Accept':'application/vnd.git-lfs+json'})
with urllib.request.urlopen(req,timeout=90) as res:b=json.load(res)
act=b['objects'][0]['actions']['download'];dest=w/'verified_core60_part001.bin';h=hashlib.sha256();n=0;start=time.time()
with urllib.request.urlopen(urllib.request.Request(act['href'],headers=act.get('header',{})),timeout=120) as stream,dest.open('wb') as f:
 while True:
  block=stream.read(8*1024**2)
  if not block:break
  f.write(block);h.update(block);n+=len(block)
assert n==part['bytes'] and h.hexdigest()==part['sha256']
proof=dict(path='archives/inspire_20261018/assets/'+part['name'],expected_sha256=part['sha256'],downloaded_sha256=h.hexdigest(),bytes=n,verified=True,elapsed_sec=time.time()-start,method='Full authenticated GitHub LFS download; SHA256 over every byte')
(a/'provenance/core60_part001_full_remote_sha256.json').write_text(json.dumps(proof,indent=2),encoding='utf-8');print(json.dumps(proof),flush=True)
