"""Offline gripper overlap, ambiguity components, and bidirectional geometry links."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def overlap_components(masks, threshold=.1):
    """Connected ambiguity components; these are NOT verified object instances."""
    if not np.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('invalid overlap threshold')
    if any(m.dtype != np.bool_ or not m.any() for m in masks):
        raise ValueError('nonempty bool masks required')
    if masks and any(m.shape != masks[0].shape for m in masks):
        raise ValueError('inconsistent mask shapes')
    adjacency=[set() for _ in masks]
    for i,m in enumerate(masks):
        for j in range(i):
            if (m & masks[j]).sum()/min(int(m.sum()),int(masks[j].sum())) > threshold:
                adjacency[i].add(j);adjacency[j].add(i)
    unseen=set(range(len(masks)));groups=[]
    while unseen:
        todo=[min(unseen)];component=set()
        while todo:
            i=todo.pop()
            if i in component:continue
            component.add(i);unseen.discard(i);todo.extend(adjacency[i]-component)
        groups.append(sorted(component))
    return groups


def overlap_record(mask, gripper, threshold=.98):
    if mask.dtype != np.bool_ or gripper.dtype != np.bool_ or mask.shape != gripper.shape or not mask.any():
        raise ValueError('aligned nonempty object mask and bool gripper mask required')
    if not np.isfinite(threshold) or not 0 < threshold <= 1:
        raise ValueError('invalid dominance threshold')
    n=int(mask.sum());overlap=int((mask & gripper).sum());fraction=overlap/n
    return dict(source_pixels=n,gripper_depth_consistent_overlap_pixels=overlap,
                gripper_overlap_fraction=fraction,remaining_pixels=n-overlap,
                offline_quarantine=fraction>=threshold,category_verified=False,identity_verified=False,
                planning_allowed=False,execution_allowed=False)


def projected_hits(source_mask, destination_mask, evidence):
    y,x=np.nonzero(source_mask & (evidence['status']==5))
    uv=evidence['destination_uv'][y,x]
    hits=destination_mask[uv[:,1],uv[:,0]]
    return dict(consistent_source_points=len(y),source_points_hitting_destination_mask=int(hits.sum()),
                unique_destination_pixels_hit=len(np.unique(uv[hits],axis=0)))


def link_strength(forward, reverse, fraction=.8, min_unique_pixels=20):
    """Diagnostic gate on both directions; never proves identity or semantics."""
    ratios=[r['source_points_hitting_destination_mask']/r['consistent_source_points']
            if r['consistent_source_points'] else 0. for r in (forward,reverse)]
    supported=all(v>=fraction for v in ratios) and all(r['unique_destination_pixels_hit']>=min_unique_pixels for r in (forward,reverse))
    return dict(wrist_to_agent_hit_fraction=ratios[0],agent_to_wrist_hit_fraction=ratios[1],
                diagnostic_strength_gate_passed=supported)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('input-dir','wrist-root','gripper-root','out-dir'):
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
    from experiments.robot.libero.skill_pipeline.cross_view_pixel_evidence import project_pixel_evidence, STATUS
    from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    wrist_report_path=args.wrist_root/'report.json';gripper_report_path=args.gripper_root/'report.json'
    wrist_report=json.loads(wrist_report_path.read_text());gripper_report=json.loads(gripper_report_path.read_text())
    for report in (wrist_report,gripper_report):
        for name,value in report['input_sha256'].items():
            if sha(Path(name))!=value:raise ValueError('upstream observation changed')
    steps=[r['env_step'] for r in wrist_report['results']]
    if steps!=[r['env_step'] for r in gripper_report['results']]:raise ValueError('upstream steps differ')
    args.out_dir.mkdir(parents=True,exist_ok=False)
    inputs={str(p):sha(p) for p in (wrist_report_path,gripper_report_path)};results=[]
    nominal=.98;thresholds=(.95,.98,.995,1.)
    def groups(detections,masks,indices,prefix):
        components=overlap_components(masks);rows=[];unions=[]
        for i,component in enumerate(components):
            union=np.logical_or.reduce([masks[j] for j in component]);unions.append(union)
            categories=sorted({detections[indices[j]].category for j in component if detections[indices[j]].category is not None})
            rows.append(dict(frame_local_group_id=prefix+str(i),original_mask_indices=[indices[j] for j in component],
                             category_alternatives=categories,category_status='ambiguous' if len(categories)>1 else 'unverified',
                             visible_union_pixels=int(union.sum()),boundary_touching=bool(union[0].any() or union[-1].any() or union[:,0].any() or union[:,-1].any()),
                             identity_verified=False,planning_allowed=False,execution_allowed=False))
        return rows,unions
    with OracleImportGuard() as guard:
        for step in steps:
            directory=args.input_dir/'frames'/f'step{step:06d}'
            wrist=load_observation(directory/'robot0_eye_in_hand');primary=load_observation(directory/'observation')
            validate_synchronized_views(wrist,primary)
            wid,wd=load_detections(wrist,args.wrist_root/f'step{step:06d}/detector');pid,pd=load_detections(primary,directory/'detector')
            if wid!=wrist_report['detector_id'] or pid!=wid:raise ValueError('detector identity mismatch')
            gp=args.gripper_root/f'step{step:06d}/gripper_projection.npz'
            with np.load(gp,allow_pickle=False) as data:
                depth=data['mesh_depth_m'];projected=data['projected_mask'];gripper=data['consistent_5mm']
                if (depth.shape!=wrist.depth_m.shape or not np.array_equal(projected,np.isfinite(depth))
                        or not np.array_equal(gripper,projected & wrist.depth_valid & (np.abs(wrist.depth_m-depth)<=.005))):raise ValueError('invalid cached projection')
            records=[dict(original_mask_index=i,category_hypothesis=d.category,**overlap_record(d.mask,gripper,nominal)) for i,d in enumerate(wd)]
            indices=[i for i,r in enumerate(records) if not r['offline_quarantine'] and r['remaining_pixels']>0]
            masks=[wd[i].mask & ~gripper for i in indices]
            wr,wm=groups(wd,masks,indices,'W');pr,pm=groups(pd,[d.mask for d in pd],list(range(len(pd))),'A')
            def evidence(source,masks,destination):
                if masks:return project_pixel_evidence(source,np.logical_or.reduce(masks),destination,.005)
                return dict(status=np.zeros(source.depth_m.shape,np.uint8),destination_uv=np.full((*source.depth_m.shape,2),-1,np.int32),delta_m=np.full(source.depth_m.shape,np.nan))
            forward=evidence(wrist,wm,primary);reverse=evidence(primary,pm,wrist)
            links=[]
            for i,m in enumerate(wm):
                counts={name:int((m & (forward['status']==code)).sum()) for code,name in STATUS.items() if code}
                wr[i]['wrist_to_agent_status_counts']=counts
                if sum(counts.values())!=int(m.sum()):raise ValueError('projection partition mismatch')
                for j,a in enumerate(pm):
                    f=projected_hits(m,a,forward);r=projected_hits(a,m,reverse)
                    if f['source_points_hitting_destination_mask'] or r['source_points_hitting_destination_mask']:
                        links.append(dict(wrist_group_id=wr[i]['frame_local_group_id'],agent_group_id=pr[j]['frame_local_group_id'],wrist_to_agent=f,agent_to_wrist=r,
                                          bidirectional_geometric_support=bool(f['source_points_hitting_destination_mask'] and r['source_points_hitting_destination_mask']),
                                          **link_strength(f,r),strength_fraction_sensitivity={str(t):link_strength(f,r,t)['diagnostic_strength_gate_passed'] for t in (.5,.8,.95)},
                                          category_alternatives_across_views=sorted(set(wr[i]['category_alternatives'])|set(pr[j]['category_alternatives'])),
                                          same_category_set=wr[i]['category_alternatives']==pr[j]['category_alternatives'],identity_verified=False,category_verified=False))
            row=dict(env_step=step,candidates=records,quarantine_threshold_sensitivity={str(t):[i for i,d in enumerate(wd) if overlap_record(d.mask,gripper,t)['offline_quarantine']] for t in thresholds},
                     wrist_ambiguity_components=wr,agent_ambiguity_components=pr,geometric_links=links,
                     category_verified=False,identity_fused=False,planning_allowed=False,execution_allowed=False)
            target=args.out_dir/f'step{step:06d}';target.mkdir()
            np.savez_compressed(target/'ambiguity_component_masks.npz',wrist=np.stack(wm) if wm else np.empty((0,*wrist.depth_m.shape),bool),agent=np.stack(pm) if pm else np.empty((0,*primary.depth_m.shape),bool))
            for label,e in (('wrist_to_agent',forward),('agent_to_wrist',reverse)):
                np.savez_compressed(target/(label+'.npz'),status=e['status'],destination_uv=e['destination_uv'],delta_m=e['delta_m'])
            (target/'diagnostic.json').write_text(json.dumps(row,indent=2)+'\n');results.append(row)
            files=[gp]
            for obs in ('robot0_eye_in_hand','observation'):files.extend(directory/obs/name for name in ('metadata.json','rgbd.npz'))
            for dd in (args.wrist_root/f'step{step:06d}/detector',directory/'detector'):files.extend(dd/name for name in ('detections.json','detections.npz'))
            inputs.update({str(p):sha(p) for p in files})
            print(json.dumps(dict(env_step=step,quarantined=[r['original_mask_index'] for r in records if r['offline_quarantine']],wrist_groups=[r['category_alternatives'] for r in wr],bidirectional_links=sum(l['bidirectional_geometric_support'] for l in links))),flush=True)
        report=dict(scope='offline_frame_local_ambiguity_components_and_geometric_links',episode_id=wrist_report['episode_id'],results=results,
                    nominal_diagnostic_quarantine_threshold=nominal,thresholds_not_calibrated=True,projection_tolerance_m=.005,
                    diagnostic_link_gate=dict(bidirectional_hit_fraction=.8,min_unique_destination_pixels_each_direction=20),
                    environment_actions=0,policy_inferences=0,blocked_oracle_import_attempts=guard.blocked_import_attempts,
                    production_compatible=False,identity_fused=False,input_sha256=inputs,source_sha256={str(Path(__file__)):sha(Path(__file__))})
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
