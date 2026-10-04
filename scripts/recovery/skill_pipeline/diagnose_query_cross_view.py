"""Project query raw masks into the synchronized saved wrist RGB-D sequence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', required=True, type=Path)
    p.add_argument('--out-dir', required=True, type=Path)
    args = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene import mask_conflicts
        from experiments.robot.libero.skill_pipeline.cross_view_pixel_evidence import project_pixel_evidence, STATUS
        episode_path = args.input_dir / 'episode.json'
        trace_path = args.input_dir / 'visual_query_trace.jsonl'
        episode = json.loads(episode_path.read_text())
        trace = [json.loads(line) for line in trace_path.read_text().splitlines() if line.strip()]
        if len(trace) != episode['queries'] or not trace:
            raise ValueError('completed nonempty episode required')
        args.out_dir.mkdir(parents=True, exist_ok=False)
        files = [episode_path, trace_path]
        results = []
        config_digest = None
        for row in trace:
            step = row['env_step']
            directory = args.input_dir / 'frames' / f'step{step:06d}'
            source = load_observation(directory / 'observation')
            wrist = load_observation(directory / 'robot0_eye_in_hand')
            if (source.env_step != step or source.episode_id != episode['episode_id']
                    or not row['synchronized_query_wrist_saved'] or source.camera_id != 'agentview'
                    or wrist.camera_id != 'robot0_eye_in_hand'):
                raise ValueError('query source mismatch')
            detector_id, detections = load_detections(source, directory / 'detector')
            configuration = json.loads((directory / 'detector/run_config.json').read_text())
            digest = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
            if (detector_id != 'grounded-sam2-' + digest[:12] or detector_id != row['artifact_detector_id']
                    or config_digest is not None and config_digest != digest):
                raise ValueError('detector configuration mismatch')
            config_digest = digest
            for camera in ('observation', 'robot0_eye_in_hand'):
                files.extend([directory / camera / 'rgbd.npz', directory / camera / 'metadata.json'])
            files.extend([directory / 'detector/detections.npz', directory / 'detector/detections.json', directory / 'detector/run_config.json'])
            union = np.logical_or.reduce([d.mask for d in detections]) if detections else np.zeros(source.depth_m.shape, dtype=bool)
            conflict = np.zeros_like(union)
            for i, first in enumerate(detections):
                for second in detections[i+1:]:
                    if first.category != second.category:
                        conflict |= first.mask & second.mask
            regions = [(f'detection_{i}', d.mask, d.category) for i, d in enumerate(detections)]
            regions += [('raw_union', union, None), ('cross_category_overlap', conflict, None)]
            for tolerance in [.002, .005, .010]:
                # A frame without detections still validates synchronization via a full-image probe,
                # but its reported regions remain empty and cannot create object evidence.
                probe_mask = union if union.any() else np.ones_like(union)
                evidence = project_pixel_evidence(source, probe_mask, wrist, tolerance)
                target = args.out_dir / f'step{step:06d}' / f'tolerance{int(tolerance*1000):03d}'
                target.mkdir(parents=True)
                np.savez_compressed(target / 'pixel_evidence.npz', status=evidence['status'], destination_uv=evidence['destination_uv'], delta_m=evidence['delta_m'], requested_raw_union=union)
                counts = [dict(region=name, category_hypothesis=category, source_mask_pixels=int(mask.sum()),
                    status_counts={name:int(np.count_nonzero(mask & (evidence['status']==code))) for code,name in STATUS.items() if code})
                    for name,mask,category in regions]
                results.append(dict(env_step=step, query_idx=row['query_idx'], visual_status=row['visual_status'],
                    depth_tolerance_m=tolerance, source_scene_conflicts=mask_conflicts(detections), regions=counts,
                    category_verified=False, identity_verified=False, planning_allowed=False, execution_allowed=False))
        sources = [Path(__file__), Path('experiments/robot/libero/skill_pipeline/cross_view_pixel_evidence.py'),
                   Path('experiments/robot/libero/skill_pipeline/visual_mask_depth_diagnostic.py')]
        report = dict(scope='synchronized_query_raw_mask_wrist_projection', episode_id=episode['episode_id'],
            query_count=len(trace), projection_direction='agentview_to_robot0_eye_in_hand', tolerances_m=[.002,.005,.010],
            results=results, semantics='geometric_source_samples_not_robot_or_object_identity_verification',
            wrist_object_detector_run=False, identity_fused=False, production_compatible=False,
            diagnostic_policy_inferences=0, diagnostic_environment_actions=0, blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files},
            source_sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sources})
        (args.out_dir / 'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        for row in results:
            if row['depth_tolerance_m']==.005:
                print(json.dumps(dict(env_step=row['env_step'],visual_status=row['visual_status'],regions=[r for r in row['regions'] if r['region'] in ('raw_union','cross_category_overlap')])) )


if __name__ == '__main__':
    main()
