"""Current RGB robot segmentation and offline historical-proposal subtraction."""
import argparse
import dataclasses
import hashlib
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, required=True)
    p.add_argument('--proposal-root', type=Path, required=True)
    p.add_argument('--reference-manifest', type=Path, required=True)
    p.add_argument('--robot-points-json', type=Path, required=True)
    p.add_argument('--grounding-model-dir', type=Path, required=True)
    p.add_argument('--sam2-model-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    args = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from run_grounded_sam2_snapshot import _verify_model_weights, GROUNDING_SHA256, GROUNDING_REVISION, SAM2_SHA256, SAM2_REVISION
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        import torch
        import transformers
        from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256, save_detections
        from experiments.robot.libero.skill_pipeline.visual_perception_eval import load_visual_reference, evaluate_reference_points
        from experiments.robot.libero.skill_pipeline.historical_box_proposals import HistoricalBoxProposal, subtract_robot_proposal
        output = args.out_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        manifest = json.loads(args.reference_manifest.read_text())
        entries = manifest['entries']
        if not 1 <= len(entries) <= 100 or len({entry['env_step'] for entry in entries}) != len(entries):
            raise ValueError('expected 1 to 100 distinct frames')
        refs = json.loads(args.robot_points_json.read_text())
        robot_refs = {row['env_step']: row for row in refs['frames']}
        first_dir = args.input_dir / 'frames' / f"step{entries[0]['env_step']:06d}"
        config = json.loads((first_dir / 'detector/run_config.json').read_text())
        if config['torch_version'] != torch.__version__ or config['transformers_version'] != transformers.__version__:
            raise ValueError('library versions differ from source detector')
        config.update(prompts={'robot': 'robot arm'}, prompt_source='explicit_rgb_robot_probe', task_language=None, device='cpu')
        identity = 'grounded-sam2-' + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        detector = GroundedSam2Detector(
            grounding_model=str(_verify_model_weights(args.grounding_model_dir, GROUNDING_SHA256)),
            grounding_revision=GROUNDING_REVISION,
            sam2_model=str(_verify_model_weights(args.sam2_model_dir, SAM2_SHA256)), sam2_revision=SAM2_REVISION,
            prompts=config['prompts'], box_threshold=config['box_threshold'], text_threshold=config['text_threshold'], device='cpu')
        results, files = [], [args.reference_manifest, args.robot_points_json, first_dir / 'detector/run_config.json']
        for entry in entries:
            step = entry['env_step']
            source = args.input_dir / 'frames' / f'step{step:06d}'
            frame = load_observation(source / 'observation')
            if frame.env_step != step or frame.episode_id != manifest['source_episode'] or frame.camera_id != manifest['camera_id']:
                raise ValueError('wrong proposal source frame')
            ref_path = args.reference_manifest.parent / entry['reference']
            if ref_path.resolve().parent != args.reference_manifest.parent.resolve():
                raise ValueError('reference path outside manifest directory')
            reference = load_visual_reference(frame, ref_path)
            robot_ref = robot_refs[step]
            if robot_ref['rgb_sha256'] != rgb_sha256(frame) or robot_ref['episode_id'] != frame.episode_id or robot_ref['camera_id'] != frame.camera_id:
                raise ValueError('robot points do not match current frame')
            directory = args.proposal_root / f'step{step:06d}'
            metadata = json.loads((directory / 'proposal_metadata.json').read_text())
            if (metadata['schema'] != 'historical_box_proposals_v1' or metadata['env_step'] != step
                    or metadata['episode_id'] != frame.episode_id or metadata['camera_id'] != frame.camera_id
                    or metadata['rgb_sha256'] != rgb_sha256(frame) or metadata['production_compatible']):
                raise ValueError('historical proposal provenance mismatch')
            with np.load(directory / 'proposal_masks.npz', allow_pickle=False) as data:
                masks = data['masks']
            if masks.dtype != np.bool_ or masks.shape != (len(metadata['proposals']), *frame.rgb.shape[:2]):
                raise ValueError('proposal masks differ from metadata')
            proposals = [HistoricalBoxProposal(mask, **row) for mask, row in zip(masks, metadata['proposals'])]
            robot_detections = detector(frame)
            robot_mask = np.logical_or.reduce([d.mask for d in robot_detections]) if robot_detections else np.zeros(frame.rgb.shape[:2], dtype=bool)
            filtered = subtract_robot_proposal(proposals, robot_mask)
            before = evaluate_reference_points(frame, proposals, reference)
            after = evaluate_reference_points(frame, filtered, reference)
            points = robot_ref['robot_points_xy']
            if any(not (isinstance(x, int) and isinstance(y, int) and 0 <= x < robot_mask.shape[1] and 0 <= y < robot_mask.shape[0]) for x, y in points):
                raise ValueError('robot point outside image')
            residual_hits = sum(any(proposal.mask[y, x] for proposal in filtered) for x, y in points)
            robot_covered = sum(bool(robot_mask[y, x]) for x, y in points)
            object_erased = [obj['reference_id'] for obj in reference['instances']
                             if robot_mask[obj['point_xy'][1], obj['point_xy'][0]]]
            target = output / f'step{step:06d}'
            target.mkdir()
            save_detections(frame, robot_detections, target / 'robot_detector', detector_id=identity)
            (target / 'robot_detector/run_config.json').write_text(json.dumps(config, indent=2) + '\n')
            (target / 'robot_detector/grounding_boxes.json').write_text(json.dumps(detector.last_grounding_boxes, indent=2) + '\n')
            np.savez_compressed(target / 'filtered_proposal_masks.npz', masks=np.stack([proposal.mask for proposal in filtered])
                                if filtered else np.empty((0, *frame.rgb.shape[:2]), dtype=bool), robot_union=robot_mask)
            (target / 'filtered_proposal_metadata.json').write_text(json.dumps(dict(
                scope='offline_rgb_robot_subtracted_historical_proposals', rgb_sha256=rgb_sha256(frame),
                proposals=[{k: v for k, v in dataclasses.asdict(proposal).items() if k != 'mask'} for proposal in filtered],
                production_compatible=False), indent=2) + '\n')
            row = dict(env_step=step, before=before, after=after, robot_detection_count=len(robot_detections),
                robot_reference_points=len(points), robot_covered_points=robot_covered,
                object_reference_points_erased=object_erased, residual_robot_point_hits=residual_hits,
                robot_category_verified=False, category_verified=False, identity_verified=False, execution_allowed=False,
                strict_point_checks_passed=after['passed'] and residual_hits == 0 and robot_covered == len(points) and not object_erased)
            results.append(row)
            files.extend([ref_path, directory / 'proposal_metadata.json', directory / 'proposal_masks.npz',
                          source / 'observation/rgbd.npz', source / 'observation/metadata.json'])
            print(json.dumps({k: row[k] for k in ('env_step', 'robot_detection_count', 'robot_covered_points', 'object_reference_points_erased', 'residual_robot_point_hits')}), flush=True)
        summary = dict(frame_count=len(results), scored_object_points=sum(row['after']['reference_count'] for row in results),
            exclusive_before=sum(row['before']['exclusive_correct_point_count'] for row in results),
            exclusive_after=sum(row['after']['exclusive_correct_point_count'] for row in results),
            robot_reference_points=sum(row['robot_reference_points'] for row in results),
            robot_covered_points=sum(row['robot_covered_points'] for row in results),
            erased_object_reference_points=sum(len(row['object_reference_points_erased']) for row in results),
            residual_robot_hit_frames=sum(row['residual_robot_point_hits'] > 0 for row in results),
            strict_point_checks_passed_frames=sum(row['strict_point_checks_passed'] for row in results))
        report = dict(scope='offline_rgb_robot_foreground_proposal_filter', detector_id=identity, configuration=config,
            summary=summary, results=results, production_compatible=False, policy_inferences=0, environment_actions=0,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
            source_sha256={str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in (
                Path(__file__), Path('experiments/robot/libero/skill_pipeline/historical_box_proposals.py'))})
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps(summary))


if __name__ == '__main__':
    main()
