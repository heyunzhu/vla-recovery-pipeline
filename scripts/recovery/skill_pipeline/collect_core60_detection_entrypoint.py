"""Instrument frozen C4 rollouts for offline RGB/instance labels only.

Truth identities are confined to the label writer. The policy still receives
its ordinary RGB/proprioception. A genuine C4 recovery trigger is captured,
then returns to VLA; this collector does not benchmark a recovery controller.
"""
from pathlib import Path
import hashlib,json,os,runpy,sys
import numpy as np
from PIL import Image

RUN=Path(os.environ['FULL_DINO_RUN']);CODE=Path(os.environ['FULL_DINO_CODE'])
FROZEN=RUN/'runtime/frozen_runtime';CASE=Path(os.environ['FULL_DINO_CASE'])
sys.path.insert(0,str(CODE));sys.path.insert(0,str(FROZEN))
from experiments.robot.libero.skill_pipeline import runner
from experiments.robot.libero.tiptop_repro import cutamp_controller_v2 as ctl
from scripts.recovery.skill_pipeline.shared_benchmark_policy import SharedBenchmarkPolicy
runner.JaxOpenPIUncertaintyPolicyAdapter=SharedBenchmarkPolicy
runner.SubprocessOpenPIUncertaintyPolicyAdapter=SharedBenchmarkPolicy
TAXONOMY=json.loads((RUN/'taxonomy.json').read_text());CLASSES=TAXONOMY['classes']
RECORD=json.loads((CASE/'record.json').read_text())


class Annotator:
    def __init__(self,env):
        from robosuite.utils.binding_utils import MjRenderContextOffscreen
        self.env=env;self.sim=env.env.sim;self.model=self.sim.model;self.step=0
        self.rgb=self.sim._render_context_offscreen;self.rgb.gl_ctx.make_current()
        self.rgb.update_offscreen_size(640,640)
        samples=int(self.model.vis.quality.offsamples);self.model.vis.quality.offsamples=0
        try:self.seg=MjRenderContextOffscreen(self.sim,device_id=int(os.environ['FULL_DINO_RENDER_GPU']),max_width=640,max_height=640)
        finally:self.model.vis.quality.offsamples=samples
        self.seg.vopt.geomgroup[:]=self.rgb.vopt.geomgroup;self.seg.vopt.sitegroup[:]=self.rgb.vopt.sitegroup;self.seg.vopt.flags[:]=self.rgb.vopt.flags
        assert self.seg.con.offSamples==0
        self.sim._render_context_offscreen=self.rgb
        assets={**env.env.fixtures_dict,**env.env.objects_dict};self.objects=[];all_objects=[]
        for name,obj in sorted(assets.items()):
            typ=type(obj).__name__.lower().removesuffix('object')
            # BDDL object declarations define asset identities for offline labels.
            asset=RECORD['instance_assets'][name]
            body=int(self.model.body_name2id(obj.root_body))
            all_objects.append(dict(name=name,**{'class':type(obj).__name__},position=np.round(self.sim.data.body_xpos[body],4).tolist(),quaternion=np.round(self.sim.data.body_xquat[body],4).tolist()))
            if asset in TAXONOMY['excluded_assets']:continue
            category=TAXONOMY['asset_to_category'][asset]
            self.objects.append(dict(name=name,asset=asset,category=category,body=body))
        self.layout=hashlib.sha256(json.dumps(all_objects,sort_keys=True).encode()).hexdigest()
        self.lut=np.zeros(self.model.ngeom,np.uint16);self.robot=np.zeros(self.model.ngeom,bool)
        roots={o['body']:i+1 for i,o in enumerate(self.objects)}
        for geom in range(self.model.ngeom):
            body=int(self.model.geom_bodyid[geom])
            while body:
                if body in roots:self.lut[geom]=roots[body];break
                body=int(self.model.body_parentid[body])
            name=self.model.geom_id2name(geom) or '';self.robot[geom]=name.startswith(('robot0_','gripper0_','mount0_'))
        self.goal_pairs=[]
        for atom in env.env.parsed_problem.get('goal_state',[]):
            if len(atom)>=3 and str(atom[0]).lower() in ['on','in','inside']:
                self.goal_pairs.append(dict(target_instance=atom[1],goal_instance=atom[2]))
        (CASE/'initial_layout.json').write_text(json.dumps(dict(layout_group=self.layout,objects=all_objects,annotation_objects=self.objects),indent=2))
        self.seen=set()

    def capture(self,phase):
        key=(self.step,phase)
        if key in self.seen:return
        self.seen.add(key)
        for camera in ['agentview','robot0_eye_in_hand']:
            camera_id=self.model.camera_name2id(camera)
            self.rgb.gl_ctx.make_current();self.rgb.render(640,640,camera_id=camera_id,segmentation=False)
            rgb=np.ascontiguousarray(self.rgb.read_pixels(640,640)[::-1])
            self.seg.gl_ctx.make_current();self.seg.render(640,640,camera_id=camera_id,segmentation=True)
            seg=self.seg.read_pixels(640,640,segmentation=True)[::-1];ids=seg[...,1]
            valid=(seg[...,0]==5)&(ids>=0)&(ids<self.model.ngeom)
            instance=np.zeros(ids.shape,np.uint16);instance[valid]=self.lut[ids[valid]]
            robot=np.zeros(ids.shape,bool);robot[valid]=self.robot[ids[valid]]
            annotations=[]
            for i,obj in enumerate(self.objects,1):
                ys,xs=np.nonzero(instance==i)
                if not len(xs):continue
                x,y=int(xs.min()),int(ys.min());w,h=int(xs.max())-x+1,int(ys.max())-y+1
                # Tiny fragments are retained and explicitly stratified at evaluation.
                annotations.append(dict(category_id=CLASSES.index(obj['category'])+1,bbox=[x,y,w,h],area=w*h,iscrowd=0,visible_pixels=len(xs),instance_name=obj['name']))
            instance[robot]=65535
            stem=f"{RECORD['case_id']}_{phase}_{self.step:05d}_{camera}"
            dataset=Path(os.environ['FULL_DINO_DATASET'])
            for folder in ['images640','instance_masks640','states']:(dataset/folder).mkdir(parents=True,exist_ok=True)
            Image.fromarray(rgb).save(dataset/'images640'/(stem+'.png'),compress_level=1)
            Image.fromarray(instance).save(dataset/'instance_masks640'/(stem+'.png'))
            np.save(dataset/'states'/(stem+'.npy'),self.sim.get_state().flatten())
            row=dict(id=int(hashlib.sha256(stem.encode()).hexdigest()[:12],16),file_name='images640/'+stem+'.png',width=640,height=640,episode=RECORD['case_id'],suite=RECORD['suite'],task_id=RECORD['task_1based'],init_id=RECORD['init_id'],split=RECORD['split'],phase=phase,step=self.step,camera=camera,layout_group=self.layout,pixel_sha256=hashlib.sha256(rgb.tobytes()).hexdigest(),task_language=RECORD['language'],goal_role_pairs=self.goal_pairs,annotations=annotations)
            with (CASE/'frames.jsonl').open('a') as stream:stream.write(json.dumps(row)+'\n')
        self.rgb.gl_ctx.make_current();self.sim._render_context_offscreen=self.rgb


def get_env(task,resolution,seed):
    from libero.libero.envs import OffScreenRenderEnv
    env=OffScreenRenderEnv(bddl_file_name=str(task.bddl_path),camera_heights=256,camera_widths=256,render_gpu_device_id=int(os.environ['FULL_DINO_RENDER_GPU']))
    env.seed(seed);original_init=env.set_init_state;original_step=env.step
    def initialize(state):
        result=original_init(state);env._labeler=Annotator(env);env._labeler.capture('initial');return result
    def step(action,*args,**kwargs):
        result=original_step(action,*args,**kwargs)
        if hasattr(env,'_labeler'):
            env._labeler.step+=1
            if env._labeler.step in [10,35,60,85,110,135,160,185,210,235,260,285]:env._labeler.capture('policy_rollout')
        return result
    env.set_init_state=initialize;env.step=step
    return env,task.language


def capture_handoff(self,env,obs,language,*args,**kwargs):
    env._labeler.capture('skill_trigger')
    with (CASE/'handoffs.jsonl').open('a') as stream:stream.write(json.dumps(dict(step=env._labeler.step,language=language,hints=kwargs.get('recovery_hints'),offline_collection_only=True))+'\n')
    return ctl.CuTAMPRecoveryResult(obs=obs,success=False,total_env_steps=0)

runner._get_libero_env=get_env
ctl.CuTAMPV2TipTopController.recover=capture_handoff
runpy.run_path(str(RUN/'runtime/core60_entrypoint.py'),run_name='__main__')
