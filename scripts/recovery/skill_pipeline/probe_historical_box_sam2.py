"""Segment current RGB with fixed historical boxes; save offline proposals only."""
import argparse
from collections import Counter
import dataclasses
import hashlib
import json
from pathlib import Path
import sys


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, required=True)
    p.add_argument('--reference-manifest', type=Path, required=True)
    p.add_argument('--robot-points-json', type=Path, required=True)
    p.add_argument('--sam2-model-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    args = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from run_grounded_sam2_snapshot import _verify_model_weights, SAM2_SHA256, SAM2_REVISION
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        import torch
        import transformers
        from transformers import Sam2Model, Sam2Processor
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections, rgb_sha256
        from experiments.robot.libero.skill_pipeline.rgbd_scene import mask_conflicts
        from experiments.robot.libero.skill_pipeline.visual_perception_eval import load_visual_reference, evaluate_reference_points
        from experiments.robot.libero.skill_pipeline.historical_box_proposals import HistoricalBoxProposal, mask_box
        root = args.input_dir.resolve()
        output = args.out_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        manifest = json.loads(args.reference_manifest.read_text())
        entries = manifest['entries']
        if not 1 <= len(entries) <= 100 or len({e['env_step'] for e in entries}) != len(entries):
            raise ValueError('expected 1 to 100 distinct reference frames')
        rows = json.loads(args.robot_points_json.read_text())
        robot_points = {row['env_step']: row for row in rows['frames']}
        if len(robot_points) != len(rows['frames']):
            raise ValueError('duplicate robot reference frame')
        first = root / 'frames' / f"step{entries[0]['env_step']:06d}"
        seed_frame = load_observation(first / 'observation')
        config = json.loads((first / 'detector/run_config.json').read_text())
        identity, seed = load_detections(seed_frame, first / 'detector')
        expected = 'grounded-sam2-' + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        if identity != expected or mask_conflicts(seed) or not seed:
            raise ValueError('initial detector configuration or scene is invalid')
        if config['sam2_sha256'] != SAM2_SHA256 or config['sam2_revision'] != SAM2_REVISION:
            raise ValueError('SAM2 differs from seed detector')
        if config['torch_version'] != torch.__version__ or config['transformers_version'] != transformers.__version__:
            raise ValueError('library versions differ from seed detector')
        boxes = [mask_box(d.mask) for d in seed]
        model_dir = str(_verify_model_weights(args.sam2_model_dir, SAM2_SHA256))
        processor = Sam2Processor.from_pretrained(model_dir, local_files_only=True)
        model = Sam2Model.from_pretrained(model_dir, local_files_only=True, use_safetensors=True).eval()
        results, files = [], [args.reference_manifest, args.robot_points_json,
                            first / 'detector/run_config.json', first / 'detector/detections.json', first / 'detector/detections.npz']
        for entry in entries:
            step = entry['env_step']
            directory = root / 'frames' / f'step{step:06d}'
            frame = load_observation(directory / 'observation')
            ref_path = args.reference_manifest.parent / entry['reference']
            if ref_path.resolve().parent != args.reference_manifest.parent.resolve():
                raise ValueError('reference path outside manifest directory')
            reference = load_visual_reference(frame, ref_path)
            if (frame.env_step != step or frame.episode_id != seed_frame.episode_id or frame.camera_id != seed_frame.camera_id
                    or frame.calibration_version != seed_frame.calibration_version
                    or not np.array_equal(frame.K, seed_frame.K)
                    or not np.array_equal(frame.T_world_camera, seed_frame.T_world_camera)):
                raise ValueError('fixed-box probe requires same episode and fixed camera')
            negative = robot_points[step]
            if (negative['rgb_sha256'] != rgb_sha256(frame) or negative['episode_id'] != frame.episode_id
                    or negative['camera_id'] != frame.camera_id):
                raise ValueError('robot reference points do not match frame')
            inputs = processor(images=np.ascontiguousarray(frame.rgb), input_boxes=[boxes], return_tensors='pt')
            with torch.no_grad():
                prediction = model(**inputs, multimask_output=False)
            masks = np.asarray(processor.post_process_masks(prediction.pred_masks.cpu(), inputs['original_sizes'])[0])
            if masks.shape != (len(seed), 1, *frame.rgb.shape[:2]):
                raise ValueError('SAM2 mask dimensions differ from prompts')
            proposals = [HistoricalBoxProposal(np.asarray(masks[i, 0], dtype=bool), d.category, i)
                         for i, d in enumerate(seed) if np.asarray(masks[i, 0]).any()]
            evaluation = evaluate_reference_points(frame, proposals, reference)
            hits = []
            for point in negative['robot_points_xy']:
                x, y = point
                if not 0 <= x < frame.rgb.shape[1] or not 0 <= y < frame.rgb.shape[0]:
                    raise ValueError('robot point out of image')
                indices = [i for i, proposal in enumerate(proposals) if proposal.mask[y, x]]
                if indices:
                    hits.append(dict(point_xy=point, proposal_indices=indices,
                                     historical_categories=[proposals[i].category for i in indices]))
            target = output / f'step{step:06d}'
            target.mkdir()
            np.savez_compressed(target / 'proposal_masks.npz', masks=np.stack([proposal.mask for proposal in proposals])
                                if proposals else np.empty((0, *frame.rgb.shape[:2]), dtype=bool))
            metadata = dict(schema='historical_box_proposals_v1', episode_id=frame.episode_id,
                env_step=step, camera_id=frame.camera_id, rgb_sha256=rgb_sha256(frame),
                seed_snapshot_id=f'{seed_frame.episode_id}:step{seed_frame.env_step}:{seed_frame.camera_id}',
                fixed_seed_boxes=boxes, category_source='first_frame_detector_hypothesis_not_current_classification',
                proposals=[{k: v for k, v in dataclasses.asdict(proposal).items() if k != 'mask'} for proposal in proposals],
                production_compatible=False)
            (target / 'proposal_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
            results.append(dict(env_step=step, visible_point_evaluation=evaluation, robot_point_hits=hits,
                                category_verified=False, identity_verified=False, execution_allowed=False))
            files.extend([ref_path, directory / 'observation/rgbd.npz', directory / 'observation/metadata.json'])
            print(json.dumps(dict(env_step=step, exclusive_points=evaluation['exclusive_correct_point_count'],
                                  conflicts=len(evaluation['mask_conflicts']), robot_point_hits=len(hits))), flush=True)
        counts = Counter()
        for row in results:
            counts.update(row['visible_point_evaluation']['status_counts'])
        summary = dict(status_counts=dict(counts), scored_points=sum(row['visible_point_evaluation']['reference_count'] for row in results),
            exclusive_correct_points=sum(row['visible_point_evaluation']['exclusive_correct_point_count'] for row in results),
            wrong_category_points=sum(row['visible_point_evaluation']['wrong_category_point_count'] for row in results),
            mask_conflict_frames=sum(bool(row['visible_point_evaluation']['mask_conflicts']) for row in results),
            robot_hit_frames=sum(bool(row['robot_point_hits']) for row in results),
            point_checks_passed_frames=sum(row['visible_point_evaluation']['passed'] and not row['robot_point_hits'] for row in results))
        report = dict(scope='offline_fixed_historical_box_sam2_proposals', seed_detector_id=identity,
            configuration=dict(sam2_revision=SAM2_REVISION, sam2_sha256=SAM2_SHA256, device='cpu',
                torch_version=torch.__version__, transformers_version=transformers.__version__,
                boxes_policy='fixed_first_frame_mask_bbox_no_motion_prediction_no_box_update'),
            summary=summary, results=results, production_compatible=False,
            policy_inferences=0, environment_actions=0, blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
            source_sha256={str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in (
                Path(__file__), Path('experiments/robot/libero/skill_pipeline/historical_box_proposals.py'))})
        (output / 'report.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps(summary))


if __name__ == '__main__':
    main()
