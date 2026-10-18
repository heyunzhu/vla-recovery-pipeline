from pathlib import Path
import os,sys,json,time,subprocess,signal
O=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/github_inspire_archive_20261018');plan=json.loads((O/'archive_plan.json').read_text());labels=[x['label'] for x in plan['jobs']]
main=json.loads((O/'collector.launch.json').read_text())['pid']
while not (O/'visual-runtime.verification.json').exists():
 if not Path('/proc',str(main)).exists():raise RuntimeError('Original collector ended before handoff boundary')
 time.sleep(2)
p=Path('/proc',str(main));stopped=False
if p.exists():
 cmd=(p/'cmdline').read_bytes();assert str(O/'collect.py').encode() in cmd and 'python' in Path(os.readlink(p/'exe')).name
 os.kill(main,signal.SIGTERM);stopped=True;time.sleep(2)
# Preserve only generated unfinished archive parts before retrying their label.
backup=O/'interrupted_serial_collector_20261019';moved=[]
for label in labels:
 if (O/(label+'.manifest.json')).exists():continue
 for part in O.glob(label+'.tar.gz.part*'):
  assert part.resolve().is_relative_to(O.resolve());backup.mkdir(exist_ok=True);part.rename(backup/part.name);moved.append(part.name)
# Give each independent worker a distinct progress file.
helper=O/'package_ssh_research_assets.py';s=helper.read_text();s=s.replace("out/'status.json'","out/(label+'.progress.json')");helper.write_text(s)
(O/'parallel_handoff.json').write_text(json.dumps(dict(stopped_own_serial_pid=main if stopped else None,preserved_generated_partial_parts=moved,concurrency=3,original_research_files_unchanged=True,unix=time.time())))
priority=['rgbd_native_mmdet_20261018','rgbd_known_model_20261018','rgbd_core60_20261017','core60-results']
queue=[x for x in priority+labels if x in labels];queue=list(dict.fromkeys(queue));running={};failed={}
while queue or running:
 done={x for x in labels if (O/(x+'.verification.json')).exists()}
 for label in list(running):
  proc,log=running[label];rc=proc.poll()
  if rc is not None:
   log.close();del running[label]
   if rc!=0 or label not in done:failed[label]=rc
 if failed:queue=[]
 while len(running)<3 and queue:
  label=queue.pop(0)
  if label in done:continue
  f=(O/(label+'.worker.log')).open('wb');proc=subprocess.Popen([sys.executable,'-u',str(O/'collect_worker.py'),label],stdin=subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);running[label]=(proc,f)
 (O/'parallel_status.json').write_text(json.dumps(dict(completed=sorted(done),total=len(labels),running={x:v[0].pid for x,v in running.items()},queued=len(queue),failed=failed,unix=time.time())))
 time.sleep(3)
if failed:raise RuntimeError('Workers failed: '+repr(failed))
assert all((O/(x+'.verification.json')).exists() for x in labels)
(O/'archive_finished.json').write_text(json.dumps(dict(completed=labels,concurrency=3,unix=time.time())))
print('PARALLEL_ARCHIVE_FINISHED',len(labels),flush=True)
