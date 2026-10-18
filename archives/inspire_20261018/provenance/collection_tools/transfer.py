from pathlib import Path
import json,subprocess,os,base64,urllib.request,time,argparse,hashlib
from transport import execute,download,ROOT,REMOTE,CLI,TARGET
w=Path(__file__).parent;r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018';state=w/'transfer_state.json'
def save(d):state.write_text(json.dumps(d,indent=2),encoding='utf-8')
def batch(objects):
 cred=subprocess.run(['git','credential','fill'],cwd=r,input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),check=True).stdout
 v=dict(l.split('=',1) for l in cred.splitlines() if '=' in l);auth=base64.b64encode((v['username']+':'+v['password']).encode()).decode()
 body=json.dumps(dict(operation='upload',transfers=['basic'],ref=dict(name='refs/heads/codex/inspire-archive-20261018'),objects=[dict(oid=o['oid'],size=o['size']) for o in objects])).encode()
 req=urllib.request.Request('https://github.com/heyunzhu/vla-recovery-pipeline.git/info/lfs/objects/batch',data=body,headers={'Authorization':'Basic '+auth,'Accept':'application/vnd.git-lfs+json','Content-Type':'application/vnd.git-lfs+json'})
 with urllib.request.urlopen(req,timeout=90) as f:d=json.load(f)
 assert all(not x.get('error') for x in d['objects']);return d

def dispatch(label,m):
 objects=[dict(name=x['name'],oid=x['sha256'],size=x['bytes']) for x in m['parts']];b=batch(objects);lookup={x['oid']:x for x in objects}
 payload=[dict(lookup[x['oid']],upload=x.get('actions',{}).get('upload')) for x in b['objects']]
 phase=label+'.upload';priv=w/(phase+'.private.json');priv.write_text(json.dumps(b),encoding='utf-8')
 code="""from pathlib import Path
import sys,json,os,subprocess,time
out=Path(REMOTE);phase=PHASE;p=out/(phase+'.private.json')
fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'wb') as f:f.write(sys.stdin.buffer.read())
with (out/(phase+'.log')).open('wb') as f:proc=subprocess.Popen([sys.executable,str(out/'upload_driver.py'),'--phase',phase],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
print(json.dumps(dict(pid=proc.pid,phase=phase)))
""".replace('REMOTE',repr(REMOTE)).replace('PHASE',repr(phase))
 cmd=ROOT+"/envs/rlinf-openpi/bin/python -c 'import base64;exec(base64.b64decode(\""+base64.b64encode(code.encode()).decode()+"\"))'"
 result=subprocess.run(CLI+['exec',*TARGET,'--stdin',cmd,'--timeout','60'],input=json.dumps(payload).encode(),capture_output=True,timeout=100)
 if result.returncode:raise RuntimeError('Private upload dispatch failed '+label)
 print('UPLOAD_DISPATCHED',label,len(objects),m['archive_bytes'],flush=True)

def register(label,receipt):
 priv=w/(label+'.upload.private.json');b=json.loads(priv.read_text(encoding='utf-8'));actions={x['oid']:x for x in b['objects']};rows=[]
 assert receipt['complete'] and receipt['success'],('Remote upload failed',label,[x.get('http_status') or x.get('error_type') for x in receipt['objects'] if not x['success']])
 for row in receipt['objects']:
  action=actions[row['oid']].get('actions',{}).get('verify');res=dict(name=row['name'],oid=row['oid'],bytes=row['size'])
  if action:
   headers=dict(action.get('header',{}));headers['Content-Type']='application/vnd.git-lfs+json'
   req=urllib.request.Request(action['href'],data=json.dumps(dict(oid=row['oid'],size=row['size'])).encode(),headers=headers)
   with urllib.request.urlopen(req,timeout=90) as f:assert 200<=f.status<300;f.read(4096);res['registered']=True
  else:res['registered']=True
  rows.append(res)
 (a/'provenance'/(label+'.upload_receipt.json')).write_text(json.dumps(dict(complete=True,objects=rows),indent=2),encoding='utf-8')
 priv.unlink()

if __name__=='__main__':
 d=json.loads(state.read_text()) if state.exists() else dict(dispatched=[],complete=[]);start=time.time()
 while True:
  status_code="""from pathlib import Path
import json
p=Path(REMOTE);done=[];receipts={}
for x in sorted(p.glob('*.verification.json')):
 label=x.name[:-len('.verification.json')]
 if (p/(label+'.security_audit.json')).exists():done.append(label)
for x in sorted(p.glob('*.upload.receipt.json')):
 v=json.loads(x.read_text())
 if v.get('complete'):receipts[x.name[:-len('.upload.receipt.json')]]=v
print(json.dumps(dict(ready=done,receipts=receipts,finished=(p/'archive_finished.json').exists())))
""".replace('REMOTE',repr(REMOTE))
  out=execute(status_code,90);status=json.loads(out[:out.rfind('}')+1])
  for label,receipt in status['receipts'].items():
   if label in d['complete']:continue
   register(label,receipt);d['complete'].append(label);save(d);print('REGISTERED',label,flush=True)
  for label in status['ready']:
   if label in d['dispatched']:continue
   if len(set(d['dispatched'])-set(d['complete']))>=2:break
   for suffix,folder in [('.manifest.json','manifests'),('.security_audit.json','provenance'),('.verification.json','provenance')]:download(REMOTE+'/'+label+suffix,a/folder/(label+suffix))
   m=json.loads((a/'manifests'/(label+'.manifest.json')).read_text(encoding='utf-8'));v=json.loads((a/'provenance'/(label+'.verification.json')).read_text(encoding='utf-8'));assert v['verified'] and v['files']==len(m['files']) and v['archive_bytes']==m['archive_bytes']
   for x in m['parts']:
    assert Path(x['name']).name==x['name'];p=a/'assets'/x['name'];pointer=f"version https://git-lfs.github.com/spec/v1\noid sha256:{x['sha256']}\nsize {x['bytes']}\n";p.write_bytes(pointer.encode('ascii'))
   dispatch(label,m);d['dispatched'].append(label);save(d)
  if status['finished'] and set(status['ready'])==set(d['complete']):break
  if time.time()-start>14400:raise TimeoutError('transfer controller 4h budget; state saved')
  time.sleep(15)
 print('ALL_ARCHIVES_UPLOADED',len(d['complete']),flush=True)
