from pathlib import Path
import json,os,subprocess,time,shutil,hashlib
ROOT=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');RUN=ROOT/'logs/rgbd_native_mmdet_20261018'
def alive(name,needle):
 p=RUN/name
 if not p.exists():return False
 pid=json.loads(p.read_text())['pid'];proc=Path('/proc')/str(pid)/'cmdline'
 return proc.exists() and needle in proc.read_text().replace('\x00',' ') and str(RUN) in proc.read_text().replace('\x00',' ')
if (RUN/'finished.json').exists():
 print('BATCH_COMPLETE');raise SystemExit(0)
if alive('batch_launch.json','run_rgbd_core60_batch.py'):
 print('BATCH_RUNNING');raise SystemExit(0)
if alive('setup_launch.json','setup_and_run.py'):
 print('SETUP_RUNNING');raise SystemExit(0)
if (RUN/'startup_blocked.json').exists() or (RUN/'setup_error.txt').exists():
 print('ACTION_REQUIRED');raise SystemExit(0)
relative='scripts/recovery/skill_pipeline/run_rgbd_core60_batch.py'
shutil.copyfile(RUN/'run_rgbd_core60_batch.py',RUN/'code'/relative)
manifest=json.loads((RUN/'protocol_manifest.json').read_text());manifest['source_hashes'][relative]=hashlib.sha256((RUN/'code'/relative).read_bytes()).hexdigest();(RUN/'protocol_manifest.json').write_text(json.dumps(manifest,indent=2))
if not alive('policy_launch.json','shared_benchmark_policy.py'):
 for name in ['policy_ready.json','policy_endpoint.json']:(RUN/name).unlink(missing_ok=True)
 base=json.loads((ROOT/'logs/rgbd_partial_tracking_20261017/plane_00/command.json').read_text())['env'];env=dict(os.environ,**base)
 env.update(OVERLAY_ROOT=str(RUN/'runtime_overlay'),ANCHOR_VISUAL_CODE=str(RUN/'code'),PYTHONPATH=str(RUN/'runtime_overlay')+':'+str(ROOT/'third_party/LIBERO-PRO')+':'+str(RUN/'code'),XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='.45',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 argv=[str(ROOT/'envs/rlinf-openpi/bin/python'),str(RUN/'code/scripts/recovery/skill_pipeline/shared_benchmark_policy.py'),'--config-name','pi0_libero','--checkpoint-dir',str(ROOT/'models/pi0_libero_openpi'),'--directory',str(RUN)]
 with (RUN/'policy_server.log').open('ab') as log:
  p=subprocess.Popen(argv,env=env,cwd=RUN/'runtime_overlay',stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 (RUN/'policy_launch.json').write_text(json.dumps(dict(pid=p.pid,argv=argv)))
with (RUN/'setup.log').open('ab') as log:
 p=subprocess.Popen([str(ROOT/'envs/rlinf-openpi/bin/python'),'-u',str(RUN/'setup_and_run.py')],cwd=RUN,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
(RUN/'setup_launch.json').write_text(json.dumps(dict(pid=p.pid)))
print('SETUP_STARTED',p.pid)
