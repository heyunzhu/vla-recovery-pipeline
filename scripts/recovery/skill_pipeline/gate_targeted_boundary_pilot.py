"""One-shot startup gate; launch pilot only after valid canary and initial states."""
import json
import os
import subprocess
import time
from pathlib import Path

R=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
O=R/'logs/skill_boundary_pilot_20261010'
PY=R/'envs/rlinf-openpi/bin/python'


def main():
    validation=json.loads((O/'all_init_validation.json').read_text())
    assert len(validation)==100 and all(r['valid'] for r in validation)
    canary_pid=int((O/'canary_v2.pid').read_text())
    deadline=time.monotonic()+1800
    while not (O/'canary_v2.done').exists():
        if list((O/'canary_v2').glob('*/.infrastructure_invalid')) or list((O/'canary_v2').glob('*/.failed')):
            raise RuntimeError('canary invalid; refusing pilot')
        try:os.kill(canary_pid,0)
        except ProcessLookupError:raise RuntimeError('canary stopped without completion')
        if time.monotonic()>deadline:raise TimeoutError('canary gate timed out')
        time.sleep(15)
    for path in (O/'canary_v2').glob('*/run/task*/ep*/episode.json'):
        ep=json.loads(path.read_text())
        assert ep['recovery_calls']>=1
        qs=[json.loads(l) for l in (path.parent/'query_trace.jsonl').read_text().splitlines()]
        assert qs[0]['mode']=='recovery'
        assert qs[0]['recovery_hints']['grasp_profile']=='cream_cheese_flat_box_topdown_deep_v1'
    subprocess.run([str(PY),str(O/'launch_targeted_boundary_pilot.py'),'start','--lanes','4'],check=True)
    (O/'pilot.started').write_text('4 lanes admitted after canary/initial validity checks\n')


if __name__=='__main__':main()
