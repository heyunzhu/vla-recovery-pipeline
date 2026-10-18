"""Resume the immutable pilot queue without overwriting interrupted attempts."""
import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import launch_targeted_boundary_pilot as base

S=base.O/'resume_v1'
INFRA=('runner_failed:', 'No such file or directory', 'ModuleNotFoundError', 'Traceback')


def completed(job):
    found={}
    roots=[base.O/'jobs'/job['id'],*sorted((S/'attempts'/job['id']).glob('*'))]
    for root in roots:
        cmd=root/'command.json'
        if not cmd.exists():
            continue
        c=json.loads(cmd.read_text())
        expected=hashlib.sha256((base.O/'targeted_boundary_entrypoint.py').read_bytes()).hexdigest()
        assert c['entrypoint_sha256']==expected, 'entrypoint changed; cannot mix results'
        for ep in sorted(root.glob('run/task*/ep*/episode.json')):
            try:
                e=json.loads(ep.read_text())
                idx=int(ep.parent.name[2:])
                if not (0<=idx<5 and e.get('seed')==idx+1 and e.get('init_state_idx')==idx and isinstance(e.get('success'),bool)):
                    raise ValueError('episode identity mismatch: '+str(ep))
                trace=ep.parent/'recovery_trace.jsonl'
                rows=[json.loads(l) for l in trace.read_text().splitlines()]
                if any(any(s in str(r.get('error') or '') for s in INFRA) for r in rows):
                    raise RuntimeError('infrastructure error: '+str(ep))
                found.setdefault(idx,str(ep))
            except json.JSONDecodeError:
                # An interrupted final write is not a completed sample.
                continue
    return found


def lane(lane_id,session):
    jobs=json.loads((base.O/'manifest.json').read_text())['jobs']
    original_command=base.command
    for i,job in enumerate(jobs):
        if i%4!=lane_id:
            continue
        done=completed(job)
        missing=[idx for idx in range(5) if idx not in done]
        while missing:
            start=missing[0]
            end=start+1
            while end in missing:
                end+=1
            attempt=S/'attempts'/job['id']/(session+f'_from{start:02d}')
            def command(j,d,n,_start=start):
                return original_command(j,d,n)+['--episode_index_start',str(_start)]
            base.command=command
            print('RUN',job['id'],'indices',list(range(start,end)),str(attempt),flush=True)
            base.run(job,attempt,end-start)
            done=completed(job)
            missing=[idx for idx in range(5) if idx not in done]
        print('DONE',job['id'],json.dumps(done),flush=True)


def main():
    p=argparse.ArgumentParser()
    p.add_argument('mode',choices=['start','lane','status'])
    p.add_argument('--lane',type=int)
    p.add_argument('--session')
    a=p.parse_args()
    if a.mode=='lane':
        lane(a.lane,a.session)
        return
    jobs=json.loads((base.O/'manifest.json').read_text())['jobs']
    if a.mode=='status':
        print(json.dumps({j['id']:completed(j) for j in jobs},indent=2))
        return
    assert (base.O/'canary_v2.done').exists()
    v=json.loads((base.O/'all_init_validation.json').read_text())
    assert len(v)==100 and all(r['valid'] for r in v)
    S.mkdir(parents=True,exist_ok=True)
    # A kernel-held lock, not a stale PID, prevents overlapping restart sessions.
    with (S/'master.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        session=time.strftime('%Y%m%dT%H%M%SZ',time.gmtime())+'_'+uuid.uuid4().hex[:6]
        d=S/'sessions'/session
        d.mkdir(parents=True)
        (S/'active_session.json').write_text(json.dumps(dict(session=session,pid=os.getpid())))
        hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in base.O.glob('*.py')}
        (d/'implementation.json').write_text(json.dumps(hashes,indent=2))
        children=[]
        handles=[]
        for k in range(4):
            h=(d/f'lane{k}.log').open('w');handles.append(h)
            proc=subprocess.Popen([str(base.PY),str(base.O/'resume_targeted_boundary_pilot.py'),'lane','--lane',str(k),'--session',session],stdout=h,stderr=subprocess.STDOUT)
            children.append(proc)
            (d/f'lane{k}.pid').write_text(str(proc.pid))
            print('STARTED',k,proc.pid,flush=True)
        codes=[proc.wait() for proc in children]
        for h in handles:h.close()
        (d/'exit_codes.json').write_text(json.dumps(codes))
        if any(codes):raise RuntimeError('lane failed; inspect session logs: '+session)
        results={j['id']:completed(j) for j in jobs}
        assert all(len(r)==5 for r in results.values())
        (S/'completed_index.json').write_text(json.dumps(results,indent=2))
        (S/'all.done').write_text('180 unique episodes completed\n')


if __name__=='__main__':main()
