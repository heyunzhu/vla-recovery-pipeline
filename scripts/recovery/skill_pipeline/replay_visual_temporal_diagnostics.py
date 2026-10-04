"""Replay temporal diagnostic logic on saved real policy-query frames."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, required=True)
    parser.add_argument("--out-file", type=Path, required=True)
    args = parser.parse_args()
    if args.out_file.exists():
        raise FileExistsError(args.out_file)
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import RGBDSceneProvider
        from experiments.robot.libero.skill_pipeline.visual_dry_run_adapter import VisualDryRunAdapter
        from experiments.robot.libero.skill_pipeline.visual_temporal_diagnostics import VisualTemporalDiagnostics
        root = args.input_dir.resolve()
        rows = [json.loads(line) for line in (root / "visual_query_trace.jsonl").read_text().splitlines()]
        if not rows:
            raise ValueError("real query trace is empty")
        first_dir = root / "frames" / f"step{rows[0]['env_step']:06d}"
        config = json.loads((first_dir / "detector/run_config.json").read_text())
        expected_id = "grounded-sam2-" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()[:12]
        calls = []
        def detector(frame):
            directory = root / "frames" / f"step{frame.env_step:06d}"
            actual_config = json.loads((directory / "detector/run_config.json").read_text())
            if actual_config != config or config.get("image_shape_hw") != list(frame.rgb.shape[:2]):
                raise ValueError("replay detector configuration changed or wrong image size")
            actual_id, detections = load_detections(frame, directory / "detector")
            if actual_id != expected_id:
                raise ValueError("replay detector identity mismatch")
            calls.append(frame.env_step)
            return detections
        adapter = VisualDryRunAdapter(RGBDSceneProvider(detector, detector_id=expected_id, camera_id="agentview"))
        temporal = VisualTemporalDiagnostics()
        results, files = [], [root / "visual_query_trace.jsonl"]
        for row in rows:
            directory = root / "frames" / f"step{row['env_step']:06d}"
            frame = load_observation(directory / "observation")
            language = json.loads((directory / "summary.json").read_text())["language"]
            handoff = adapter.query_state(frame, language)
            if (handoff.snapshot_id != row["snapshot_id"] or handoff.binding is None
                    or handoff.binding.target_id != row["visual_binding"]["target_id"]
                    or handoff.binding.goal_id != row["visual_binding"]["goal_id"]):
                raise ValueError("replayed identity/binding differs from original real query")
            result = temporal.observe(frame, handoff)
            assert result == temporal.observe(frame, handoff)
            results.append(result)
            files.extend(p for p in directory.rglob("*") if p.is_file())
        report = dict(scope="offline_temporal_replay_of_real_policy_frames", results=results,
                      detector_reads=calls, policy_inferences=0, environment_actions=0,
                      blocked_oracle_import_attempts=guard.blocked_import_attempts,
                      input_sha256={str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files})
        args.out_file.parent.mkdir(parents=True, exist_ok=True)
        args.out_file.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        print(json.dumps({"scope": report["scope"], "results": results}, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
