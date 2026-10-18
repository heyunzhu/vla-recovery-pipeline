from pathlib import Path
import subprocess,json
b=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_ten_tasks_20261015')
with (b/'batch_driver.log').open('wb') as f:rc=subprocess.run(json.loads((b/'batch_command.json').read_text()),stdout=f,stderr=subprocess.STDOUT).returncode
(b/'batch_exitcode.txt').write_text(str(rc))
