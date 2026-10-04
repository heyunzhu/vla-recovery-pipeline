"""Replay initial task-ID memory against saved frozen detections, without actions."""
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
    p.add_argument('--detector-root', type=Path)
    p.add_argument('--out-file', type=Path, required=True)
    args = p.parse_args()
    if args.out_file.exists():
        raise FileExistsError(args.out_file)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
        from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
        from experiments.robot.libero.skill_pipeline.visual_identity_memory import VisualIdentityMemory
        root = args.input_dir.resolve()
        detector_root = (args.detector_root or args.input_dir).resolve()
        rows = [json.loads(s) for s in (root / 'visual_query_trace.jsonl').read_text().splitlines()]
        if not 1 <= len(rows) <= 100:
            raise ValueError('expected 1 to 100 recorded queries')
        first = detector_root / 'frames' / f"step{rows[0]['env_step']:06d}" / 'detector'
        config = json.loads((first / 'run_config.json').read_text())
        identity = 'grounded-sam2-' + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        files = [root / 'visual_query_trace.jsonl']
        def detector(frame):
            directory = detector_root / 'frames' / f'step{frame.env_step:06d}' / 'detector'
            if json.loads((directory / 'run_config.json').read_text()) != config or config['image_shape_hw'] != list(frame.rgb.shape[:2]):
                raise ValueError('detector config changed or mismatched image size')
            actual, detections = load_detections(frame, directory)
            if actual != identity:
                raise ValueError('detector identity mismatch')
            files.extend(directory / name for name in ('run_config.json', 'detections.json', 'detections.npz'))
            return detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id=identity, camera_id='agentview'))
        memory = VisualIdentityMemory()
        results = []
        for row in rows:
            directory = root / 'frames' / f"step{row['env_step']:06d}"
            frame = load_observation(directory / 'observation')
            language = json.loads((directory / 'summary.json').read_text())['language']
            handoff = adapter.query_state(frame, language)
            result = memory.observe(frame, handoff)
            assert result == memory.observe(frame, handoff)
            results.append(dict(env_step=frame.env_step, framewise_binding_status=handoff.status,
                framewise_binding=dataclasses.asdict(handoff.binding) if handoff.binding else None,
                identity_memory=result))
            files.extend(directory / name for name in ('summary.json', 'observation/metadata.json', 'observation/rgbd.npz'))
        report = dict(scope='offline_initial_identity_memory_diagnostic', detector_id=identity,
            status_counts=dict(Counter(row['identity_memory']['status'] for row in results)), results=results,
            policy_inferences=0, environment_actions=0, production_adapter_integrated=False,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,
            input_sha256={str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in files},
            source_sha256={str(file): hashlib.sha256(file.read_bytes()).hexdigest() for file in (
                Path(__file__), Path('experiments/robot/libero/skill_pipeline/visual_identity_memory.py'))})
        args.out_file.parent.mkdir(parents=True, exist_ok=True)
        args.out_file.write_text(json.dumps(report, indent=2, allow_nan=False) + '\n')
        print(json.dumps(report['status_counts']))


if __name__ == '__main__':
    main()
