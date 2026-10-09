"""Read-only check of RGB-D hand state and depth-consistent robot pixels."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    parser.add_argument('--model-dir', type=Path, required=True)
    parser.add_argument('--out-dir', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard():
        import numpy as np
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_hand_aperture import infer_open_pad_handempty
        from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
        frame = load_observation(args.snapshot)
        hand = infer_open_pad_handempty(frame, args.model_dir)
        args.out_dir.mkdir(parents=True, exist_ok=False)
        try:
            robot = project_static_arm_gripper(frame, args.model_dir)
            robot_report = robot.report
            np.savez_compressed(args.out_dir / 'robot_pixels.npz', mask=robot.mask)
        except (ValueError, FileNotFoundError) as exc:
            robot = None
            robot_report = dict(status='unavailable', reason=f'{type(exc).__name__}: {exc}')
        (args.out_dir / 'state_diagnostic.json').write_text(json.dumps(dict(
            hand=hand, robot_pixels=robot_report, environment_actions=0, solver_called=False), indent=2))
        print(json.dumps(dict(hand_status=hand['status'], hand_reason=hand.get('reason'),
                              robot_matched_pixels=int(robot.mask.sum()) if robot else None)), flush=True)


if __name__ == '__main__':
    main()
