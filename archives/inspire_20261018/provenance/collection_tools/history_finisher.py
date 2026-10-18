from pathlib import Path
import sys,subprocess,json,time
O=Path(__file__).resolve().parent;label='historical-records';plan=json.loads((O/'archive_plan.json').read_text());labels=[x['label'] for x in plan['jobs']]
with (O/'historical-fast.worker.log').open('wb') as f:
 p=subprocess.Popen([sys.executable,'-u',str(O/'collect_worker.py'),label],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL)
 (O/'parallel_status.json').write_text(json.dumps(dict(completed=[x for x in labels if x!=label],total=len(labels),running={label:p.pid},queued=0,failed={},unix=time.time())))
 rc=p.wait()
assert rc==0 and all((O/(x+'.verification.json')).exists() for x in labels)
(O/'parallel_status.json').write_text(json.dumps(dict(completed=labels,total=len(labels),running={},queued=0,failed={},unix=time.time())))
(O/'archive_finished.json').write_text(json.dumps(dict(completed=labels,concurrency=3,jsonl_fastpath_applied_to_history=True,unix=time.time())))
