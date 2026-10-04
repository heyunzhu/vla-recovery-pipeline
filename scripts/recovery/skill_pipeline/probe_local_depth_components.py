"""Offline depth-component anchor diagnostic on saved masks and RGB-D only."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('depth-report', 'input-dir', 'proposal-root', 'robot-root', 'reference-manifest', 'robot-points-json', 'out-dir'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        from experiments.robot.libero.skill_pipeline.local_depth_components import depth_components, classify_proposal_components
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
        from experiments.robot.libero.skill_pipeline.visual_perception_eval import load_visual_reference, evaluate_reference_points
        from experiments.robot.libero.skill_pipeline.historical_box_proposals import HistoricalBoxProposal
        preceding = json.loads(args.depth_report.read_text())
        for path, expected in preceding['input_sha256'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError('preceding experiment input hash mismatch')
        args.out_dir.mkdir(parents=True, exist_ok=False)
        manifest = json.loads(args.reference_manifest.read_text())
        robot_refs = json.loads(args.robot_points_json.read_text())
        points = {r['env_step']: r for r in robot_refs['frames']}
        thresholds = [.002, .005, .010]  # Predeclared sweep; no labels used in mask inference.
        results = []
        files = [args.depth_report, args.reference_manifest, args.robot_points_json]
        for entry in manifest['entries']:
            step = entry['env_step']
            observation = args.input_dir / 'frames' / f'step{step:06d}' / 'observation'
            directory = args.proposal_root / f'step{step:06d}'
            ref_path = args.reference_manifest.parent / entry['reference']
            if ref_path.resolve().parent != args.reference_manifest.parent.resolve():
                raise ValueError('reference outside manifest directory')
            meta_path = directory / 'proposal_metadata.json'
            masks_path = directory / 'proposal_masks.npz'
            robot_path = args.robot_root / f'step{step:06d}' / 'filtered_proposal_masks.npz'
            current_files = [observation/'rgbd.npz', observation/'metadata.json', meta_path, masks_path, robot_path, ref_path]
            for path in current_files:
                if hashlib.sha256(path.read_bytes()).hexdigest() != preceding['input_sha256'][str(path)]:
                    raise ValueError('current paths differ from preceding experiment')
            files.extend(current_files)
            frame = load_observation(observation)
            reference = load_visual_reference(frame, ref_path)
            meta = json.loads(meta_path.read_text())
            if (frame.env_step != step or frame.episode_id != manifest['source_episode'] or frame.camera_id != manifest['camera_id']
                    or meta['env_step'] != step or meta['rgb_sha256'] != rgb_sha256(frame) or meta['production_compatible']):
                raise ValueError('frame provenance mismatch')
            with np.load(masks_path, allow_pickle=False) as data:
                masks = data['masks']
            proposals = [HistoricalBoxProposal(mask, **row) for mask, row in zip(masks, meta['proposals'])]
            if masks.shape != (len(meta['proposals']), *frame.depth_m.shape):
                raise ValueError('proposal dimensions mismatch')
            with np.load(robot_path, allow_pickle=False) as data:
                robot = data['robot_union']
            if robot.dtype != np.bool_ or robot.shape != frame.depth_m.shape:
                raise ValueError('robot mask dimensions mismatch')
            all_masks = np.logical_or.reduce(masks)
            robot_ref = points[step]
            if robot_ref['rgb_sha256'] != rgb_sha256(frame):
                raise ValueError('robot points differ from RGB')
            for threshold in thresholds:
                labels = depth_components(frame.depth_m, frame.depth_valid, all_masks | robot, threshold)
                kept_masks, unknown_masks, rejected_masks, filtered = [], [], [], []
                for proposal in proposals:
                    kept, rejected, unknown = classify_proposal_components(labels, proposal.mask, robot, all_masks)
                    kept_masks.append(kept); unknown_masks.append(unknown); rejected_masks.append(rejected)
                    if kept.any():
                        filtered.append(HistoricalBoxProposal(kept, proposal.category, proposal.seed_detection_index))
                evaluation = evaluate_reference_points(frame, filtered, reference)
                robot_hits = [xy for xy in robot_ref['robot_points_xy'] if any(p.mask[xy[1], xy[0]] for p in filtered)]
                object_unknown = [o['reference_id'] for o in reference['instances'] if any(mask[o['point_xy'][1], o['point_xy'][0]] for mask in unknown_masks)]
                row = dict(env_step=step, max_neighbor_jump_m=threshold, component_count=int(labels.max()),
                    evaluation=evaluation, residual_robot_point_hits=robot_hits, object_points_unknown=object_unknown,
                    kept_pixel_count=int(np.sum(kept_masks)), unknown_pixel_count=int(np.sum(unknown_masks)),
                    robot_anchor_only_pixel_count=int(np.sum(rejected_masks)),
                    strict_point_checks_passed=evaluation['passed'] and not robot_hits)
                results.append(row)
                target = args.out_dir / f'jump{int(threshold*1000):03d}' / f'step{step:06d}'
                target.mkdir(parents=True)
                np.savez_compressed(target/'component_masks.npz', labels=labels, retained=np.stack(kept_masks), unknown=np.stack(unknown_masks), robot_anchor_only=np.stack(rejected_masks))
                (target/'metadata.json').write_text(json.dumps(dict(
                    scope='offline_local_depth_components', production_compatible=False, category_verified=False,
                    identity_verified=False, planning_allowed=False, execution_allowed=False,
                    seed_detection_indices=[p.seed_detection_index for p in proposals], rgb_sha256=rgb_sha256(frame),
                    episode_id=frame.episode_id, camera_id=frame.camera_id, env_step=step), indent=2)+'\n')
                print(json.dumps({k:row[k] for k in ('env_step','max_neighbor_jump_m','component_count','object_points_unknown','residual_robot_point_hits')}), flush=True)
        summary=[]
        for threshold in thresholds:
            rows=[r for r in results if r['max_neighbor_jump_m']==threshold]
            summary.append(dict(max_neighbor_jump_m=threshold,exclusive_object_points=sum(r['evaluation']['exclusive_correct_point_count'] for r in rows),
                object_points_unknown=sum(len(r['object_points_unknown']) for r in rows),
                residual_robot_hit_frames=sum(bool(r['residual_robot_point_hits']) for r in rows),
                strict_passed_frames=sum(r['strict_point_checks_passed'] for r in rows)))
        source=Path('experiments/robot/libero/skill_pipeline/local_depth_components.py')
        report=dict(scope='offline_local_depth_component_anchor_sweep', thresholds_m=thresholds,summary=summary,results=results,
            anchor_semantics='model_mask_exclusive_regions_are_hypotheses_not_verified_labels',
            connectivity='four_neighbor_optical_z_local_difference_transitive',selected_operating_point=None,
            annotation_status='assistant_visual_draft_requires_human_review',production_compatible=False,
            environment_actions=0,policy_inferences=0,blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
            source_sha256={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (Path(__file__),source)})
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps(summary))


if __name__ == '__main__':
    main()
