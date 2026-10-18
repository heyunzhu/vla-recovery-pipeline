from pathlib import Path
import json,subprocess,base64,urllib.request,os,concurrent.futures,datetime,sys
r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive');a=r/'archives/inspire_20261018'
f=json.loads(subprocess.check_output(['git','lfs','ls-files','--json'],cwd=r,text=True))['files'];f=[x for x in f if x['name'].startswith('archives/inspire_20261018/assets/')];lookup={x['oid']:x for x in f};objects=list(lookup.values())
cred=subprocess.run(['git','credential','fill'],cwd=r,input='protocol=https\nhost=github.com\n\n',text=True,capture_output=True,env=dict(os.environ,GIT_TERMINAL_PROMPT='0'),check=True).stdout
v=dict(x.split('=',1) for x in cred.splitlines() if '=' in x);auth=base64.b64encode((v['username']+':'+v['password']).encode()).decode();rows=[]
path=a/'provenance/remote_lfs_verification.json'
old=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(files=[]);known={x['oid']:x for x in old['files'] if x.get('accessible') and x.get('total_bytes_match')}
rows=[known[x['oid']] for x in objects if x['oid'] in known];pending=[x for x in objects if x['oid'] not in known]
def check(o):
 x=lookup[o['oid']];row=dict(name=x['name'],oid=o['oid'],bytes=x['size'])
 if o.get('error'):return dict(row,accessible=False,error=o['error'].get('code'))
 action=o['actions']['download'];headers=dict(action.get('header',{}));headers['Range']='bytes=0-'+str(min(127,x['size']-1))
 with urllib.request.urlopen(urllib.request.Request(action['href'],headers=headers),timeout=90) as res:
  b=res.read(min(128,x['size']));cr=res.headers.get('Content-Range');cl=res.headers.get('Content-Length');total=int(cr.rsplit('/',1)[-1] if cr else cl)
  row.update(accessible=len(b)==min(128,x['size']),status=res.status,total_bytes_match=total==x['size'],content_range=cr,content_length=cl)
 return row
for i in range(0,len(pending),50):
 chunk=pending[i:i+50];body=json.dumps(dict(operation='download',transfers=['basic'],objects=[dict(oid=x['oid'],size=x['size']) for x in chunk])).encode()
 req=urllib.request.Request('https://github.com/heyunzhu/vla-recovery-pipeline.git/info/lfs/objects/batch',data=body,headers={'Authorization':'Basic '+auth,'Content-Type':'application/vnd.git-lfs+json','Accept':'application/vnd.git-lfs+json'})
 with urllib.request.urlopen(req,timeout=90) as res:batch=json.load(res)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for row in pool.map(check,batch['objects']):rows.append(row)
 path.write_text(json.dumps(dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),verification='Each unique object: authenticated GitHub LFS download action, bounded range read and exact total-length check. Complete archive part/file SHA256 checks performed independently on Inspire; readable-index also restored locally.',objects=len(rows),unique_object_bytes=sum(x['bytes'] for x in rows),files=rows),indent=2)+'\n',encoding='utf-8')
 print('REMOTE_CHECKED',len(rows),'of',len(objects),flush=True)
assert {x['oid'] for x in rows}==set(lookup)
assert all(x.get('accessible') and x.get('total_bytes_match') for x in rows)
print('ALL_REMOTE_OBJECTS_VERIFIED',len(objects),sum(x['size'] for x in objects),flush=True)
