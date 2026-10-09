"""Anchor bottle tracking from learned RGB appearance and measured depth.

This diagnostic assumes the fitted bottle stays upright. Robot motion only
predicts a search location; accepted object poses always require depth samples.
"""
import copy
import numpy as np
from scipy.ndimage import label
from scipy.optimize import least_squares
from .rgbd_observation import unproject_world
from .visual_bottle_geometry import connected_depth_surface


class BottleColorDepthTracker:
    def __init__(self, frame, mask, model):
        self.initial_model=copy.deepcopy(model)
        self.current_model=copy.deepcopy(model)
        colours=frame.rgb[mask].astype(float)
        dark=colours[np.max(colours,axis=1)<=np.percentile(np.max(colours,axis=1),65)]
        self.channel=int(np.argmax(np.median(dark,axis=0)))
        self.other=[i for i in range(3) if i!=self.channel]
        contrast=dark[:,self.channel,None]-dark[:,self.other]
        if len(dark)<50 or np.median(contrast)<1:
            raise ValueError('anchor bottle appearance is not distinct enough for colour tracking')
        self.max_brightness=float(np.percentile(np.max(dark,axis=1),95)+12)
        self.minimum_contrast=max(1.,float(np.percentile(contrast,10)-1))
        world=self._world(frame)
        own=mask & self._colour_mask(frame) & frame.depth_valid
        self.bottom_offset=model['bottom_z_world_m']-float(np.quantile(world[own,2],.01))
        self.previous_eef=np.asarray(frame.robot_state['robot0_eef_pos'],float)
        self.last_step=frame.env_step
        self.report={}

    def _world(self, frame):
        world=np.full((*frame.depth_m.shape,3),np.nan)
        world[frame.depth_valid]=unproject_world(frame)
        return world

    def _colour_mask(self,frame):
        rgb=frame.rgb.astype(float)
        contrast=rgb[...,self.channel,None]-rgb[...,self.other]
        return (np.max(rgb,axis=-1)<=self.max_brightness)&np.all(contrast>=self.minimum_contrast,axis=-1)

    def update(self,frame):
        if frame.env_step==self.last_step:return self.current_model,self.report
        if frame.env_step<self.last_step:raise ValueError('tracking frame moved backwards')
        world=self._world(frame)
        eef=np.asarray(frame.robot_state['robot0_eef_pos'],float)
        prediction=np.asarray(self.current_model['axis_xy_world_m'],float)
        q=np.asarray(frame.robot_state['robot0_gripper_qpos'])
        if np.mean(abs(q))<.035:prediction=prediction+(eef-self.previous_eef)[:2]
        components,n=label(self._colour_mask(frame)&frame.depth_valid,np.ones((3,3)))
        candidates=[]
        radius=self.initial_model['body_radius_m']
        for i in range(1,n+1):
            mask=components==i
            if mask.sum()<50:continue
            try:mask,_unused=connected_depth_surface(world,mask)
            except (TypeError,ValueError):continue
            # connected_depth_surface returns mask and component-size report.
            points=world[mask]
            if len(points)<50 or np.ptp(points[:,2])<.035:continue
            if np.linalg.norm(np.median(points[:,:2],axis=0)-prediction)>.14:continue
            lower=points[points[:,2]<=np.quantile(points[:,2],.5),:2]
            def residual(xy):return np.linalg.norm(lower-xy,axis=1)-radius
            fits=[least_squares(residual,prediction+offset,loss='soft_l1',f_scale=.001)
                  for offset in (np.zeros(2),np.array([.02,0]),np.array([-.02,0]))]
            fit=min(fits,key=lambda f:np.median(abs(residual(f.x))))
            errors=abs(residual(fit.x))
            if np.median(errors)>.002 or np.quantile(errors,.95)>.005:continue
            bottom=float(np.quantile(points[:,2],.01)+self.bottom_offset)
            candidates.append((float(np.linalg.norm(fit.x-prediction)),fit.x,bottom,mask,
                               float(np.median(errors))))
        candidates.sort(key=lambda c:c[0])
        if not candidates or candidates[0][0]>.08:
            raise ValueError('current RGB-D bottle tracking unresolved')
        if len(candidates)>1 and candidates[1][0]-candidates[0][0]<.02:
            raise ValueError('current bottle appearance association ambiguous')
        _,xy,bottom,mask,error=candidates[0]
        model=copy.deepcopy(self.initial_model)
        delta=bottom-model['bottom_z_world_m']
        model['axis_xy_world_m']=xy.tolist();model['bottom_z_world_m']=bottom
        model['top_z_world_m']+=delta
        for part in model['parts']:part['z_min_m']+=delta;part['z_max_m']+=delta
        model['pose_source']='current_rgb_appearance_and_depth_fixed_radius_fit'
        self.report=dict(env_step=frame.env_step,observed_point_count=int(mask.sum()),
            fit_residual_median_m=error,axis_xy_world_m=xy.tolist(),bottom_z_world_m=bottom,
            learned_dominant_channel=self.channel,robot_motion_used_for_search_only=True,
            hidden_shape_prior='initial_rgbd_upright_bottle_fit',oracle_object_state_used=False)
        self.current_model=model;self.previous_eef=eef;self.last_step=frame.env_step
        return model,self.report
