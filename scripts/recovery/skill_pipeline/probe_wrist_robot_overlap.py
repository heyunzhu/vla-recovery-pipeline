"""Offline independent wrist gripper hypotheses and object-mask subtraction."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('input-dir','object-root','reference-json','out-dir','grounding-model-dir','sam2-model-dir'):
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from run_grounded_sam2_snapshot import _verify_model_weights,GROUNDING_SHA256,SAM2_SHA256,GROUNDING_REVISION,SAM2_REVISION
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        import torch
        import transformers
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections,save_detections,rgb_sha256
        from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
        from experiments.robot.libero.skill_pipeline.rgbd_scene import mask_conflicts
        args.out_dir.mkdir(parents=True,exist_ok=False)
        prior_path=args.object_root/'report.json';prior=json.loads(prior_path.read_text())
        references=json.loads(args.reference_json.read_text());refs={r['env_step']:r for r in references['frames']}
        config=dict(prior['configuration'])
        if (config['torch_version']!=torch.__version__ or config['transformers_version']!=transformers.__version__
                or config['grounding_sha256']!=GROUNDING_SHA256 or config['sam2_sha256']!=SAM2_SHA256
                or config['grounding_revision']!=GROUNDING_REVISION or config['sam2_revision']!=SAM2_REVISION):
            raise ValueError('pinned libraries or model configuration mismatch')
        config.update(prompts={'robot':'robot gripper'},prompt_source='explicit_wrist_robot_probe',task_language=None,device='cpu')
        identity='grounded-sam2-'+hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:12]
        detector=GroundedSam2Detector(grounding_model=str(_verify_model_weights(args.grounding_model_dir,GROUNDING_SHA256)),grounding_revision=GROUNDING_REVISION,
            sam2_model=str(_verify_model_weights(args.sam2_model_dir,SAM2_SHA256)),sam2_revision=SAM2_REVISION,
            prompts=config['prompts'],box_threshold=config['box_threshold'],text_threshold=config['text_threshold'],device='cpu')
        results=[];files=[prior_path,args.reference_json]
        for source in prior['results']:
            step=source['env_step'];observation=args.input_dir/'frames'/f'step{step:06d}'/'robot0_eye_in_hand'
            for name in ('rgbd.npz','metadata.json'):
                path=observation/name
                if hashlib.sha256(path.read_bytes()).hexdigest()!=prior['input_sha256'][str(path)]:raise ValueError('wrist observation changed')
                files.append(path)
            frame=load_observation(observation)
            if frame.episode_id!=prior['episode_id'] or frame.env_step!=step or frame.camera_id!='robot0_eye_in_hand':raise ValueError('wrong wrist frame')
            objdir=args.object_root/f'step{step:06d}'/'detector'
            oid,objects=load_detections(frame,objdir)
            if oid!=prior['detector_id']:raise ValueError('object detector mismatch')
            robot_detections=detector(frame)
            robot=np.logical_or.reduce([d.mask for d in robot_detections]) if robot_detections else np.zeros(frame.depth_m.shape,dtype=bool)
            # Diagnostic arrays only; the filtered mask format is not a runtime detection artifact.
            filtered=[dataclasses.replace(d,mask=d.mask & ~robot) for d in objects if (d.mask & ~robot).any()]
            target=args.out_dir/f'step{step:06d}';target.mkdir()
            save_detections(frame,robot_detections,target/'robot_detector',detector_id=identity)
            (target/'robot_detector/run_config.json').write_text(json.dumps(config,indent=2)+'\n')
            (target/'robot_detector/grounding_boxes.json').write_text(json.dumps(detector.last_grounding_boxes,indent=2)+'\n')
            filtered_indices=[i for i,d in enumerate(objects) if (d.mask & ~robot).any()]
            np.savez_compressed(target/'offline_candidate_masks.npz',candidate_masks=np.stack([d.mask for d in filtered]) if filtered else np.empty((0,*robot.shape),dtype=bool),robot_union=robot,candidate_indices=np.array(filtered_indices,dtype=np.int32))
            overlaps=[dict(mask_index=i,category_hypothesis=d.category,source_pixels=int(d.mask.sum()),robot_overlap_pixels=int((d.mask & robot).sum()),robot_overlap_fraction=float((d.mask & robot).sum()/d.mask.sum())) for i,d in enumerate(objects)]
            point_checks=None
            if step in refs:
                ref=refs[step]
                if ref['rgb_sha256']!=rgb_sha256(frame) or ref['episode_id']!=frame.episode_id or ref['camera_id']!=frame.camera_id:raise ValueError('point provenance mismatch')
                def hits(dets,xy):return [i for i,d in enumerate(dets) if d.mask[xy[1],xy[0]]]
                all_points=[o['point_xy'] for o in ref['objects']]+ref['robot_points_xy']
                if any(not(0<=x<robot.shape[1] and 0<=y<robot.shape[0]) for x,y in all_points):raise ValueError('point outside image')
                points=[]
                for o in ref['objects']:
                    xy=o['point_xy'];before=hits(objects,xy);after=hits(filtered,xy)
                    points.append(dict(reference_id=o['reference_id'],point_xy=xy,robot_union_covers_point=bool(robot[xy[1],xy[0]]),
                        raw_category_hits=[objects[i].category for i in before],filtered_category_hits=[filtered[i].category for i in after],
                        correct_category_covered_before=any(objects[i].category==o['category_hypothesis'] for i in before),
                        correct_category_covered_after=any(filtered[i].category==o['category_hypothesis'] for i in after)))
                point_checks=dict(objects=points,robot_reference_count=len(ref['robot_points_xy']),
                    robot_union_covered_points=sum(bool(robot[y,x]) for x,y in ref['robot_points_xy']),
                    robot_points_in_object_masks_before=sum(bool(hits(objects,xy)) for xy in ref['robot_points_xy']),
                    robot_points_in_object_masks_after=sum(bool(hits(filtered,xy)) for xy in ref['robot_points_xy']))
            row=dict(env_step=step,robot_detection_count=len(robot_detections),object_overlaps=overlaps,
                scene_conflicts_before=mask_conflicts(objects),scene_conflicts_after=mask_conflicts(filtered),point_checks=point_checks,
                category_verified=False,identity_verified=False,planning_allowed=False,execution_allowed=False,production_compatible=False)
            results.append(row)
            (target/'diagnostic.json').write_text(json.dumps(row,indent=2)+'\n')
            files.extend([objdir/'detections.json',objdir/'detections.npz',objdir/'run_config.json'])
            print(json.dumps(dict(env_step=step,robot_detection_count=len(robot_detections),point_checks=point_checks)),flush=True)
        scored=[r['point_checks'] for r in results if r['point_checks'] is not None]
        summary=dict(frame_count=len(results),frames_with_robot_detection=sum(r['robot_detection_count']>0 for r in results),
            scene_conflict_frames_before=sum(bool(r['scene_conflicts_before']) for r in results),scene_conflict_frames_after=sum(bool(r['scene_conflicts_after']) for r in results),
            annotated_frames=len(scored),object_reference_points=sum(len(r['objects']) for r in scored),robot_reference_points=sum(r['robot_reference_count'] for r in scored),
            robot_union_covered_points=sum(r['robot_union_covered_points'] for r in scored),
            object_reference_points_erased=sum(o['robot_union_covers_point'] for r in scored for o in r['objects']),
            correct_object_points_before=sum(o['correct_category_covered_before'] for r in scored for o in r['objects']),
            correct_object_points_after=sum(o['correct_category_covered_after'] for r in scored for o in r['objects']),
            residual_robot_reference_points_before=sum(r['robot_points_in_object_masks_before'] for r in scored),
            residual_robot_reference_points_after=sum(r['robot_points_in_object_masks_after'] for r in scored))
        sources=[Path(__file__),Path('experiments/robot/libero/skill_pipeline/grounded_sam2_backend.py')]
        report=dict(scope='offline_wrist_rgb_gripper_overlap_and_subtraction',configuration=config,detector_id=identity,episode_id=prior['episode_id'],summary=summary,results=results,
            annotation_status=references['review_status'],point_inputs_used_by_model=False,production_compatible=False,identity_fused=False,
            diagnostic_environment_actions=0,diagnostic_policy_inferences=0,blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n');print(json.dumps(summary))


if __name__=='__main__':main()
