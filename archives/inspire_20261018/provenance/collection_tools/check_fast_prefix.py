from pathlib import Path
import hashlib,json
O=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/github_inspire_archive_20261018');old=O/'interrupted_slow_history_20261019';rows=[]
def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
 return h.hexdigest()
for p in sorted(old.glob('historical-records.tar.gz.part*')):
 q=O/p.name
 if p.stat().st_size==250_000_000 and q.exists() and q.stat().st_size==250_000_000:
  a=digest(p);b=digest(q);assert a==b;rows.append(dict(part=p.name,bytes=250_000_000,sha256=a,identical=True))
report=dict(scope='Complete common prefix parts from preserved interrupted slow run versus accelerated regenerated run; this is not a complete old archive',parts=rows)
(O/'history_fast_prefix_equivalence.json').write_text(json.dumps(report,indent=2));print('IDENTICAL_COMMON_PREFIX_PARTS',len(rows),sum(x['bytes'] for x in rows))
