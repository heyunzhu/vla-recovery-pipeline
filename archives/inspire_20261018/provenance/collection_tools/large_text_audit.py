from pathlib import Path
import json,hashlib,sys,time
O=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/github_inspire_archive_20261018');sys.path.insert(0,str(O))
from package_ssh_research_assets import TEXT,sanitize
m=json.loads((O/'historical-records.manifest.json').read_text());rows=[]
for x in m['files']:
 if x.get('source_bytes',0)<=32*1024**2 or Path(x['path']).suffix.lower() not in TEXT:continue
 p=Path(m['source_root'])/x['path'];data=p.read_bytes();sha=hashlib.sha256(data).hexdigest()
 cleaned,n=sanitize(data,p.suffix.lower())
 row=dict(path=x['path'],bytes=len(data),sha256=sha,source_equals_archived=sha==x['sha256'],sanitizer_unchanged=cleaned==data,findings=n)
 rows.append(row)
 (O/'large_text_audit.progress.json').write_text(json.dumps(dict(checked=len(rows),total=10)))
report=dict(label='historical-records',completed=True,policy='Apply original full sanitizer without 32MiB cap; verify source SHA equals archived member SHA',files=rows,all_clean=all(x['source_equals_archived'] and x['sanitizer_unchanged'] and x['findings']==0 for x in rows))
(O/'large_text_audit.json').write_text(json.dumps(report,indent=2))
assert report['all_clean'],'Findings require archive scrub before publication'
