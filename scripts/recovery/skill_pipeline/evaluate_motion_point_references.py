"""Evaluate cached query-mode masks on provisional visible pixel references."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root', type=Path, required=True)
    p.add_argument('--candidate-root', type=Path, required=True)
    p.add_argument('--reference-manifest', type=Path, required=True)
    p.add_argument('--out-file', type=Path, required=True)
    args = p.parse_args()
    if args.out_file.exists():
        raise FileExistsError(args.out_file)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.visual_perception_eval import load_visual_reference, evaluate_reference_points
        manifest = json.loads(args.reference_manifest.read_text())
        if manifest.get('scope') != 'provisional_visible_pixel_points' or manifest.get('schema_version') != 1:
            raise ValueError('unsupported reference manifest')
        results, hashes, identities, configs = [], {}, {}, {}
        seen = set()
        for entry in manifest['entries']:
            step = entry['env_step']
            if step in seen:
                raise ValueError('duplicate frame in reference manifest')
            seen.add(step)
            reference_path = args.reference_manifest.parent / entry['reference']
            if reference_path.resolve().parent != args.reference_manifest.parent.resolve():
                raise ValueError('reference file must be beside manifest')
            source = args.data_root / 'frames' / f'step{step:06d}'
            frame = load_observation(source / 'observation')
            reference = load_visual_reference(frame, reference_path)
            if frame.episode_id != manifest['source_episode'] or frame.env_step != step or frame.camera_id != manifest['camera_id']:
                raise ValueError('wrong episode, camera or step')
            if reference.get('review_status') != manifest['review_status']:
                raise ValueError('reference review status differs from manifest')
            ids = [item['reference_id'] for item in reference['instances']]
            if len(ids) != len(set(ids)):
                raise ValueError('duplicate instance reference IDs')
            row = dict(env_step=step, unscored_instances=reference.get('unscored_instances', []))
            for mode, detector_dir in [('joint', source / 'detector'),
                    ('per_category', args.candidate_root / 'frames' / f'step{step:06d}' / 'detector')]:
                config = json.loads((detector_dir / 'run_config.json').read_text())
                identity, detections = load_detections(frame, detector_dir)
                expected = 'grounded-sam2-' + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
                if identity != expected or config.get('grounding_mode', 'joint') != mode:
                    raise ValueError('detector mode/configuration identity mismatch')
                if mode in identities and (identities[mode] != identity or configs[mode] != config):
                    raise ValueError('detector configuration drift')
                identities[mode], configs[mode] = identity, config
                row[mode] = evaluate_reference_points(frame, detections, reference)
                for name in ('detections.json', 'detections.npz', 'run_config.json'):
                    file = detector_dir / name
                    hashes[str(file.resolve())] = hashlib.sha256(file.read_bytes()).hexdigest()
            results.append(row)
            for file in (reference_path, source / 'observation/metadata.json', source / 'observation/rgbd.npz'):
                hashes[str(file.resolve())] = hashlib.sha256(file.read_bytes()).hexdigest()
        summary = {}
        for mode in identities:
            count = Counter()
            for row in results:
                count.update(row[mode]['status_counts'])
            summary[mode] = dict(status_counts=dict(count), scored_points=sum(row[mode]['reference_count'] for row in results),
                exclusive_correct_points=sum(row[mode]['exclusive_correct_point_count'] for row in results),
                wrong_category_points=sum(row[mode]['wrong_category_point_count'] for row in results),
                point_checks_passed_frames=sum(row[mode]['passed'] for row in results),
                mask_conflict_frames=sum(bool(row[mode]['mask_conflicts']) for row in results),
                negative_point_hits=sum(len(row[mode]['negative_point_hits']) for row in results))
        hashes[str(args.reference_manifest.resolve())] = hashlib.sha256(args.reference_manifest.read_bytes()).hexdigest()
        report = dict(scope='provisional_visible_point_diagnostics', review_status=manifest['review_status'],
            annotation_blind_to_detector=False, frame_count=len(results), detector_ids=identities,
            unscored_instance_frames=sum(len(row['unscored_instances']) for row in results),
            policy_inferences=0, environment_actions=0, blocked_oracle_import_attempts=guard.blocked_import_attempts,
            summary=summary, results=results, input_sha256=hashes)
        args.out_file.parent.mkdir(parents=True, exist_ok=True)
        args.out_file.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
