"""Fit sensor-only geometry from synchronized saved RGB-D views.

Inputs are RGB-D captures and detector artifacts. Oracle comparison is a
separate command; neither simulator state nor object assets are accepted here.
"""
import argparse
import hashlib
import itertools
import json
from pathlib import Path
import sys
import numpy as np


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--snapshot',type=Path,required=True)
    ap.add_argument('--perception',type=Path,required=True)
    ap.add_argument('--language',required=True)
    ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.visual_language_prompts import parse_visual_pick_place_language,category_for_phrase
    from experiments.robot.libero.skill_pipeline.visual_observed_geometry import observed_points,fit_observed_cuboid,fit_observed_support,cuboid_geometry
    from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base
    task=parse_visual_pick_place_language(args.language)
    categories=dict(target=category_for_phrase(task.target_phrase),support=category_for_phrase(task.goal_phrase))
    args.out.mkdir(exist_ok=False,parents=True)
    roles=dict(target=[],support=[]); frames={}; reports={}; models={}; masks={}
    manifest={}
    identity_notes=[]
    for camera in ['agentview','robot0_eye_in_hand']:
        source=args.snapshot/camera;perception=args.perception/camera
        frame=load_observation(source);frames[camera]=frame
        for p in [source/'metadata.json',source/'rgbd.npz',perception/'detections.json',perception/'detections.npz']:
            manifest[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
        _,detections=load_detections(frame,perception)
        if camera!='agentview':
            first=frames['agentview']
            if (frame.episode_id!=first.episode_id or frame.env_step!=first.env_step
                    or abs(frame.timestamp_s-first.timestamp_s)>1e-6):
                raise ValueError('multi-view input is not synchronized')
        reports[camera]={}
        for role,category in categories.items():
            candidates=[d for d in detections if d.category==category]
            if len(candidates)!=1:
                reports[camera][role]=dict(status='missing' if not candidates else 'ambiguous',candidate_count=len(candidates))
                continue
            points,report=observed_points(frame,candidates[0].mask,world_from_base=infer_world_from_base(frame))
            masks[camera,role]=candidates[0].mask
            if len(points)<100:
                reports[camera][role]=dict(report,status='insufficient_depth');continue
            # Cross-view fusion requires measured overlap, not category alone.
            if roles[role]:
                from scipy.spatial import cKDTree
                distance=cKDTree(roles[role][0][1]).query(points,k=1)[0]
                overlap=float(np.mean(distance<.004))
                if overlap<.2:
                    reports[camera][role]=dict(report,status='cross_view_identity_unresolved',overlap=overlap)
                    identity_notes.append(f'{camera}:{role}:not_fused');continue
                report['cross_view_surface_overlap']=overlap
            roles[role].append((camera,points))
            reports[camera][role]=dict(report,status='observed')
            models[camera+'_'+role]=fit_observed_cuboid(points) if role=='target' else fit_observed_support(points)
            np.savez_compressed(args.out/(camera+'_'+role+'_points.npz'),points_world=points)
    if not roles['target'] or not roles['support']:
        raise ValueError('no usable target or support observation; inspect per-view detection artifacts')
    target=np.concatenate([p for _,p in roles['target']]);support=np.concatenate([p for _,p in roles['support']])
    models['fused_target']=fit_observed_cuboid(target)
    models['fused_support']=fit_observed_support(support)
    for key,model in models.items():(args.out/(key+'.json')).write_text(json.dumps(model,indent=2))
    if models['fused_target'].get('planning_allowed'):
        raw_geometry=cuboid_geometry(models['fused_target'])
        (args.out/'target_geometry.json').write_text(json.dumps(raw_geometry,indent=2))
        from experiments.robot.libero.tiptop_repro.scene_types import ObjectState,SceneState
        from experiments.robot.libero.tiptop_repro.geometry import estimate_object_geometry
        m=models['fused_target']
        obj=ObjectState('rgbd_cheese_obj_001',np.array(m['center_world_m']),
            np.array(m['quat_world_wxyz']),geometry=raw_geometry)
        scene=SceneState(np.zeros(3),np.array([1.,0.,0.,0.]),np.array([.04,-.04]))
        proxy=estimate_object_geometry(obj,scene)
        part=proxy.metadata['collision_parts'][0]
        np.testing.assert_allclose(part['local_pos'],[0,0,0],atol=1e-7)
        np.testing.assert_allclose(part['size'],m['collision_half_extents_m'],atol=1e-9)
        assert proxy.source=='rgbd_observed_cuboid'
        (args.out/'existing_geometry_adapter.json').write_text(json.dumps(dict(
            passed=True,geometry=proxy.to_dict(),full_motion_planning_attempted=False),indent=2))
    np.savez_compressed(args.out/'observed_points.npz',target_world=target,support_world=support)
    summary=dict(language=args.language,source='current_sensor_observations_only',views=reports,
        fused_views={role:[c for c,_ in views] for role,views in roles.items()},
        cross_view_notes=identity_notes,target_geometry_gate=models['fused_target']['planning_allowed'],
        support_geometry_gate=models['fused_support']['planning_allowed'],
        support_gate_reasons=models['fused_support']['reasons'],
        execution_attempted=False,initial_geometry_only=True,
        descriptor_status='cream cheese phrase passed to detector; identity not independently certified',
        simulator_geometry_used=False,environment_actions=0)
    (args.out/'summary.json').write_text(json.dumps(summary,indent=2))
    (args.out/'input_sha256.json').write_text(json.dumps(manifest,indent=2))
    render(args.out,frames,masks,target,support,models)
    print(json.dumps(summary),flush=True)


def render(out,frames,masks,target,support,models):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from PIL import Image,ImageDraw
    for camera,frame in frames.items():
        image=Image.fromarray(frame.rgb.copy());draw=ImageDraw.Draw(image)
        for role,color in [('target','lime'),('support','cyan')]:
            if (camera,role) not in masks:continue
            ys,xs=np.where(masks[camera,role]);draw.rectangle((int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())),outline=color,width=2)
        model=models['fused_target']
        if model.get('corners_world_m'):
            corners=np.array(model['corners_world_m'])
            t=np.linalg.inv(frame.T_world_camera);p=corners@t[:3,:3].T+t[:3,3]
            pix=p@frame.K.T;pix=pix[:,:2]/pix[:,2:]-0.5
            for i,j in itertools.combinations(range(8),2):
                if (i^j) in (1,2,4):draw.line([tuple(pix[i]),tuple(pix[j])],fill='red',width=2)
        image.save(out/(camera+'_geometry.png'))
    fig=plt.figure(figsize=(13,5))
    ax=fig.add_subplot(121,projection='3d')
    p=target[::max(1,len(target)//3500)]
    ax.scatter(*p.T,s=1,c=p[:,2],cmap='viridis')
    m=models['fused_target']
    if m.get('corners_world_m'):
        c=np.array(m['corners_world_m'])
        for i,j in itertools.combinations(range(8),2):
            if (i^j) in (1,2,4):ax.plot(*c[[i,j]].T,color='red',linewidth=1)
    ax.set_title('Target: measured surfaces + fitted cuboid')
    ax.set_box_aspect(np.maximum(np.ptp(p,axis=0),.01))
    ax=fig.add_subplot(122,projection='3d')
    p=support[::max(1,len(support)//6500)]
    ax.scatter(*p.T,s=1,c=p[:,2],cmap='viridis')
    for plane in models['fused_support']['plane_evidence'][:4]:
        c=np.array(plane['centroid']);n=np.array(plane['normal'])
        ax.quiver(*c,*n,length=.04,color='red')
    ax.set_title('Rack: observed surfaces; red = fitted normals')
    ax.set_box_aspect(np.maximum(np.ptp(p,axis=0),.01))
    for ax in fig.axes:
        ax.set_xlabel('world X (m)');ax.set_ylabel('world Y (m)');ax.set_zlabel('world Z (m)')
    fig.tight_layout();fig.savefig(out/'pointcloud_geometry.png',dpi=180);plt.close(fig)


if __name__=='__main__':main()
