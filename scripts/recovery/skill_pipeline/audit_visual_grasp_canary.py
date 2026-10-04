"""Audit recorded canary motion and selection provenance; never infer holding."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import numpy as np


def audit(root, repository, manifest):
    sys.path.insert(0, str(repository))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
    from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
    result = json.loads((root / 'result.json').read_text())
    trace = [json.loads(line) for line in (root / 'control_trace.jsonl').read_text().splitlines()]
    assert len(trace) == result['control_actions']
    assert [r['control_step'] for r in trace] == list(range(1, len(trace) + 1))
    assert [r['env_step'] for r in trace] == list(range(11, 11 + len(trace)))
    counts = Counter(r['phase'] for r in trace)
    assert counts['pregrasp'] == result['pregrasp_actions']
    assert counts['close'] == 16 and counts['hold'] == 8
    assert sum(n for phase, n in counts.items() if phase not in ('pregrasp', 'close', 'hold')) == result['grasp_motion_actions']
    for row in trace:
        action = np.asarray(row['action'])
        assert action.shape == (7,) and np.isfinite(action).all()
        assert np.max(np.abs(action[:3])) <= .2 and np.all(action[3:6] == 0)
        expected_gripper = -1 if row['phase'] in ('pregrasp', 'rim_align', 'before_close') else 1
        assert action[6] == expected_gripper
        if row['phase'] in ('close', 'hold'):
            assert np.all(action[:6] == 0)
        if 'goal_world_m' in row:
            error = np.linalg.norm(np.asarray(row['goal_world_m']) - row['eef_after_m'])
            assert np.isclose(error, row['error_after_m'], atol=1e-12)
    assert all(p['position_reached'] and p['error_m'] <= .003 for p in result['grasp_phase_results'])
    frames = {}
    for folder in root.iterdir():
        if (folder / 'agentview/metadata.json').is_file() and (folder / 'robot0_eye_in_hand/metadata.json').is_file():
            a = load_observation(folder / 'agentview')
            w = load_observation(folder / 'robot0_eye_in_hand')
            validate_synchronized_views(a, w)
            assert a.episode_id == result['episode_id']
            frames[folder.name] = a
    for selection_name, label in (('selection', 'initial'), ('grasp_selection', 'pregrasp')):
        selection = result[selection_name]
        frame = frames[label]
        assert selection['human_reviewed'] is False
        assert selection['selection_source'] == 'assistant_explicit_visual_candidate'
        assert (selection['episode_id'], selection['env_step'], selection['rgb_sha256']) == (frame.episode_id, frame.env_step, rgb_sha256(frame))
        assert hashlib.sha256((root / selection_name / 'mask.npz').read_bytes()).hexdigest() == selection['mask_sha256']
    assert rgb_sha256(frames['final']) == result['final_rgb_sha256']
    assert frames['final'].env_step == 10 + len(trace)
    np.testing.assert_allclose(frames['final'].robot_state['robot0_eef_pos'], trace[-1]['eef_after_m'], atol=1e-12)
    for name in ('identity_verified', 'holding_verified', 'task_success_verified', 'production_recovery_integrated', 'cutamp_used', 'benchmark_terminal_used_for_control'):
        assert result[name] is False
    hashes = json.loads(manifest.read_text())
    for name, expected in hashes.items():
        assert hashlib.sha256((repository / name).read_bytes()).hexdigest() == expected, name
    delta = np.asarray(frames['after_hold'].robot_state['robot0_eef_pos']) - frames['after_close'].robot_state['robot0_eef_pos']
    paths = [root / 'result.json', root / 'control_trace.jsonl', root / 'rim_plan.json', manifest]
    return dict(scope='recorded_motion_and_provenance_audit', episode_id=result['episode_id'],
                passed=True, control_actions=len(trace), phase_action_counts=dict(counts),
                synchronized_snapshot_pairs=len(frames), source_files_verified=len(hashes),
                after_close_to_after_hold_eef_delta_m=delta.tolist(),
                holding_verified=False, task_success_verified=False,
                oracle_guard_scope='three named module import paths; not a general simulator memory audit',
                input_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', required=True, type=Path)
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    report = audit(args.dataset, Path(__file__).resolve().parents[3], args.manifest)
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
