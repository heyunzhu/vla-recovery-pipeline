"""Offline paired comparison on saved policy frames; no simulation or actions."""
from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
from pathlib import Path
import sys


def same_binding(a, b):
    """Allow only floating roundoff across server/local NumPy implementations."""
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(same_binding(a[k], b[k]) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same_binding(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float):
        return math.isclose(a, b, rel_tol=0, abs_tol=1e-12)
    return a == b


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--grounding-model-dir', type=Path, required=True)
    p.add_argument('--sam2-model-dir', type=Path, required=True)
    p.add_argument('--candidate-prompts-json', type=Path)
    p.add_argument('--candidate-mode', choices=('joint', 'per_category'), default='per_category')
    args = p.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from run_grounded_sam2_snapshot import _verify_model_weights, GROUNDING_SHA256, SAM2_SHA256, GROUNDING_REVISION, SAM2_REVISION
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import torch
        import transformers
        from experiments.robot.libero.skill_pipeline.grounded_sam2_backend import GroundedSam2Detector
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections, save_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene import mask_conflicts
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
        from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
        from experiments.robot.libero.skill_pipeline.visual_temporal_diagnostics import VisualTemporalDiagnostics
        root = args.input_dir.resolve()
        output = args.out_dir.resolve()
        output.mkdir(parents=True, exist_ok=False)
        rows = [json.loads(s) for s in (root / 'visual_query_trace.jsonl').read_text().splitlines()]
        if not 1 <= len(rows) <= 100:
            raise ValueError('expected 1 to 100 recorded queries')
        first = root / 'frames' / f"step{rows[0]['env_step']:06d}"
        baseline_config = json.loads((first / 'detector/run_config.json').read_text())
        if baseline_config.get('grounding_mode', 'joint') != 'joint':
            raise ValueError('baseline must use joint queries')
        if baseline_config['torch_version'] != torch.__version__ or baseline_config['transformers_version'] != transformers.__version__:
            raise ValueError('comparison requires matching model library versions')
        config = dict(baseline_config, device='cpu')
        candidate_key = 'prompt_candidate' if args.candidate_prompts_json else args.candidate_mode
        if args.candidate_mode == 'joint' and args.candidate_prompts_json is None:
            raise ValueError('joint candidate requires an explicit alternative prompt file')
        if args.candidate_prompts_json:
            prompts = json.loads(args.candidate_prompts_json.read_text())
            if not isinstance(prompts, dict) or set(prompts) != set(baseline_config['prompts']) or not all(isinstance(v, str) and v.strip() for v in prompts.values()):
                raise ValueError('candidate prompts must retain the same category keys')
            config['prompts'] = prompts
        if args.candidate_mode != 'joint':
            config['grounding_mode'] = args.candidate_mode
        new_id = 'grounded-sam2-' + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        old_id = 'grounded-sam2-' + hashlib.sha256(json.dumps(baseline_config, sort_keys=True).encode()).hexdigest()[:12]
        model = GroundedSam2Detector(
            grounding_model=str(_verify_model_weights(args.grounding_model_dir, GROUNDING_SHA256)),
            grounding_revision=GROUNDING_REVISION,
            sam2_model=str(_verify_model_weights(args.sam2_model_dir, SAM2_SHA256)),
            sam2_revision=SAM2_REVISION, prompts=config['prompts'],
            box_threshold=config['box_threshold'], text_threshold=config['text_threshold'],
            device='cpu', grounding_mode=args.candidate_mode)
        current = {}
        adapters = {mode: VisualDryRunAdapter(RGBDSceneProvider(
            lambda frame, mode=mode: current[mode], detector_id=identity, camera_id='agentview'))
            for mode, identity in [('joint', old_id), (candidate_key, new_id)]}
        temporal = {mode: VisualTemporalDiagnostics() for mode in adapters}
        results, hashes = [], {}
        for row in rows:
            directory = root / 'frames' / f"step{row['env_step']:06d}"
            frame = load_observation(directory / 'observation')
            if json.loads((directory / 'detector/run_config.json').read_text()) != baseline_config or list(frame.rgb.shape[:2]) != config['image_shape_hw']:
                raise ValueError('baseline configuration changed')
            identity, current['joint'] = load_detections(frame, directory / 'detector')
            if identity != old_id:
                raise ValueError('baseline artifact identity mismatch')
            language = json.loads((directory / 'summary.json').read_text())['language']
            current[candidate_key] = model(frame)
            target = output / 'frames' / f"step{frame.env_step:06d}" / 'detector'
            target.mkdir(parents=True)
            (target / 'run_config.json').write_text(json.dumps(config, indent=2) + '\n')
            (target / 'grounding_boxes.json').write_text(json.dumps(model.last_grounding_boxes, indent=2) + '\n')
            save_detections(frame, current[candidate_key], target, detector_id=new_id)
            comparison = dict(env_step=frame.env_step, snapshot_id=row['snapshot_id'])
            for mode, adapter in adapters.items():
                handoff = adapter.query_state(frame, language)
                comparison[mode] = dict(status=handoff.status,
                    binding=dataclasses.asdict(handoff.binding) if handoff.binding else None,
                    detection_count=len(current[mode]), mask_conflicts=mask_conflicts(current[mode]),
                    temporal=temporal[mode].observe(frame, handoff), planning_allowed=handoff.planning_allowed)
            if comparison['joint']['status'] != row['visual_status'] or not same_binding(comparison['joint']['binding'], row['visual_binding']):
                raise ValueError('baseline replay differs from online binding')
            results.append(comparison)
            for f in directory.rglob('*'):
                if f.is_file():
                    hashes[str(f.relative_to(root))] = hashlib.sha256(f.read_bytes()).hexdigest()
            print(json.dumps({k: comparison[k] if k == 'env_step' else comparison[k]['status'] for k in ('env_step', 'joint', candidate_key)}), flush=True)
        if args.candidate_prompts_json:
            hashes[str(args.candidate_prompts_json.resolve())] = hashlib.sha256(args.candidate_prompts_json.read_bytes()).hexdigest()
        report = dict(scope='offline_query_mode_comparison', candidate_key=candidate_key, policy_inferences=0, environment_actions=0,
            blocked_oracle_import_attempts=guard.blocked_import_attempts, baseline_detector_id=old_id,
            candidate_detector_id=new_id, results=results, input_sha256=hashes,
            source_sha256={str(f): hashlib.sha256(f.read_bytes()).hexdigest() for f in (
                Path(__file__), Path('experiments/robot/libero/skill_pipeline/grounded_sam2_backend.py'))})
        (output / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')


if __name__ == '__main__':
    main()
