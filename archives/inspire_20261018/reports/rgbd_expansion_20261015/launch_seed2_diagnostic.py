from pathlib import Path
import subprocess,time
b=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_expansion_20261015')
while not (b/'batch_exitcode.txt').exists():time.sleep(10)
p=b/'goal_plate_init1/visual_seed2_diagnostic'
with (p/'driver.log').open('wb') as f:rc=subprocess.run(['bash',str(p/'command.sh')],stdout=f,stderr=subprocess.STDOUT).returncode
(p/'exitcode.txt').write_text(str(rc))
