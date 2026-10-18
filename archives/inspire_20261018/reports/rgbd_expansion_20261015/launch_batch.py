from pathlib import Path
import time,subprocess
b=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_expansion_20261015')
while not (b/'anchor_recheck/exitcode.txt').exists(): time.sleep(10)
f=(b/'batch_driver.log').open('wb')
p=subprocess.run(['/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/bin/python','/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_expansion_20261015/expansion_code/scripts/recovery/skill_pipeline/run_rgbd_expansion_batch.py',"--root",'/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo',"--out-root",'/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_expansion_20261015',"--visual-code",'/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_expansion_20261015/expansion_code'],stdout=f,stderr=subprocess.STDOUT)
(b/'batch_exitcode.txt').write_text(str(p.returncode))
