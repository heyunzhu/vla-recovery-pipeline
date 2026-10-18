from pathlib import Path
import os,hashlib,json,time
R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');O=R/'logs/github_inspire_archive_20261018';rows=[];start=time.time()
for top in sorted((R/'models').iterdir()):
 for base,dirs,files in os.walk(top,followlinks=False):
  dirs[:]=sorted(x for x in dirs if x not in {'.cache','.git','__pycache__'})
  for name in sorted(files):
   q=Path(base)/name
   if q.is_symlink() or not q.is_file():continue
   h=hashlib.sha256()
   with q.open('rb') as f:
    for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
   rows.append(dict(path=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=h.hexdigest()));(O/'base_model_hash_progress.json').write_text(json.dumps(dict(files=len(rows),bytes=sum(x['bytes'] for x in rows),elapsed_sec=time.time()-start)))
(O/'base_model_hashes.json').write_text(json.dumps(dict(complete=True,weights_archived=False,scope='Identity manifest of policy base model directories; model cache internals excluded',files=rows,elapsed_sec=time.time()-start),indent=2));print('BASE_MODEL_IDENTITY_DONE',len(rows),sum(x['bytes'] for x in rows),flush=True)
