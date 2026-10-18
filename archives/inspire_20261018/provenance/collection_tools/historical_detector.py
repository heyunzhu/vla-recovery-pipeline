from pathlib import Path
import json,sys,hashlib,shutil,time
R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');O=R/'logs/github_inspire_archive_20261018';sys.path.insert(0,str(O))
import package_ssh_research_assets as p
import audit_ssh_archive as au
from restore_ssh_research_assets import verify
q=R/'logs/rgbd_native_mmdet_20261018/best_coco_bbox_mAP_epoch_10.pth';h=hashlib.sha256()
with q.open('rb') as f:
 for b in iter(lambda:f.read(8*1024**2),b''):h.update(b)
assert h.hexdigest()=='735b0e3ca9f8a44ad97dbaec97d15c61f18248e01d3e1479d0556d50f3388edd'
(O/'detector_artifact_identity.json').write_text(json.dumps(dict(native19=dict(path=str(q.relative_to(R)),bytes=q.stat().st_size,sha256=h.hexdigest(),existing_git_path='models/rgbd_dino_full_20261018/best_coco_bbox_mAP_epoch_10.pth'),historical_hf8=dict(path='logs/rgbd_dino_integration_20261016/hf_export_best',purpose='Actual historical export used by 300-episode RGB-D baseline; archival reproduction artifact, not a new parity endorsement')),indent=2))
source=R/'logs/rgbd_dino_integration_20261016/hf_export_best';assert source.is_dir();label='historical-hf8-detector'
m=p.package(R,O,label,[source],'checkpoint');assert any(x['path'].endswith(('.safetensors','.bin','.pth')) for x in m['files']);au.audit(O,label)
ar=O/'verify_layout';(ar/'manifests').mkdir(parents=True,exist_ok=True)
shutil.copyfile(O/(label+'.manifest.json'),ar/'manifests'/(label+'.manifest.json'));v=verify(ar,label);(O/(label+'.verification.json')).write_text(json.dumps(v))
(O/'historical_detector_finished.json').write_text(json.dumps(dict(completed=True,unix=time.time())));print('VERIFIED',label,v['files'],v['archive_bytes'],flush=True)
