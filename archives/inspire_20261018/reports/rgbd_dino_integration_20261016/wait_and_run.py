import time,runpy
from pathlib import Path
r=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_dino_integration_20261016')
for i in range(240):
 if (r/'hf_export_best.tar').stat().st_size==696176640 and (r/'source_overlay.tar.gz').stat().st_size==28467260 and (r/'dino440_deps/transformers/__init__.py').exists():break
 time.sleep(5)
else:raise RuntimeError('transfer or dependency setup did not complete')
runpy.run_path(str(r/'recovery_batch.py'),run_name='__main__')
