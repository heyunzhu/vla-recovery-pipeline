"""Independent fixed-reference matching to diagnose chained tracking drift."""
import argparse,json,hashlib,sys
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image,ImageDraw
from probe_grasp_texture_motion import match_patch
from probe_static_wrist_gripper import pose,read_stl,raster_depth


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('dataset','reference-dataset','reference-report','model-dir','out-dir'):p.add_argument('--'+n,required=True,type=Path)
    a=p.parse_args();repo=Path(__file__).resolve().parents[3];sys.path.insert(0,str(repo))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation,unproject_world
    from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
    from experiments.robot.libero.skill_pipeline.visual_rigid_motion import robust_motion
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    ref=json.loads(a.reference_report.read_text())
    for name,h in dict(ref['input_sha256'],**ref['source_sha256']).items():
        if sha(Path(name))!=h:raise ValueError('reference changed')
    manifest=json.loads((a.model_dir/'manifest.json').read_text())
    for name,h in manifest['source_sha256'].items():
        if sha(a.model_dir/name)!=h:raise ValueError('static model changed')
    arm=ET.parse(a.model_dir/'models/assets/robots/panda/robot.xml');grip=ET.parse(a.model_dir/'models/assets/grippers/panda_gripper.xml');hc=pose(arm.find('.//body[@name="right_hand"]/camera[@name="eye_in_hand"]')) @ np.diag([1,-1,-1,1])
    meshes={e.get('name'):read_stl(a.model_dir/'models/assets/grippers'/e.get('file')) for e in grip.findall('./asset/mesh')}
    def robot_mask(f):
        qmap=dict(zip(('finger_joint1','finger_joint2'),f.robot_state['robot0_gripper_qpos']));tri=[]
        def visit(body,parent):
            t=parent @ pose(body)
            for j in body.findall('./joint'):
                if j.get('type')!='slide' or j.get('name') not in qmap:raise ValueError('unsupported joint')
                jt=np.eye(4);jt[:3,3]=np.array([float(x) for x in j.get('axis').split()])*qmap[j.get('name')];t=t @ jt
            for g in body.findall('./geom'):
                if g.get('group')=='1' and g.get('type')=='mesh':
                    gt=np.linalg.inv(hc) @ t @ pose(g);tri.append(meshes[g.get('mesh')] @ gt[:3,:3].T+gt[:3,3])
            for child in body.findall('./body'):visit(child,t)
        visit(grip.find('./worldbody/body'),np.eye(4));d,_=raster_depth(np.concatenate(tri),f.K,f.depth_m.shape)
        return np.isfinite(d)&f.depth_valid&(np.abs(f.depth_m-d)<=.005)
    a.out_dir.mkdir(exist_ok=False);source=load_observation(a.dataset/'observation_return/robot0_eye_in_hand');old=load_observation(a.reference_dataset/'observation_return/robot0_eye_in_hand')
    for key in ('rgb','depth_m','depth_valid','K','T_world_camera'):
        if not np.array_equal(getattr(source,key),getattr(old,key)):raise ValueError('source frame differs')
    source_hand=source.T_world_camera @ np.linalg.inv(hc);source_points=np.full((*source.depth_m.shape,3),np.nan);source_points[source.depth_valid]=unproject_world(source);robot=robot_mask(source)
    anchors=[t['target_xy'] for t in next(r for r in ref['results'] if r['region']=='front_bowl_draft' and r['label']=='observation_return')['tracks'] if t['accepted']]
    initial={i:source_points[y,x] for i,(x,y) in enumerate(anchors) if source.depth_valid[y,x] and not robot[y,x]};active={i:tuple(anchors[i]) for i in initial};previous=np.asarray(Image.fromarray(source.rgb).convert('L'),float)/255;source_gray=previous.copy()
    inputs={str(a.reference_report):sha(a.reference_report)};rows=[]
    for label in ['observation_return']+['dense_hold'+str(n).zfill(2) for n in range(1,41)]:
        f=load_observation(a.dataset/label/'robot0_eye_in_hand');v=load_observation(a.dataset/label/'agentview');validate_synchronized_views(f,v)
        if f.episode_id!=source.episode_id:raise ValueError('episode mismatch')
        for camera in ('agentview','robot0_eye_in_hand'):
            for name in ('metadata.json','rgbd.npz'):
                path=a.dataset/label/camera/name;inputs[str(path)]=sha(path)
        if label=='observation_return':continue
        gray=np.asarray(Image.fromarray(f.rgb).convert('L'),float)/255;robot=robot_mask(f);coords=np.full((*f.depth_m.shape,3),np.nan);coords[f.depth_valid]=unproject_world(f);hand=f.T_world_camera @ np.linalg.inv(hc);tracks=[];candidates={}
        for i,(x,y) in {i:tuple(anchors[i]) for i in initial}.items():
            template=source_gray[y-8:y+9,x-8:x+9];(tx,ty),score,margin=match_patch(template,gray,(x,y),search=28)
            back,back_score,_=match_patch(gray[ty-8:ty+9,tx-8:tx+9],source_gray,(tx,ty),search=28);fb=float(np.linalg.norm(np.asarray(back)-[x,y]))
            ok=bool(score>=.90 and margin>=.015 and back_score>=.90 and fb<=2 and f.depth_valid[ty,tx] and not robot[ty,tx])
            tracks.append(dict(anchor_id=i,previous_xy=[x,y],target_xy=[tx,ty],ncc=score,margin=margin,reverse_ncc=back_score,forward_backward_px=fb,accepted=ok))
            if ok:candidates[i]=(tx,ty)
        ids=list(candidates);world=dict(accepted=False,reason='fewer_than_six_correspondences');relative=world.copy()
        if len(ids)>=6:
            s=np.array([initial[i] for i in ids]);t=np.array([coords[candidates[i][1],candidates[i][0]] for i in ids]);world=robust_motion(s,t)
            relative=robust_motion((s-source_hand[:3,3]) @ source_hand[:3,:3],(t-hand[:3,3]) @ hand[:3,:3])
            if world['accepted']:
                consensus={ids[j] for j in world['inlier_indices']};candidates={i:xy for i,xy in candidates.items() if i in consensus}
        active=candidates;previous=gray
        rows.append(dict(label=label,env_step=f.env_step,time_since_return_s=f.timestamp_s-source.timestamp_s,active_tracks=len(active),tracks=tracks,world_motion=world,hand_relative_motion=relative))
        im=Image.fromarray(f.rgb);draw=ImageDraw.Draw(im)
        for r in tracks:
            x,y=r['target_xy'];draw.ellipse((x-3,y-3,x+3,y+3),outline='lime' if r['anchor_id'] in active else 'red',width=2)
        im.save(a.out_dir/(label+'.png'))
        print(json.dumps(dict(label=label,active=len(active),world_rotation_deg=world.get('rotation_deg'),relative_rotation_deg=relative.get('rotation_deg'),relative_centroid_displacement_m=relative.get('centroid_displacement_m'),accepted=relative['accepted'])),flush=True)
    sources=[Path(__file__),repo/'experiments/robot/libero/skill_pipeline/visual_rigid_motion.py',repo/'scripts/recovery/skill_pipeline/probe_grasp_texture_motion.py']
    report=dict(scope='fixed_reference_assisted_local_rigid_motion',episode_id=source.episode_id,source_label='observation_return',source_anchors_xy=anchors,settings=dict(search_radius_px=28,ncc_min=.90,peak_margin_min=.015,forward_backward_max_px=2,rigid_residual_m=.003,independent_source_match_per_frame=True),results=rows,input_sha256=inputs,source_sha256={str(p):sha(p) for p in sources},human_reviewed=False,identity_verified=False,holding_verified=False,environment_actions=0,limitations=['independent matches can switch repeated texture instances','initial texture anchors are assistant draft correspondences','rigid consensus is not physical contact verification','no background/robot negative control benchmark'])
    (a.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
