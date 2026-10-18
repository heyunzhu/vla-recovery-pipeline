from pathlib import Path
import json,subprocess,shutil,hashlib
import numpy as np
from PIL import Image,ImageFont,ImageDraw
root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
run=root/'logs/rgbd_framewise_20261016_replay03'
assets=run/'report_assets';assets.mkdir(exist_ok=True)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',18)
small=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',15)
summary={}
for case in ['bowl','plate']:
 if not (run/(case+'_finished.json')).exists():continue
 c=run/case
 result_path=c/'replay_result.json';result_path=result_path if result_path.exists() else c/'failure_result.json'
 result=json.loads(result_path.read_text())
 info={k:v for k,v in result.items() if k!='attempts'}
 info['attempts']=[{k:a.get(k) for k in ['num_env_steps','selected_skeleton','executed_steps','feasible']} for a in result.get('attempts',[])]
 records=[json.loads(p.read_text()) for p in sorted((c/'framewise_tracking').glob('step*.json'))]
 steps=[r['env_step'] for r in records]
 info.update(observed_frames=len(records),first_observed_step=min(steps) if steps else None,last_observed_step=max(steps) if steps else None,
  contiguous_observations=bool(steps and steps==list(range(min(steps),max(steps)+1))),
  resident_requests=len(list((c/'resident_vision').glob('step*/result.json'))))
 if len(records)>1:
  warm=records[1:]
  info['warm_median_ms']={k:float(np.median([r['detection'][k] for r in warm])) for k in ['dino_ms','vision_ms']}
  info['warm_median_ms']['registration_and_vision_ms']=float(np.median([r['registration_and_vision_ms'] for r in warm]))
  info['warm_p95_registration_and_vision_ms']=float(np.quantile([r['registration_and_vision_ms'] for r in warm],.95))
 info['first_frame_ms']=records[0]['registration_and_vision_ms'] if records else None
 phases=c/'snapshots/recovery01';end='final' if (phases/'final').exists() else 'failure'
 final_meta=json.loads((phases/end/'agentview/metadata.json').read_text())
 info['final_finger_qpos_m']=final_meta['robot_state']['robot0_gripper_qpos']
 with np.load(phases/end/'agentview/rgbd.npz') as d:Image.fromarray(d['rgb']).save(assets/(case+'_final.png'))
 # Repeated scene reads use a cache; each execution step contributes one RGB frame.
 images={}
 for phase in ['entry','pre_solver_attempt01']:
  meta=json.loads((phases/phase/'agentview/metadata.json').read_text())
  with np.load(phases/phase/'agentview/rgbd.npz') as d:images[meta['env_step']]=Image.fromarray(d['rgb'])
 for p in sorted((c/'resident_vision').glob('step*/rgb.png')):
  images[int(p.parent.name[4:])]=Image.open(p).convert('RGB')
 ordered=sorted(images.items())
 video=assets/(case+'_framewise.mp4')
 if not video.exists():
  command=[shutil.which('ffmpeg'),'-y','-loglevel','error','-f','rawvideo','-pix_fmt','rgb24','-s','640x688','-r','20','-i','-','-an','-c:v','libx264','-threads','2','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(video)]
  process=subprocess.Popen(command,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
  for i,(step,img) in enumerate(ordered):
   canvas=Image.new('RGB',(640,688),'#171b23');canvas.paste(img,(0,48));draw=ImageDraw.Draw(canvas)
   draw.text((8,4),f'{case.upper()} | step {step} | simulation {(step-ordered[0][0])/20:.2f}s',font=font,fill='white')
   draw.text((8,27),'Per-step DINO+SAM | playback omits inference waiting',font=small,fill='white')
   repetitions=ordered[i+1][0]-step if i+1<len(ordered) else 20
   for _ in range(repetitions):process.stdin.write(canvas.tobytes())
  process.stdin.close();error=process.stderr.read();assert process.wait()==0,error
 info['video']=dict(path=str(video),sha256=hashlib.sha256(video.read_bytes()).hexdigest(),
  sensor_frames=len(ordered),encoding_fps=20,simulation_time_playback=True,
  initial_entry_lift_sampled_every_5_steps=True,execution_sensor_frames_every_step=True,final_hold_seconds=1)
 summary[case]=info
(run/'run_summary.json').write_text(json.dumps(summary,indent=2))
print(json.dumps(summary))
