from pathlib import Path
import json,sys,hashlib
import numpy as np
from libero.libero.envs import OffScreenRenderEnv

root=Path('/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo')
source=root/'logs/rgbd_release_candidate_20261017_v2/plane_01'
out=root/'logs/rgbd_rack_contact_replay_20261017'
command=json.loads((source/'command.json').read_text());argv=command['argv']
fixture=Path(argv[argv.index('--fixture')+1]);bddl=argv[argv.index('--bddl')+1]
meta=json.loads((fixture/'config.json').read_text())
env=OffScreenRenderEnv(bddl_file_name=bddl,camera_heights=640,camera_widths=640,camera_depths=True)
env.seed(meta.get('episode_seed',1));env.reset()
initial=np.load(fixture/'initial_physics_state.npy');obs=env.set_init_state(initial)
assert np.array_equal(initial,env.sim.get_state().flatten())
env.env.robots[0].gripper.current_action=np.array([1.,-1.])
events=json.loads((source/'execution_events.json').read_text())
rows=[]
for index,event in enumerate(events):
 obs=env.step(np.asarray(event['action']))[0]
 contacts=[]
 for i in range(env.sim.data.ncon):
  c=env.sim.data.contact[i]
  g1=int(c.geom1);g2=int(c.geom2)
  contacts.append(dict(geom1=env.sim.model.geom_id2name(g1),geom2=env.sim.model.geom_id2name(g2),
   body1=env.sim.model.body_id2name(int(env.sim.model.geom_bodyid[g1])),
   body2=env.sim.model.body_id2name(int(env.sim.model.geom_bodyid[g2])),
   dist_m=float(c.dist),position=np.asarray(c.pos).tolist()))
 row=dict(action_index=index,env_step=meta['control_steps']+index+1,label=event.get('label'),
  ee_pos=obs['robot0_eef_pos'].tolist(),gripper_qpos=obs['robot0_gripper_qpos'].tolist(),contacts=contacts)
 rows.append(row)
 if index%20==0:print(index,row['ee_pos'],flush=True)
sys.path.insert(0,str(source/'capture_support'))
from anchor_sensor.libero_rgbd_sensor import capture_libero_rgbd
from anchor_sensor.rgbd_observation import save_observation
frame=capture_libero_rgbd(env,obs,episode_id=meta['episode_id'],env_step=rows[-1]['env_step'],camera_id='agentview')
save_observation(frame,out/'final/agentview')
original=json.loads((source/'snapshots/recovery01/final/agentview/metadata.json').read_text())
new=json.loads((out/'final/agentview/metadata.json').read_text())
comparison=dict(original_robot=original['robot_state'],replayed_robot=new['robot_state'],
 original_env_step=original['env_step'],replayed_env_step=new['env_step'])
np.save(out/'final_physics_state.npy',env.sim.get_state().flatten())
(out/'contacts.json').write_text(json.dumps(rows,indent=2))
(out/'replay_comparison.json').write_text(json.dumps(comparison,indent=2))
(out/'finished.json').write_text(json.dumps(dict(actions=len(rows),source=str(source),
 action_sha256=hashlib.sha256((source/'execution_events.json').read_bytes()).hexdigest(),
 use='Offline diagnosis only: simulator contacts are not provided to recovery'),indent=2))
env.close();print('CONTACT_REPLAY_FINISHED',flush=True)
