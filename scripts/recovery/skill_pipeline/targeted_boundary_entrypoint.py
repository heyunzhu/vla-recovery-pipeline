"""Frozen-runner overlay for physical, audited skill-boundary perturbations.

No source asset/pack changes. Reject unsupported XML transforms rather than
silently changing only the planner proxy. Config is passed via BOUNDARY_CONFIG.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np


def quat_matrix(q):
    q = np.asarray(q, dtype=float)
    q /= np.linalg.norm(q)
    w,x,y,z=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                     [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                     [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])


def numbers(node, key, default):
    return np.fromstring(node.get(key,default),sep=' ')


def stretch_xml(xml, body_name, factor):
    if not 0.5 <= factor <= 1.5:
        raise ValueError('thickness factor outside admitted pilot range')
    root=ET.fromstring(xml)
    body=root.find(f".//body[@name='{body_name}']")
    if body is None or body.findall('body') or body.find('inertial') is not None:
        raise ValueError('requires one rigid root with auto-computed inertia')
    asset=root.find('asset')
    stretch=np.diag([1.,1.,factor])
    for geom in body.findall('geom'):
        if any(k in geom.attrib for k in ('euler','axisangle','xyaxes','zaxis','fromto')):
            raise ValueError('unsupported geom orientation')
        rot=quat_matrix(numbers(geom,'quat','1 0 0 0'))
        squared=rot.T @ stretch.T @ stretch @ rot
        if np.max(np.abs(squared-np.diag(np.diag(squared))))>1e-7:
            raise ValueError('anisotropic stretch not representable at this geom rotation')
        scale=np.sqrt(np.diag(squared))
        pos=numbers(geom,'pos','0 0 0')*np.array([1.,1.,factor])
        geom.set('pos',' '.join(map(str,pos)))
        kind=geom.get('type','sphere')
        if kind=='box':
            geom.set('size',' '.join(map(str,numbers(geom,'size','')*scale)))
        elif kind=='mesh':
            mesh=asset.find(f"mesh[@name='{geom.get('mesh')}']")
            if mesh is None or mesh.get('refpos') or mesh.get('refquat'):
                raise ValueError('unsupported mesh reference transform')
            new=copy.deepcopy(mesh)
            new.set('name',mesh.get('name')+'_boundary_'+str(len(asset)))
            new.set('scale',' '.join(map(str,numbers(mesh,'scale','1 1 1')*scale)))
            asset.append(new)
            geom.set('mesh',new.get('name'))
        else:
            raise ValueError('unsupported target geom: '+kind)
        # Preserve geom mass (and recompute shape-dependent inertia on compile).
        if 'mass' not in geom.attrib:
            geom.set('density',str(float(geom.get('density','1000'))/factor))
    for site in body.findall('site'):
        site.set('pos',' '.join(map(str,numbers(site,'pos','0 0 0')*np.array([1.,1.,factor]))))
    return ET.tostring(root,encoding='unicode')


def bounds(env, name):
    obj=env.env.objects_dict[name]
    model,data=env.sim.model,env.sim.data
    lows=[]; highs=[]
    for geom_name in obj.contact_geoms:
        gid=model.geom_name2id(geom_name)
        center=data.geom_xpos[gid]
        kind=int(model.geom_type[gid])
        rot=data.geom_xmat[gid].reshape(3,3)
        if kind==7:
            mid=int(model.geom_dataid[gid]); start=int(model.mesh_vertadr[mid]); n=int(model.mesh_vertnum[mid])
            points=model.mesh_vert[start:start+n] @ rot.T + center
            lows.append(points.min(axis=0));highs.append(points.max(axis=0))
        elif kind==6:
            radius=np.abs(rot) @ model.geom_size[gid]
            lows.append(center-radius);highs.append(center+radius)
        else:
            raise ValueError('unsupported collision geom for boundary audit: '+str(kind))
    return np.min(lows,axis=0),np.max(highs,axis=0)


def set_object_xy(env, name, xy):
    obj=env.env.objects_dict[name]
    q=np.array(env.sim.data.get_joint_qpos(obj.joints[0]),copy=True)
    assert len(q)==7
    q[:2]=xy
    env.sim.data.set_joint_qpos(obj.joints[0],q)
    env.sim.data.set_joint_qvel(obj.joints[0],np.zeros(6))
    env.sim.forward()


def install_env_overlay(runner, config):
    original=runner._get_libero_env
    def create(task,resolution,seed):
        env,description=original(task,resolution,seed)
        target=config['target']
        original_reset=env.reset
        original_set=env.set_init_state
        factor=config.get('thickness_factor',1.)
        env.boundary_episode=-1
        env.boundary_query=0
        def reset():
            obs=original_reset()
            if factor!=1.:
                xml=stretch_xml(env.env.model.get_xml(),env.env.objects_dict[target].root_body,factor)
                env.reset_from_xml_string(xml)
                obs=env.env._get_observations()
            return obs
        count=0
        def set_init(state):
            nonlocal count
            obs=original_set(state)
            before=np.asarray(state,dtype=float)
            before_bounds=bounds(env,target)
            if factor!=1.:
                # Modified local z must coincide with world vertical for this pilot.
                bid=env.sim.model.body_name2id(env.env.objects_dict[target].root_body)
                if abs(env.sim.data.body_xmat[bid].reshape(3,3)[2,2])<0.999:
                    raise ValueError('target local z is not vertical')
                q=np.array(env.sim.data.get_joint_qpos(env.env.objects_dict[target].joints[0]),copy=True)
                # Preserve original collision bottom, including offset collision geoms.
                body_z=float(env.sim.data.body_xpos[bid][2])
                new_bottom=float(before_bounds[0][2])
                original_bottom=body_z+(new_bottom-body_z)/factor
                q[2]+=original_bottom-new_bottom
                env.sim.data.set_joint_qpos(env.env.objects_dict[target].joints[0],q)
                env.sim.forward()
            blocker=config.get('blocker')
            if blocker:
                bid=env.sim.model.body_name2id(env.env.objects_dict[blocker].root_body)
                pos=env.sim.data.body_xpos[bid].copy()
                if 'side_gap_m' in config:
                    lo,hi=bounds(env,target)
                    # Move blocker along world Y; use a conservative physical XY radius.
                    glo,ghi=bounds(env,blocker)
                    radius=max((ghi[:2]-glo[:2])/2)
                    pos[:2]=[(lo[0]+hi[0])/2,hi[1]+radius+config['side_gap_m']]
                elif 'ee_distance_m' in config:
                    ee=env.sim.data.site_xpos[env.env.robots[0].eef_site_id]
                    direction=pos[:2]-ee[:2]
                    direction/=max(np.linalg.norm(direction),1e-8)
                    # Keep original Z; set initial 3-D EE-to-body-center distance.
                    d=config['ee_distance_m']; dz=pos[2]-ee[2]
                    if abs(dz)>=d:
                        raise ValueError('requested EE distance below vertical separation')
                    pos[:2]=ee[:2]+direction*np.sqrt(d*d-dz*dz)
                elif 'blocker_radial_shift_m' in config:
                    ee=env.sim.data.site_xpos[env.env.robots[0].eef_site_id]
                    direction=pos[:2]-ee[:2]
                    direction/=max(np.linalg.norm(direction),1e-8)
                    pos[:2]+=direction*config['blocker_radial_shift_m']
                set_object_xy(env,blocker,pos[:2])
            env.sim.forward()
            for c in env.sim.data.contact[:env.sim.data.ncon]:
                g1=env.sim.model.geom_id2name(c.geom1) or ''
                g2=env.sim.model.geom_id2name(c.geom2) or ''
                if c.dist < -0.001 and ((target in g1 and blocker and blocker in g2) or (target in g2 and blocker and blocker in g1)):
                    raise ValueError('initial target-blocker penetration')
            if env.check_success():
                raise ValueError('already-successful initial state')
            current=env.sim.get_state().flatten()
            lo,hi=bounds(env,target)
            audit=dict(episode_index=count,config=config,target_collision_bounds=[lo.tolist(),hi.tolist()],
                modified_state_sha256=hashlib.sha256(np.asarray(current,dtype=np.float64).tobytes()).hexdigest(),
                source_state_sha256=hashlib.sha256(before.astype(np.float64).tobytes()).hexdigest(),
                mass=float(env.sim.model.body_mass[env.sim.model.body_name2id(env.env.objects_dict[target].root_body)]))
            if blocker:
                bid=env.sim.model.body_name2id(env.env.objects_dict[blocker].root_body)
                audit['blocker_xyz']=env.sim.data.body_xpos[bid].tolist()
            with Path(os.environ['BOUNDARY_AUDIT']).open('a') as f:
                f.write(json.dumps(audit)+'\n')
            count+=1
            env.boundary_episode=count-1
            env.boundary_query=0
            return env.regenerate_obs_from_state(current)
        env.reset=reset
        env.set_init_state=set_init
        runner.boundary_live_env=env
        return env,description
    runner._get_libero_env=create
    query_original=runner._query_state
    def query(*args,**kwargs):
        state=query_original(*args,**kwargs)
        env=runner.boundary_live_env
        snapshot=Path(os.environ['BOUNDARY_AUDIT']).parent/'query_states'/f'ep{env.boundary_episode:02d}'
        snapshot.mkdir(parents=True,exist_ok=True)
        np.save(snapshot/f'q{env.boundary_query:03d}.npy',env.sim.get_state().flatten())
        env.boundary_query+=1
        return state
    runner._query_state=query


def main():
    import sys
    from libero.libero import benchmark, get_libero_path
    suite='libero_object_task'
    stems=sorted(p.stem for p in (Path(get_libero_path('bddl_files'))/suite).glob('*.bddl'))
    benchmark.libero_task_map[suite]=stems
    benchmark.task_maps[suite]={stem:benchmark.Task(name=stem,language=benchmark.grab_language_from_filename(stem+'.bddl'),problem='Libero',problem_folder=suite,bddl_file=stem+'.bddl',init_states_file=stem+'.pruned_init') for stem in stems}
    def init(self,task_order_index=0):
        benchmark.Benchmark.__init__(self,task_order_index=task_order_index)
        self.name=suite
        self._make_benchmark()
    benchmark.BENCHMARK_MAPPING[suite]=type('BOUNDARY_OBJECT_TASK',(benchmark.Benchmark,),{'__init__':init})
    from experiments.robot.libero.skill_pipeline import runner
    config=json.loads(Path(os.environ['BOUNDARY_CONFIG']).read_text())
    install_env_overlay(runner,config)
    if config.get('profile_arm')=='generic':
        from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
        for method in ('_emit','force_recovery_query'):
            original=getattr(SkillRuntime,method)
            def wrapped(self,*a,_original=original,**kw):
                result=_original(self,*a,**kw)
                if result and result.get('enter_recovery'):
                    result['recovery_hints']['grasp_profile']='libero_topdown'
                    result['recovery_hints'].get('params',{}).pop('grasp_profile_adapter',None)
                    result['recovery_hints'].get('params',{}).pop('_grasp_profile_adapter_path',None)
                    params=result['recovery_hints'].setdefault('params',{})
                    params['boundary_profile_arm']='generic'
                    params['capability_audit_before_boundary_override']=params.pop('capability_audit',None)
                return result
            setattr(SkillRuntime,method,wrapped)
    runner.main(runner.parse_args())


if __name__=='__main__':
    main()
