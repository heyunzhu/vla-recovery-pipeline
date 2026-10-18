from pathlib import Path
import json,subprocess
b=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_ten_tasks_20261015')
with (b/'resume_driver.log').open('wb') as f:rc=subprocess.run(json.loads((b/'resume_command.json').read_text()),stdout=f,stderr=subprocess.STDOUT).returncode
(b/'batch_exitcode.txt').write_text(str(rc))
