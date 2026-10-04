"""Associate terminal raw masks across synchronized RGB-D; never repair labels."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene import mask_conflicts
        from experiments.robot.libero.skill_pipeline.cross_view_pixel_evidence import project_pixel_evidence, STATUS
        args.out_dir.mkdir(parents=True, exist_ok=False)
        cameras = ['agentview', 'robot0_eye_in_hand']
        frames, detections, configs, detector_ids, files = {}, {}, {}, {}, []
        for camera in cameras:
            observation = args.input_dir/'final_observation'/camera
            directory = args.input_dir/'final_detector'/camera
            frames[camera] = load_observation(observation)
            detector_ids[camera], detections[camera] = load_detections(frames[camera], directory)
            configs[camera] = json.loads((directory/'run_config.json').read_text())
            expected = 'grounded-sam2-' + hashlib.sha256(json.dumps(configs[camera],sort_keys=True).encode()).hexdigest()[:12]
            if detector_ids[camera] != expected:
                raise ValueError('detector configuration ID mismatch')
            files.extend([observation/'rgbd.npz', observation/'metadata.json',directory/'detections.json',directory/'detections.npz',directory/'run_config.json'])
        episode_path = args.input_dir/'episode.json'
        episode = json.loads(episode_path.read_text()); files.append(episode_path)
        if any(f.env_step != episode['final_env_step'] or f.episode_id != episode['episode_id'] for f in frames.values()):
            raise ValueError('terminal observations differ from episode')
        results = []
        for source_camera, destination_camera in [cameras, cameras[::-1]]:
            source, other = frames[source_camera], frames[destination_camera]
            raw = detections[source_camera]
            union = np.logical_or.reduce([d.mask for d in raw])
            conflict = np.zeros_like(union)
            for i, first in enumerate(raw):
                for second in raw[i+1:]:
                    if first.category != second.category:
                        conflict |= first.mask & second.mask
            regions = [(f'detection_{i}', d.mask, d.category) for i,d in enumerate(raw)]
            regions += [('raw_union',union,None), ('cross_category_overlap',conflict,None)]
            for tolerance in [.002, .005, .010]:
                evidence = project_pixel_evidence(source,union,other,tolerance)
                target = args.out_dir/f'{source_camera}_to_{destination_camera}'/f'tolerance{int(tolerance*1000):03d}'
                target.mkdir(parents=True)
                np.savez_compressed(target/'pixel_evidence.npz',status=evidence['status'],destination_uv=evidence['destination_uv'],delta_m=evidence['delta_m'])
                rows=[]
                for name,mask,category in regions:
                    counts = {label:int(np.count_nonzero(mask & (evidence['status']==code))) for code,label in STATUS.items() if code}
                    consistent = mask & (evidence['status']==5)
                    sy,sx = np.nonzero(consistent)
                    uv = evidence['destination_uv'][sy,sx]
                    memberships = np.stack([d.mask[uv[:,1],uv[:,0]] for d in detections[destination_camera]])
                    distinct_categories = sorted({d.category for d in detections[destination_camera]})
                    category_masks = [np.logical_or.reduce([memberships[i] for i,d in enumerate(detections[destination_camera]) if d.category==cat]) for cat in distinct_categories]
                    multiple_categories = np.sum(category_masks,axis=0)>1
                    rows.append(dict(region=name,source_category_hypothesis=category,source_mask_pixels=int(mask.sum()),status_counts=counts,
                        destination_raw_mask_hits=[dict(mask_index=i,category_hypothesis=d.category,consistent_source_points=int(memberships[i].sum())) for i,d in enumerate(detections[destination_camera])],
                        consistent_points_with_multiple_destination_categories=int(multiple_categories.sum()),
                        consistent_points_with_no_destination_detection=int(np.count_nonzero(~memberships.any(axis=0))),
                        identity_verified=False,category_verified=False,planning_allowed=False,execution_allowed=False))
                results.append(dict(source_camera=source_camera,destination_camera=destination_camera,depth_tolerance_m=tolerance,
                    aggregate=evidence['aggregate'],source_scene_conflicts=mask_conflicts(raw),regions=rows))
        # Only full calibrated RGB-D pairs count; policy IPC RGB alone is insufficient.
        query_pairs=[]
        for directory in sorted((args.input_dir/'frames').glob('step*')):
            wrist_depth = directory/'robot0_eye_in_hand'/'rgbd.npz'
            query_pairs.append(dict(frame_directory=directory.name,synchronized_wrist_rgbd_saved=wrist_depth.is_file()))
        sources=[Path(__file__),Path('experiments/robot/libero/skill_pipeline/cross_view_pixel_evidence.py'),Path('experiments/robot/libero/skill_pipeline/visual_mask_depth_diagnostic.py')]
        report=dict(scope='terminal_synchronized_raw_mask_projection_diagnostic',env_step=episode['final_env_step'],episode_id=episode['episode_id'],
            query_pair_inventory=query_pairs,terminal_only=True,detector_ids=detector_ids,results=results,
            projection_semantics='source_depth_samples_not_unique_destination_pixels_or_semantic_matches',
            selected_operating_point=None,identity_fused=False,production_compatible=False,
            environment_actions=0,policy_inferences=0,blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources})
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        for result in results:
            if result['depth_tolerance_m']==.005:
                print(json.dumps(result))


if __name__ == '__main__':
    main()
