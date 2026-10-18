from pathlib import Path
import sys,json,time,subprocess
O=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/github_inspire_archive_20261018');label='historical-records';manifest=O/(label+'.manifest.json')
if (O/'archive_finished.json').exists():print('Already finished');raise SystemExit
# Only generated partial archive files are moved; no original experiment files are modified.
valid=False
if manifest.exists():
 try:json.loads(manifest.read_text());valid=True
 except ValueError:pass
if not valid:
 backup=O/('interrupted_recycle_'+str(time.time_ns()));parts=list(O.glob(label+'.tar.gz.part*'))
 if parts or manifest.exists():
  backup.mkdir(exist_ok=False)
  for p in parts+([manifest] if manifest.exists() else []):
   assert p.resolve().is_relative_to(O.resolve());p.rename(backup/p.name)
# The finisher runs the already-deployed fast sanitizer, full audit, and SHA256 verification.
with (O/'resume-after-recycle.log').open('wb') as f:p=subprocess.Popen([sys.executable,'-u',str(O/'history_finisher.py')],stdout=f,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
record=dict(pid=p.pid,started=time.time(),scope=label,original_research_files_unchanged=True);(O/'resume_after_recycle.launch.json').write_text(json.dumps(record));print(json.dumps(record))
