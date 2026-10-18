from pathlib import Path
import hashlib
import json
import zipfile

root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016')
selected=[]
for path in sorted(root.rglob('*')):
    if not path.is_file():continue
    rel=path.relative_to(root)
    if '__pycache__' in rel.parts or rel.parts[0]=='dino440_deps':continue
    if path.name in ('hf_export_best.tar','recovery_evidence.zip','recovery_evidence_manifest.json'):continue
    if path.suffix=='.safetensors':continue
    if rel.parts[0] in ('code','code_ownership8') and path.suffix not in ('.py','.json','.sh','.md','.txt'):continue
    if path.suffix in ('.pyc','.lock'):continue
    selected.append(path)
with zipfile.ZipFile(root/'recovery_evidence.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for path in selected:archive.write(path,path.relative_to(root))
path=root/'recovery_evidence.zip'
digest=hashlib.sha256(path.read_bytes()).hexdigest()
manifest={'file':path.name,'bytes':path.stat().st_size,'sha256':digest,'files':len(selected),
          'excluded':'Model weight tensors and installed dependencies; retained on server with pinned paths/hashes.'}
(root/'recovery_evidence_manifest.json').write_text(json.dumps(manifest,indent=2))
print(json.dumps(manifest),flush=True)
