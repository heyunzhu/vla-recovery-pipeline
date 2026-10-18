
from pathlib import Path
import json,os,subprocess,time,traceback
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo');run=root/'logs/rgbd_core60_20261017'
try:
 for name in ['policy_launch.json','batch_launch.json']:
  old=json.loads((run/name).read_text())
  assert not Path('/proc/'+str(old['pid'])).exists(),'recorded process PID exists, inspect before resume'
 stamp=str(time.time_ns());archive=run/'resumes'/stamp;archive.mkdir(parents=True)
 for name in ['policy_launch.json','batch_launch.json','policy_ready.json','policy_endpoint.json','policy_server.log']:
  p=run/name
  if p.exists():p.rename(archive/name)
 base=json.loads((root/'logs/rgbd_partial_tracking_20261017/plane_00/command.json').read_text())['env']
 env=dict(os.environ,**base)
 env.update(OVERLAY_ROOT=str(run/'runtime_overlay'),ANCHOR_VISUAL_CODE=str(run/'code'),PYTHONPATH=str(run/'runtime_overlay')+':'+str(root/'third_party/LIBERO-PRO')+':'+str(run/'code'),XLA_PYTHON_CLIENT_PREALLOCATE='false',XLA_PYTHON_CLIENT_MEM_FRACTION='0.45',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
 argv=json.loads((archive/'policy_launch.json').read_text())['argv']
 with (run/'policy_server.log').open('wb') as log:p=subprocess.Popen(argv,env=env,cwd=run/'runtime_overlay',stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 (run/'policy_launch.json').write_text(json.dumps(dict(pid=p.pid,argv=argv),indent=2))
 for _ in range(300):
  if p.poll() is not None:raise RuntimeError('policy server exited: '+str(p.returncode))
  if (run/'policy_ready.json').exists():break
  time.sleep(1)
 else:raise TimeoutError('policy server not ready after 300s')
 argv=json.loads((archive/'batch_launch.json').read_text())['argv']
 with (run/'scheduler.log').open('ab') as log:
  log.write(('\nRESUME_AFTER_INSTANCE_RESTART '+stamp+'\n').encode());log.flush()
  scheduler=subprocess.Popen(argv,cwd=run,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
 (run/'batch_launch.json').write_text(json.dumps(dict(pid=scheduler.pid,argv=argv),indent=2))
 (run/'resume_verified.json').write_text(json.dumps(dict(resume_unix=time.time(),policy_pid=p.pid,scheduler_pid=scheduler.pid,preserved_completed=70,configuration_changed=False,archive=str(archive)),indent=2))
 print('RESUMED',scheduler.pid,flush=True)
except Exception:
 (run/'resume_error.txt').write_text(traceback.format_exc());raise
