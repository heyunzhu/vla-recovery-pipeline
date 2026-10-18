"""Current-frame DINO/SAM masks and unconstrained SE(3) RGB-D registration.

Rigid observed shape is retained; no cylinder fit, fixed-radius residual or
world-vertical axis is used to accept a new pose. Hidden shape remains unknown.
"""
import copy
import json
import os
from pathlib import Path
import time

import numpy as np
from scipy.spatial import cKDTree
from scipy.spatial.transform import Rotation

from .rgbd_observation import unproject_world
from .resident_vision import JSONLineProcess


def transform(points, pose):
    return np.asarray(points)@pose[:3,:3].T+pose[:3,3]


def compact_cloud(points, voxel=.003):
    points=np.asarray(points,float)
    points=points[np.isfinite(points).all(axis=1)]
    _,ids=np.unique(np.floor(points/voxel).astype(np.int64),axis=0,return_index=True)
    points=points[np.sort(ids)]
    if len(points)>2200:points=points[np.linspace(0,len(points)-1,2200).astype(int)]
    return points


def register_cloud(reference, observed, seed):
    """Robust point-to-plane ICP with free rotation and translation."""
    source=compact_cloud(reference);target=compact_cloud(observed)
    if min(len(source),len(target))<40:raise ValueError('insufficient measured target points')
    tree=cKDTree(target)
    neighbors=target[tree.query(target,k=min(16,len(target)))[1]]
    centered=neighbors-neighbors.mean(axis=1,keepdims=True)
    covariance=np.einsum('nki,nkj->nij',centered,centered)
    normals=np.linalg.eigh(covariance)[1][:,:,0]
    pose=np.array(seed,float,copy=True)
    for _ in range(30):
        current=transform(source,pose)
        distances,ids=tree.query(current)
        limit=min(.035,max(.006,float(np.quantile(distances,.85))))
        keep=distances<=limit
        if keep.sum()<35:break
        p=current[keep];q=target[ids[keep]];n=normals[ids[keep]]
        origin=p.mean(axis=0)
        a=np.column_stack((np.cross(p-origin,n),n))
        b=np.sum(n*(q-p),axis=1)
        weight=1/np.maximum(1,np.abs(b)/.004)
        aw=a*np.sqrt(weight[:,None]);bw=b*np.sqrt(weight)
        delta=np.linalg.lstsq(np.vstack((aw,np.eye(6)*.02)),np.r_[bw,np.zeros(6)],rcond=None)[0]
        angle=np.linalg.norm(delta[:3])
        if angle>.15:delta[:3]*=.15/angle
        distance=np.linalg.norm(delta[3:])
        if distance>.02:delta[3:]*=.02/distance
        r=Rotation.from_rotvec(delta[:3]).as_matrix()
        update=np.eye(4);update[:3,:3]=r;update[:3,3]=origin-r@origin+delta[3:]
        pose=update@pose
        if np.linalg.norm(delta)<1e-5:break
    moved=transform(source,pose)
    distances=tree.query(moved)[0]
    reverse=cKDTree(moved).query(target)[0]
    report=dict(reference_points=len(source),observed_points=len(target),
        median_distance_m=float(np.median(distances)),q90_distance_m=float(np.quantile(distances,.9)),
        observed_overlap_fraction=float(np.mean(reverse<.012)),
        reference_overlap_fraction=float(np.mean(distances<.012)))
    report['accepted']=bool(report['median_distance_m']<.006 and
        report['reference_overlap_fraction']>.55 and report['observed_overlap_fraction']>.55)
    return pose,report


def hand_pose(frame):
    pose=np.eye(4)
    pose[:3,:3]=Rotation.from_quat(frame.robot_state['robot0_eef_quat']).as_matrix()
    pose[:3,3]=frame.robot_state['robot0_eef_pos']
    return pose


def visible_registration_quality(reference,observed,pose,frame,seed):
    """Score measured surfaces without treating depth-occluded points as errors.

    Both current-to-reference distances and visible reference coverage must
    agree. A nearby SE(3) seed bounds otherwise unobservable partial-view motion.
    """
    moved=transform(reference,pose);camera=transform(moved,np.linalg.inv(frame.T_world_camera))
    projected=camera@np.asarray(frame.K).T
    uv=np.floor(projected[:,:2]/np.maximum(projected[:,2:],1e-9)).astype(int)
    height,width=frame.depth_m.shape
    inside=(camera[:,2]>0)&(uv[:,0]>=0)&(uv[:,0]<width)&(uv[:,1]>=0)&(uv[:,1]<height)
    ids=np.flatnonzero(inside)
    ids=ids[frame.depth_valid[uv[ids,1],uv[ids,0]]]
    visible=ids[camera[ids,2]<=frame.depth_m[uv[ids,1],uv[ids,0]]+.004]
    distances=cKDTree(observed).query(moved)[0]
    reverse=cKDTree(moved).query(observed)[0]
    center=np.mean(reference,axis=0,keepdims=True)
    shift=float(np.linalg.norm(transform(center,pose)-transform(center,seed)))
    angle=float(Rotation.from_matrix(seed[:3,:3].T@pose[:3,:3]).magnitude())
    q=dict(visible_reference_points=len(visible),unscored_reference_points=len(reference)-len(visible),
           visible_reference_median_m=float(np.median(distances[visible])) if len(visible) else None,
           visible_reference_overlap=float(np.mean(distances[visible]<.012)) if len(visible) else 0.,
           observed_median_m=float(np.median(reverse)),observed_q90_m=float(np.quantile(reverse,.9)),
           partial_pose_center_shift_m=shift,partial_pose_angle_rad=angle)
    q['accepted']=bool(len(visible)>=max(40,.2*len(reference)) and len(visible)<=.8*len(reference)
        and q['visible_reference_median_m']<.006 and q['visible_reference_overlap']>.8
        and q['observed_median_m']<.004 and q['observed_q90_m']<.010
        and shift<.020 and angle<np.deg2rad(15))
    return q


class ResidentSegmentation:
    def __init__(self, config, work_dir):
        self.work=Path(work_dir);self.work.mkdir(parents=True,exist_ok=False)
        path=self.work/'config.json';path.write_text(json.dumps(config,indent=2))
        env=dict(os.environ,DINO_RESIDENT_WORKER='1',DINO_INFERENCE_WORKDIR=str(self.work/'dino'))
        env['PYTHONPATH']=os.environ['ANCHOR_SEGMENTATION_PYTHONPATH']
        self.worker=JSONLineProcess([os.environ['ANCHOR_SEGMENTATION_PYTHON'],'-m',
            'scripts.recovery.skill_pipeline.resident_rgbd_segmentation_worker','--config',str(path)],
            env=env,log_path=self.work/'segmentation.log',cwd=os.environ['ANCHOR_VISUAL_CODE'])

    def __call__(self,frame):
        from PIL import Image
        directory=self.work/f'step{frame.env_step:05d}'
        if frame.camera_id!='agentview':
            if frame.camera_id!='robot0_eye_in_hand':raise ValueError('unsupported resident camera')
            directory=self.work/frame.camera_id/directory.name
            directory.parent.mkdir(exist_ok=True)
        directory.mkdir(exist_ok=False)
        Image.fromarray(frame.rgb).save(directory/'rgb.png')
        reply=self.worker.request(dict(rgb=str(directory/'rgb.png'),output=str(directory/'masks.npz')))
        (directory/'result.json').write_text(json.dumps(reply,indent=2))
        return np.load(directory/'masks.npz')['masks'],reply

    def close(self):self.worker.close()


class FramewiseRGBDTracker:
    def __init__(self,frame,mask,model,segmenter,*,category='bottle',output_dir=None,
                 max_missing_steps=0,max_missing_seconds=.5,max_gap_translation_m=.04,
                 fallback_frame_provider=None,occlusion_aware=False):
        if max_missing_steps<0 or max_missing_seconds<=0 or max_gap_translation_m<=0:
            raise ValueError('invalid short-occlusion limits')
        self.initial_model=copy.deepcopy(model)
        self.reference=self.cloud(frame,mask)
        self.pose=np.eye(4)
        self.generic=model.get('source')=='rgbd_observed_cuboid'
        self.initial_bottom=(np.asarray(model['center_world_m']) if self.generic else
            np.r_[model['axis_xy_world_m'],model['bottom_z_world_m']])
        self.last_hand=hand_pose(frame)
        self.last_step=frame.env_step
        self.last_observed_step=frame.env_step
        self.last_observed_time=getattr(frame,'timestamp_s',None)
        self.last_observed_hand=self.last_hand.copy()
        self.last_observed_pose=self.pose.copy()
        self.last_observed_open=np.mean(np.abs(frame.robot_state['robot0_gripper_qpos']))>=.035
        self.max_missing_steps=max_missing_steps;self.max_missing_seconds=max_missing_seconds
        self.max_gap_translation_m=max_gap_translation_m
        self.fallback_frame_provider=fallback_frame_provider
        self.occlusion_aware=occlusion_aware
        self.segmenter=segmenter;self.category=category
        self.model=copy.deepcopy(model);self.report={}
        self.output=Path(output_dir) if output_dir else None
        if self.output:self.output.mkdir(exist_ok=False)

    def model_at_pose(self,pose,*,source,observed,cloud=None):
        model=copy.deepcopy(self.initial_model)
        bottom=transform(self.initial_bottom[None],pose)[0]
        model.update(T_world_from_initial=pose.tolist(),pose_source=source,
            radius_fit_constraint=False,upright_constraint=False,tracking_observed=observed)
        model.pop('observed_aabb_world_m',None)
        if cloud is not None:model['observed_aabb_world_m']=[cloud.min(0).tolist(),cloud.max(0).tolist()]
        if self.generic:
            rotation=pose[:3,:3]@np.asarray(self.initial_model['rotation_world_from_object'])
            q=Rotation.from_matrix(rotation).as_quat()
            model.update(center_world_m=bottom.tolist(),rotation_world_from_object=rotation.tolist(),
                quat_world_wxyz=np.r_[q[3],q[:3]].tolist(),
                corners_world_m=transform(np.asarray(self.initial_model['corners_world_m']),pose).tolist())
        else:
            model.update(axis_xy_world_m=bottom[:2].tolist(),bottom_z_world_m=float(bottom[2]))
            angles=np.linspace(0,2*np.pi,24,endpoint=False)
            ring=self.initial_bottom+np.c_[np.cos(angles),np.sin(angles),np.zeros_like(angles)]*self.initial_model['body_radius_m']
            model['support_footprint_world_m']=transform(ring,pose).tolist()
        return model,bottom

    def missing_pose(self,frame,current_hand,opened):
        steps=frame.env_step-self.last_observed_step
        if steps>self.max_missing_steps:return None,'missing_step_limit'
        now=getattr(frame,'timestamp_s',None)
        if now is not None and self.last_observed_time is not None and now-self.last_observed_time>self.max_missing_seconds+1e-8:
            return None,'missing_simulation_time_limit'
        delta=current_hand@np.linalg.inv(self.last_observed_hand)
        translation=np.linalg.norm(current_hand[:3,3]-self.last_observed_hand[:3,3])
        angle=Rotation.from_matrix(delta[:3,:3]).magnitude()
        if translation>self.max_gap_translation_m or angle>np.deg2rad(25):
            return None,'hand_motion_exceeds_short_gap_limit'
        if opened!=self.last_observed_open:return None,'gripper_mode_changed_without_visual_observation'
        center=transform(self.initial_bottom[None],self.last_observed_pose)[0]
        near=np.linalg.norm(center-self.last_observed_hand[:3,3])<.06
        aperture=np.mean(np.abs(frame.robot_state['robot0_gripper_qpos']))
        if not opened:
            if not (near and .005<aperture<.032):return None,'no_nearby_closed_hand_prediction_support'
            return delta@self.last_observed_pose,'short_gap_proprio_prediction'
        return self.last_observed_pose.copy(),'short_gap_stationary_assumption'

    @staticmethod
    def cloud(frame,mask):
        world=np.full((*frame.depth_m.shape,3),np.nan)
        world[frame.depth_valid]=unproject_world(frame)
        cloud=world[np.asarray(mask,bool)&frame.depth_valid]
        if len(cloud)<100:raise ValueError('segmented target depth has fewer than 100 samples')
        center=np.median(cloud,axis=0)
        cloud=cloud[np.linalg.norm(cloud-center,axis=1)<.25]
        return compact_cloud(cloud)

    def fit_observation(self,frame,masks,detection,predicted,current_hand,opened):
        candidates=[];failures=[]
        for index,(mask,category) in enumerate(zip(masks,detection['categories'])):
            if category!=self.category:continue
            try:
                cloud=self.cloud(frame,mask)
                previous=transform(self.reference,self.pose)
                shifted=self.pose.copy();shifted[:3,3]+=np.median(cloud,axis=0)-np.median(previous,axis=0)
                if np.linalg.norm(np.median(cloud,axis=0)-np.median(previous,axis=0))>.18:
                    raise ValueError('current same-class instance outside identity search gate')
                fits=[register_cloud(self.reference,cloud,seed) for seed in (predicted,shifted)]
                if self.occlusion_aware:
                    for fit_pose,quality in fits:
                        if quality['accepted']:continue
                        partial=visible_registration_quality(self.reference,cloud,fit_pose,frame,predicted)
                        quality['visibility_check']=partial
                        if partial['accepted']:
                            quality.update(accepted=True,acceptance_mode='depth_visible_partial_surface',
                                partial_pose_observability='bounded_by_previous_pose_and_proprioceptive_seed')
                valid=[fit for fit in fits if fit[1]['accepted']]
                pose,quality=min(valid or fits,key=lambda item:item[1]['median_distance_m'])
                if not quality['accepted']:raise ValueError(str(quality))
                if self.last_step>self.last_observed_step:
                    # Fresh measured geometry can reacquire after a hand mode
                    # change. The mode restriction applies to blind prediction.
                    expected=self.pose.copy()
                    if not opened and not self.last_observed_open:
                        expected=current_hand@np.linalg.inv(self.last_hand)@self.pose
                    difference=np.linalg.inv(expected)@pose
                    if np.linalg.norm(difference[:3,3])>.03 or Rotation.from_matrix(difference[:3,:3]).magnitude()>np.deg2rad(25):
                        raise ValueError('reacquisition disagrees with short-gap prediction')
                candidates.append((quality['median_distance_m'],pose,quality,index,cloud,frame,mask,detection))
            except ValueError as error:failures.append(dict(index=index,reason=str(error)))
        return candidates,failures

    def update(self,frame):
        if frame.env_step==self.last_step:return self.model,self.report
        if frame.env_step<self.last_step:raise ValueError('frame step moved backwards')
        start=time.perf_counter()
        masks,detection=self.segmenter(frame)
        current_hand=hand_pose(frame)
        predicted=current_hand@np.linalg.inv(self.last_hand)@self.pose
        opened=np.mean(np.abs(frame.robot_state['robot0_gripper_qpos']))>=.035
        if opened:predicted=self.pose.copy()
        candidates,failures=self.fit_observation(frame,masks,detection,predicted,current_hand,opened)
        camera_attempts=[dict(camera_id=getattr(frame,'camera_id','agentview'),detection=detection)]
        if not candidates and self.fallback_frame_provider is not None:
            alternate=self.fallback_frame_provider(frame)
            if alternate.env_step!=frame.env_step or not np.allclose(hand_pose(alternate),current_hand,atol=1e-6):
                raise ValueError('fallback camera must observe the same current robot state')
            alternate_masks,alternate_detection=self.segmenter(alternate)
            candidates,alternate_failures=self.fit_observation(alternate,alternate_masks,alternate_detection,predicted,current_hand,opened)
            failures.extend(dict(row,camera_id=alternate.camera_id) for row in alternate_failures)
            camera_attempts.append(dict(camera_id=alternate.camera_id,detection=alternate_detection))
        if not candidates:
            report=dict(env_step=frame.env_step,status='unresolved',detection=detection,rejections=failures,camera_attempts=camera_attempts)
            # Tolerate missing detections only. Contradictory/ambiguous measured
            # target geometry and worker errors retain their original failure.
            if all(self.category not in attempt['detection']['categories'] for attempt in camera_attempts) and self.max_missing_steps:
                pose,reason=self.missing_pose(frame,current_hand,opened)
                if pose is not None:
                    model,bottom=self.model_at_pose(pose,source=reason,observed=False)
                    report.update(status='predicted',pose_source=reason,visual_measurement=False,
                        last_observed_step=self.last_observed_step,missing_steps=frame.env_step-self.last_observed_step,
                        T_world_from_initial=pose.tolist(),bottom_world_m=bottom.tolist(),
                        oracle_object_state_used=False,eligible_for_goal_confirmation=False)
                    if self.output:(self.output/f'step{frame.env_step:05d}.json').write_text(json.dumps(report,indent=2))
                    self.last_step=frame.env_step;self.last_hand=current_hand;self.pose=pose;self.model=model;self.report=report
                    return model,report
                report['short_gap_rejection']=reason
            if self.output:(self.output/f'failure_step{frame.env_step:05d}.json').write_text(json.dumps(report,indent=2))
            raise ValueError('framewise RGB-D registration unresolved: '+json.dumps(report))
        candidates.sort(key=lambda item:item[0])
        if len(candidates)>1 and candidates[1][0]-candidates[0][0]<.001:
            raise ValueError('framewise same-class identity ambiguous')
        _,pose,quality,index,cloud,selected_frame,selected_mask,selected_detection=candidates[0]
        model,bottom=self.model_at_pose(pose,source='current_DINO_SAM_RGBD_SE3_registration',observed=True,cloud=cloud)
        self.report=dict(env_step=frame.env_step,status='observed',**quality,detection=selected_detection,
            selected_camera_id=getattr(selected_frame,'camera_id','agentview'),camera_attempts=camera_attempts,
            selected_detection=index,T_world_from_initial=pose.tolist(),bottom_world_m=bottom.tolist(),
            registration_and_vision_ms=(time.perf_counter()-start)*1000,
            radius_fit_constraint=False,upright_constraint=False,
            shape_reference='initial_RGBD_visible_surface_rigid_object_assumption',
            symmetry_yaw_observability='not_guaranteed',
            robot_pose_used_for_registration_seed_only=quality.get('acceptance_mode')!='depth_visible_partial_surface',
            robot_pose_used_for_partial_visibility_gate=quality.get('acceptance_mode')=='depth_visible_partial_surface',
            oracle_object_state_used=False)
        if self.output:
            (self.output/f'step{frame.env_step:05d}.json').write_text(json.dumps(self.report,indent=2))
            np.savez_compressed(self.output/f'step{frame.env_step:05d}.npz',points_world=cloud,mask=selected_mask)
        self.last_step=frame.env_step;self.last_hand=current_hand
        self.last_observed_step=frame.env_step;self.last_observed_hand=current_hand.copy()
        self.last_observed_pose=pose.copy();self.last_observed_time=getattr(frame,'timestamp_s',None)
        self.last_observed_open=opened
        self.pose=pose;self.model=model
        return model,self.report
