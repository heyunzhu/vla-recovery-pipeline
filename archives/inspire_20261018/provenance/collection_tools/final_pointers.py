from pathlib import Path
import hashlib,json,time
r=Path('E:/VLA_recovery_workspace/vla-recovery-ssh-archive').resolve();a=r/'archives/inspire_20261018';partial=r/'tmp/inspire_incomplete_transfers';n=0
for f in (a/'manifests').glob('*.manifest.json'):
 m=json.loads(f.read_text(encoding='utf-8'))
 for part in m['parts']:
  assert Path(part['name']).name==part['name'];p=(a/'assets'/part['name']).resolve();assert p.is_relative_to((a/'assets').resolve())
  canonical=('version https://git-lfs.github.com/spec/v1\noid sha256:'+part['sha256']+'\nsize '+str(part['bytes'])+'\n').encode()
  if p.exists() and p.stat().st_size>1024:
   h=hashlib.sha256()
   with p.open('rb') as stream:
    for b in iter(lambda:stream.read(8*1024**2),b''):h.update(b)
   if p.stat().st_size==part['bytes'] and h.hexdigest()==part['sha256']:continue
   partial.mkdir(parents=True,exist_ok=True);target=partial/(p.name+'.'+str(time.time_ns()));assert target.resolve().is_relative_to(r/'tmp');p.rename(target);n+=1
  p.write_bytes(canonical)
print('Canonical archive pointers verified; incomplete own downloads preserved:',n)
