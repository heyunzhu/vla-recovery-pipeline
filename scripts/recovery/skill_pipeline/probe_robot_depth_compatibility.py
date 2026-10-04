"""Offline depth compatibility sweep; historical depth is never identity evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def depth_band(depth, valid, mask):
    if depth.shape != mask.shape or valid.shape != mask.shape or valid.dtype != np.bool_ or mask.dtype != np.bool_:
        raise ValueError('aligned boolean depth validity and mask required')
    values = depth[mask & valid & np.isfinite(depth) & (depth > 0)]
    if values.size < 20:
        raise ValueError('insufficient seed depth')
    return np.quantile(values, [0.05, 0.95]).tolist()


def compatible_depth(depth, valid, band, margin):
    if valid.shape != depth.shape or valid.dtype != np.bool_:
        raise ValueError('aligned boolean depth validity required')
    if len(band) != 2 or not np.isfinite(band).all() or band[0] > band[1] or not np.isfinite(margin) or margin < 0:
        raise ValueError('finite ordered band and nonnegative margin required')
    return valid & np.isfinite(depth) & (depth > 0) & (depth >= band[0] - margin) & (depth <= band[1] + margin)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('input-dir', 'proposal-root', 'robot-root', 'reference-manifest', 'robot-points-json', 'out-dir'):
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
        from experiments.robot.libero.skill_pipeline.visual_perception_eval import load_visual_reference, evaluate_reference_points
        from experiments.robot.libero.skill_pipeline.historical_box_proposals import HistoricalBoxProposal
        args.out_dir.mkdir(parents=True, exist_ok=False)
        manifest = json.loads(args.reference_manifest.read_text())
        robot_refs = json.loads(args.robot_points_json.read_text())
        points = {r['env_step']: r for r in robot_refs['frames']}
        robot_report_path = args.robot_root / 'report.json'
        robot_report = json.loads(robot_report_path.read_text())
        # Check saved masks against the preceding experiment's source observations.
        files = [args.reference_manifest, args.robot_points_json, robot_report_path]
        seed = None
        bands = {}
        results = []
        margins = [0.0, 0.01, 0.02, 0.04]  # Predeclared diagnostic sweep; no selected operating point.
        for entry in manifest['entries']:
            step = entry['env_step']
            source = args.input_dir / 'frames' / f'step{step:06d}' / 'observation'
            for name in ('rgbd.npz', 'metadata.json'):
                path = source / name
                if hashlib.sha256(path.read_bytes()).hexdigest() != robot_report['input_sha256'][str(path)]:
                    raise ValueError('observation differs from preceding robot experiment')
                files.append(path)
            frame = load_observation(source)
            if frame.env_step != step or frame.episode_id != manifest['source_episode'] or frame.camera_id != manifest['camera_id']:
                raise ValueError('frame differs from manifest')
            reference_path = args.reference_manifest.parent / entry['reference']
            if reference_path.resolve().parent != args.reference_manifest.parent.resolve():
                raise ValueError('reference outside manifest directory')
            reference = load_visual_reference(frame, reference_path)
            robot_ref = points[step]
            if any(robot_ref[k] != v for k, v in dict(episode_id=frame.episode_id, camera_id=frame.camera_id, rgb_sha256=rgb_sha256(frame)).items()):
                raise ValueError('robot reference differs from RGB')
            directory = args.proposal_root / f'step{step:06d}'
            meta_path = directory / 'proposal_metadata.json'
            metadata = json.loads(meta_path.read_text())
            if (metadata['schema'] != 'historical_box_proposals_v1' or metadata['production_compatible']
                    or metadata['env_step'] != step or metadata['episode_id'] != frame.episode_id
                    or metadata['camera_id'] != frame.camera_id or metadata['rgb_sha256'] != rgb_sha256(frame)):
                raise ValueError('proposal provenance mismatch')
            masks_path = directory / 'proposal_masks.npz'
            with np.load(masks_path, allow_pickle=False) as data:
                masks = data['masks']
            if masks.shape != (len(metadata['proposals']), *frame.depth_m.shape):
                raise ValueError('proposal dimensions mismatch')
            proposals = [HistoricalBoxProposal(mask, **row) for mask, row in zip(masks, metadata['proposals'])]
            if seed is None:
                seed = frame
                bands = {p.seed_detection_index: depth_band(frame.depth_m, frame.depth_valid, p.mask) for p in proposals}
            if (frame.calibration_version != seed.calibration_version or not np.array_equal(frame.K, seed.K)
                    or not np.array_equal(frame.T_world_camera, seed.T_world_camera)):
                raise ValueError('fixed camera calibration required')
            robot_path = args.robot_root / f'step{step:06d}' / 'filtered_proposal_masks.npz'
            with np.load(robot_path, allow_pickle=False) as data:
                robot = data['robot_union']
            if robot.shape != frame.depth_m.shape or robot.dtype != np.bool_:
                raise ValueError('robot mask mismatch')
            files.extend([reference_path, meta_path, masks_path, robot_path])
            rows = []
            for margin in margins:
                filtered = []
                for proposal in proposals:
                    band = bands[proposal.seed_detection_index]
                    compatible = compatible_depth(frame.depth_m, frame.depth_valid, band, margin)
                    mask = proposal.mask & (~robot | compatible)
                    if mask.any():
                        filtered.append(HistoricalBoxProposal(mask, proposal.category, proposal.seed_detection_index))
                evaluation = evaluate_reference_points(frame, filtered, reference)
                hits = [list(xy) for xy in robot_ref['robot_points_xy'] if any(p.mask[xy[1], xy[0]] for p in filtered)]
                row = dict(env_step=step, margin_m=margin, evaluation=evaluation, residual_robot_point_hits=hits,
                           strict_point_checks_passed=evaluation['passed'] and not hits)
                rows.append(row)
                target = args.out_dir / f'margin{int(margin * 1000):03d}' / f'step{step:06d}'
                target.mkdir(parents=True)
                np.savez_compressed(target / 'proposal_masks.npz', masks=np.stack([p.mask for p in filtered]) if filtered else np.empty((0, *robot.shape), dtype=bool))
                (target / 'proposal_metadata.json').write_text(json.dumps(dict(
                    scope='offline_historical_depth_compatibility', production_compatible=False,
                    category_verified=False, identity_verified=False, planning_allowed=False, execution_allowed=False,
                    seed_detection_indices=[p.seed_detection_index for p in filtered], env_step=step,
                    episode_id=frame.episode_id, camera_id=frame.camera_id, rgb_sha256=rgb_sha256(frame)), indent=2)+'\n')
            # Raw optical-Z point depths are evaluation-only diagnostics, never classifier inputs.
            point_depths = dict(objects=[dict(reference_id=o['reference_id'], point_xy=o['point_xy'],
                depth_m=float(frame.depth_m[o['point_xy'][1], o['point_xy'][0]]) if frame.depth_valid[o['point_xy'][1], o['point_xy'][0]] else None)
                for o in reference['instances']], robot=[dict(point_xy=xy, depth_m=float(frame.depth_m[xy[1], xy[0]]) if frame.depth_valid[xy[1], xy[0]] else None) for xy in robot_ref['robot_points_xy']])
            results.append(dict(env_step=step, point_depths=point_depths, sweep=rows))
        summary = []
        for margin in margins:
            rows = [row for frame in results for row in frame['sweep'] if row['margin_m'] == margin]
            summary.append(dict(margin_m=margin, exclusive_object_points=sum(r['evaluation']['exclusive_correct_point_count'] for r in rows),
                residual_robot_hit_frames=sum(bool(r['residual_robot_point_hits']) for r in rows),
                residual_robot_point_count=sum(len(r['residual_robot_point_hits']) for r in rows),
                strict_passed_frames=sum(r['strict_point_checks_passed'] for r in rows)))
        report = dict(scope='offline_historical_depth_compatibility_sweep', seed_env_step=seed.env_step,
            seed_depth_quantiles=[0.05, 0.95], seed_optical_z_bands_m=bands, margins_m=margins,
            summary=summary, results=results, annotation_status='assistant_visual_draft_requires_human_review',
            depth_semantics='historical_depth_compatibility_not_current_semantic_or_identity_evidence',
            selected_operating_point=None, production_compatible=False, policy_inferences=0, environment_actions=0,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (args.out_dir / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
        print(json.dumps(summary))


if __name__ == '__main__':
    main()
