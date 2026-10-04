"""Independent frozen wrist RGB detection and synchronized depth association."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input-dir', 'out-dir', 'grounding-model-dir', 'sam2-model-dir'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from run_grounded_sam2_snapshot import _verify_model_weights, GROUNDING_SHA256, SAM2_SHA256, GROUNDING_REVISION, SAM2_REVISION
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        import torch
        import transformers
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections, save_detections
        from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
        from experiments.robot.libero.skill_pipeline.rgbd_scene import mask_conflicts
        from experiments.robot.libero.skill_pipeline.cross_view_pixel_evidence import project_pixel_evidence, STATUS
        from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
        root = args.input_dir.resolve()
        args.out_dir.mkdir(parents=True, exist_ok=False)
        trace_path = root / 'visual_query_trace.jsonl'
        episode_path = root / 'episode.json'
        trace = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        episode = json.loads(episode_path.read_text())
        if not 1 <= len(trace) <= 100 or len(trace) != episode['queries'] or len({r['env_step'] for r in trace}) != len(trace):
            raise ValueError('completed distinct queries required')
        first = root / 'frames' / f"step{trace[0]['env_step']:06d}" / 'detector'
        config = json.loads((first / 'run_config.json').read_text())
        if (config.get('grounding_mode','joint') != 'joint' or config['device'] != 'cpu'
                or config['torch_version'] != torch.__version__ or config['transformers_version'] != transformers.__version__
                or config['grounding_sha256'] != GROUNDING_SHA256 or config['sam2_sha256'] != SAM2_SHA256
                or config['grounding_revision'] != GROUNDING_REVISION or config['sam2_revision'] != SAM2_REVISION):
            raise ValueError('source model configuration differs from pinned CPU detector')
        identity = 'grounded-sam2-' + hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()[:12]
        detector = GroundedSam2Detector(
            grounding_model=str(_verify_model_weights(args.grounding_model_dir,GROUNDING_SHA256)), grounding_revision=GROUNDING_REVISION,
            sam2_model=str(_verify_model_weights(args.sam2_model_dir,SAM2_SHA256)), sam2_revision=SAM2_REVISION,
            prompts=config['prompts'],box_threshold=config['box_threshold'],text_threshold=config['text_threshold'],device='cpu')
        results = []
        files = [trace_path,episode_path]
        for row in trace:
            step = row['env_step']; directory = root / 'frames' / f'step{step:06d}'
            primary = load_observation(directory / 'observation')
            wrist = load_observation(directory / 'robot0_eye_in_hand')
            validate_synchronized_views(primary,wrist)
            if (primary.episode_id != episode['episode_id'] or primary.env_step != step
                    or primary.camera_id != 'agentview' or wrist.camera_id != 'robot0_eye_in_hand'
                    or not row['synchronized_query_wrist_saved'] or list(wrist.rgb.shape[:2]) != config['image_shape_hw']):
                raise ValueError('query camera provenance mismatch')
            primary_id, primary_detections = load_detections(primary,directory / 'detector')
            if (primary_id != identity or primary_id != row['artifact_detector_id']
                    or json.loads((directory/'detector/run_config.json').read_text()) != config):
                raise ValueError('primary detector configuration changed')
            detections = detector(wrist)
            target = args.out_dir / f'step{step:06d}'
            target.mkdir()
            save_detections(wrist,detections,target / 'detector',detector_id=identity)
            (target/'detector/run_config.json').write_text(json.dumps(config,indent=2)+'\n')
            (target/'detector/grounding_boxes.json').write_text(json.dumps(detector.last_grounding_boxes,indent=2)+'\n')
            conflicts = mask_conflicts(detections)
            if conflicts:
                (target/'detector/scene_refusal.json').write_text(json.dumps(dict(reason='overlapping_instance_masks',mask_conflicts=conflicts),indent=2)+'\n')
            union = np.logical_or.reduce([d.mask for d in detections]) if detections else np.zeros(wrist.depth_m.shape,dtype=bool)
            evidence = project_pixel_evidence(wrist,union if union.any() else np.ones_like(union),primary,.005)
            np.savez_compressed(target/'wrist_to_agent_projection.npz',status=evidence['status'],destination_uv=evidence['destination_uv'],delta_m=evidence['delta_m'],requested_raw_union=union)
            details=[]
            for i,detection in enumerate(detections):
                mask = detection.mask
                sy,sx = np.nonzero(mask & (evidence['status']==5))
                uv = evidence['destination_uv'][sy,sx]
                memberships = np.stack([d.mask[uv[:,1],uv[:,0]] for d in primary_detections]) if primary_detections else np.zeros((0,len(sy)),dtype=bool)
                same_category = [memberships[j] for j,d in enumerate(primary_detections) if d.category==detection.category]
                same_hits = np.logical_or.reduce(same_category) if same_category else np.zeros(len(sy),dtype=bool)
                touched = bool(mask[0].any() or mask[-1].any() or mask[:,0].any() or mask[:,-1].any())
                y,x = np.nonzero(mask)
                details.append(dict(mask_index=i,category_hypothesis=detection.category,raw_score=detection.raw_score,
                    source_mask_pixels=int(mask.sum()),mask_touches_image_boundary=touched,
                    mask_box_xyxy=[int(x.min()),int(y.min()),int(x.max())+1,int(y.max())+1],
                    status_counts={name:int(np.count_nonzero(mask & (evidence['status']==code))) for code,name in STATUS.items() if code},
                    consistent_points_in_same_primary_category=int(same_hits.sum()),
                    consistent_points_outside_all_primary_masks=int(np.count_nonzero(~memberships.any(axis=0))),
                    primary_raw_mask_hits=[dict(mask_index=j,category_hypothesis=d.category,consistent_source_points=int(memberships[j].sum())) for j,d in enumerate(primary_detections)],
                    involved_in_scene_conflict=any(i in (c['first_index'],c['second_index']) for c in conflicts),
                    category_verified=False,identity_verified=False,planning_allowed=False,execution_allowed=False))
            result=dict(env_step=step,primary_visual_status=row['visual_status'],detection_count=len(detections),
                wrist_status='scene_refused' if conflicts else 'raw_masks_candidate' if detections else 'no_detections',
                wrist_scene_conflicts=conflicts,detections=details,identity_fused=False,planning_allowed=False,execution_allowed=False)
            results.append(result)
            for camera in ('observation','robot0_eye_in_hand'):
                files.extend([directory/camera/'rgbd.npz',directory/camera/'metadata.json'])
            files.extend([directory/'detector/detections.json',directory/'detector/detections.npz',directory/'detector/run_config.json'])
            print(json.dumps(dict(env_step=step,wrist_status=result['wrist_status'],detections=[dict(category=d['category_hypothesis'],boundary=d['mask_touches_image_boundary'],consistent=d['status_counts']['depth_consistent'],outside_primary=d['consistent_points_outside_all_primary_masks']) for d in details])),flush=True)
        summary=dict(frame_count=len(results),wrist_scene_refused_frames=sum(bool(r['wrist_scene_conflicts']) for r in results),
            frames_with_bowl_candidate=sum(any(d['category_hypothesis']=='bowl' for d in r['detections']) for r in results),
            frames_with_nonconflicting_bowl_candidate=sum(any(d['category_hypothesis']=='bowl' and not d['involved_in_scene_conflict'] for d in r['detections']) for r in results),
            frames_with_boundary_touching_bowl_candidate=sum(any(d['category_hypothesis']=='bowl' and d['mask_touches_image_boundary'] for d in r['detections']) for r in results))
        sources=[Path(__file__),Path('experiments/robot/libero/skill_pipeline/grounded_sam2_backend.py'),Path('experiments/robot/libero/skill_pipeline/cross_view_pixel_evidence.py')]
        report=dict(scope='offline_independent_frozen_wrist_detection_sequence',episode_id=episode['episode_id'],detector_id=identity,
            configuration=config,summary=summary,results=results,projection_tolerance_m=.005,
            semantics='raw_wrist_category_hypotheses_and_depth_association_not_verified_target_identity',
            production_recovery_integrated=False,identity_fused=False,diagnostic_environment_actions=0,diagnostic_policy_inferences=0,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps(summary))


if __name__=='__main__':
    main()
