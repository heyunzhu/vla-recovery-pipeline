"""Separate wider translation search from rotation-aware assisted RGB-D matching."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image, ImageDraw
from probe_static_wrist_gripper import pose, read_stl, raster_depth


def bank_match(patches, image, center, search=48, radius=8):
    x,y=center
    lx,hx=max(radius,x-search),min(image.shape[1]-radius-1,x+search)
    ly,hy=max(radius,y-search),min(image.shape[0]-radius-1,y+search)
    windows=np.lib.stride_tricks.sliding_window_view(image[ly-radius:hy+radius+1,lx-radius:hx+radius+1],(17,17))
    mean=windows.mean(axis=(-2,-1));variance=np.sum(windows*windows,axis=(-2,-1))-mean*mean*289
    best=np.full(mean.shape,-1.);angle_map=np.zeros(mean.shape)
    for angle,patch in patches:
        t=patch-patch.mean();denom=np.sqrt(np.maximum(variance,0)*np.sum(t*t))
        cross=np.einsum('ijab,ab->ij',windows,t,optimize=False)
        scores=np.divide(cross,denom,out=np.full(mean.shape,-1.),where=denom>1e-8)
        update=scores>best;best[update]=scores[update];angle_map[update]=angle
    yy,xx=np.unravel_index(np.argmax(best),best.shape);peak=float(best[yy,xx]);other=best.copy();other[max(0,yy-4):yy+5,max(0,xx-4):xx+5]=-1
    return (int(xx+lx),int(yy+ly)),peak,peak-float(other.max()),float(angle_map[yy,xx])


def patch_bank(gray, xy, angles):
    x,y=xy;pad=14
    crop=gray[y-pad:y+pad+1,x-pad:x+pad+1]
    if crop.shape!=(29,29):raise ValueError('patch bank needs image margin')
    image=Image.fromarray(crop.astype(np.float32),'F')
    return [(angle,np.asarray(image.rotate(angle,resample=Image.Resampling.BILINEAR).crop((6,6,23,23)),float)) for angle in angles]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('dataset','reference-report','model-dir','out-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();repo=Path(__file__).resolve().parents[3];sys.path.insert(0,str(repo))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation,unproject_world
    from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
    from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
    from experiments.robot.libero.skill_pipeline.visual_rigid_motion import robust_motion
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    ref=json.loads(args.reference_report.read_text())
    for path,h in dict(ref['input_sha256'],**ref['source_sha256']).items():
        if sha(Path(path))!=h:raise ValueError('reference inputs/source changed: '+path)
    anchors=[t['source_xy'] for t in next(r for r in ref['results'] if r['region']=='front_bowl_draft' and r['label']=='after_observation')['tracks']]
    manifest=json.loads((args.model_dir/'manifest.json').read_text())
    for name,h in manifest['source_sha256'].items():
        if sha(args.model_dir/name)!=h:raise ValueError('static model changed')
    arm=ET.parse(args.model_dir/'models/assets/robots/panda/robot.xml');grip=ET.parse(args.model_dir/'models/assets/grippers/panda_gripper.xml')
    hc=pose(arm.find('.//body[@name="right_hand"]/camera[@name="eye_in_hand"]')) @ np.diag([1,-1,-1,1])
    meshes={e.get('name'):read_stl(args.model_dir/'models/assets/grippers'/e.get('file')) for e in grip.findall('./asset/mesh')}
    frames={};coords={};grays={};robots={};hands={};inputs={str(args.reference_report):sha(args.reference_report)}
    for label in ('after_close','observation_return','after_observation'):
        f=load_observation(args.dataset/label/'robot0_eye_in_hand');a=load_observation(args.dataset/label/'agentview');validate_synchronized_views(f,a)
        if f.episode_id!=ref['episode_id']:raise ValueError('reference episode mismatch')
        frames[label]=f;grays[label]=np.asarray(Image.fromarray(f.rgb).convert('L'),float)/255
        coords[label]=np.full((*f.depth_m.shape,3),np.nan);coords[label][f.depth_valid]=unproject_world(f);hands[label]=f.T_world_camera @ np.linalg.inv(hc)
        qmap=dict(zip(('finger_joint1','finger_joint2'),f.robot_state['robot0_gripper_qpos']));tri=[]
        def visit(body,parent):
            t=parent @ pose(body)
            for j in body.findall('./joint'):
                if j.get('type')!='slide' or j.get('name') not in qmap:raise ValueError('unsupported joint')
                jt=np.eye(4);jt[:3,3]=np.array([float(v) for v in j.get('axis').split()])*qmap[j.get('name')];t=t @ jt
            for g in body.findall('./geom'):
                if g.get('group')=='1' and g.get('type')=='mesh':
                    gt=np.linalg.inv(hc) @ t @ pose(g);tri.append(meshes[g.get('mesh')] @ gt[:3,:3].T+gt[:3,3])
            for child in body.findall('./body'):visit(child,t)
        visit(grip.find('./worldbody/body'),np.eye(4));d,_=raster_depth(np.concatenate(tri),f.K,f.depth_m.shape);robots[label]=np.isfinite(d)&f.depth_valid&(np.abs(f.depth_m-d)<=.005)
        for camera in ('agentview','robot0_eye_in_hand'):
            for name in ('metadata.json','rgbd.npz'):
                path=args.dataset/label/camera/name;inputs[str(path)]=sha(path)
    if rgb_sha256(frames['after_close'])!=ref['source_rgb_sha256']:raise ValueError('source RGB mismatch')
    args.out_dir.mkdir(exist_ok=False);results=[]
    for method,angles in [('translation48',[0]),('rotation48',list(range(-40,41,5)))]:
        for label in ('observation_return','after_observation'):
            tracks=[]
            for xy in anchors:
                target,score,margin,angle=bank_match(patch_bank(grays['after_close'],xy,angles),grays[label],xy)
                back,back_score,_,_=bank_match(patch_bank(grays[label],target,angles),grays['after_close'],target)
                x,y=xy;tx,ty=target;fb=float(np.linalg.norm(np.asarray(back)-xy))
                accepted=bool(score>=.90 and margin>=.015 and back_score>=.90 and fb<=2 and frames['after_close'].depth_valid[y,x] and frames[label].depth_valid[ty,tx] and not robots['after_close'][y,x] and not robots[label][ty,tx])
                row=dict(source_xy=xy,target_xy=list(target),ncc=score,margin=margin,patch_rotation_deg=angle,reverse_ncc=back_score,forward_backward_px=fb,accepted=accepted)
                if accepted:row.update(source_world_m=coords['after_close'][y,x].tolist(),target_world_m=coords[label][ty,tx].tolist())
                tracks.append(row)
            pairs=[t for t in tracks if t['accepted']];motion=dict(accepted=False,reason='fewer_than_six_correspondences');relative=motion.copy()
            if len(pairs)>=6:
                s=np.array([r['source_world_m'] for r in pairs]);t=np.array([r['target_world_m'] for r in pairs]);motion=robust_motion(s,t)
                sh=(s-hands['after_close'][:3,3]) @ hands['after_close'][:3,:3];th=(t-hands[label][:3,3]) @ hands[label][:3,:3];relative=robust_motion(sh,th)
            results.append(dict(method=method,label=label,source_anchor_count=len(anchors),matched_count=len(pairs),tracks=tracks,world_motion=motion,hand_relative_motion=relative))
            im=Image.fromarray(frames[label].rgb);draw=ImageDraw.Draw(im)
            for r in tracks:
                x,y=r['target_xy'];draw.ellipse((x-3,y-3,x+3,y+3),outline='lime' if r['accepted'] else 'red',width=2)
            im.save(args.out_dir/(method+'_'+label+'.png'))
            print(json.dumps(dict(method=method,label=label,matched_count=len(pairs),world_motion=motion,hand_relative_motion=relative)),flush=True)
    report=dict(scope='offline_assisted_rotation_motion_diagnostic',episode_id=ref['episode_id'],results=results,
        settings=dict(search_radius_px=48,rotation_bank_deg=list(range(-40,41,5)),ncc_min=.90,peak_margin_min=.015,reverse_ncc_min=.90,forward_backward_max_px=2,rigid_residual_m=.003),
        input_sha256=inputs,source_sha256={str(Path(__file__)):sha(Path(__file__)),str(repo/'experiments/robot/libero/skill_pipeline/visual_rigid_motion.py'):sha(repo/'experiments/robot/libero/skill_pipeline/visual_rigid_motion.py')},
        original_frozen_checker_replaced=False,human_reviewed=False,blind_evaluation=False,holding_verified=False,identity_verified=False,environment_actions=0,
        limitations=['local rotated patches approximate perspective changes','repeated texture can yield false correspondences','rigid fit residual alone does not verify semantic identity or physical grasp','visual gripper meshes only; no whole-arm segmentation'])
    (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
