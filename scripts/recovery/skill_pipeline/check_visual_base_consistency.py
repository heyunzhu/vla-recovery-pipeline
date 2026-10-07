"""Compare static-FK base estimates across recorded observations; no simulator."""
import argparse
import json
import sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observation-dir',nargs='+',type=Path,required=True)
    p.add_argument('--out-file',type=Path,required=True)
    args=p.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import _frame_digest
        from experiments.robot.libero.skill_pipeline.visual_robot_frames import compare_base_estimates
        frames=[load_observation(path) for path in args.observation_dir]
        report=compare_base_estimates(frames)
        report['input_frame_sha256']=[_frame_digest(f).hex() for f in frames]
        report['blocked_oracle_import_attempts']=guard.blocked_import_attempts
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,indent=2))


if __name__=='__main__':main()
