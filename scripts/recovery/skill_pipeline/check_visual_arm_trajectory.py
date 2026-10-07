"""Offline arm diagnostics for a saved RGB-D IK candidate."""
import argparse,hashlib,json,sys
from pathlib import Path


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observation-dir',type=Path,required=True)
    p.add_argument('--planning-json',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--out-file',type=Path,required=True)
    args=p.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_robot_pixels import project_static_gripper
        from experiments.robot.libero.skill_pipeline.visual_arm_path import inspect_arm_joint_trajectory
        frame=load_observation(args.observation_dir)
        planning_bytes=args.planning_json.read_bytes()
        planning=json.loads(planning_bytes.decode('utf-8'))
        pixels=project_static_gripper(frame,args.model_dir)
        report=inspect_arm_joint_trajectory(frame,planning['panda_joint_trajectory_candidate'],args.model_dir,robot_pixels=pixels)
        report['blocked_oracle_import_attempts']=guard.blocked_import_attempts
        report['planning_source_sha256']=hashlib.sha256(planning_bytes).hexdigest()
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({key:value for key,value in report.items() if key not in ('samples','model_source_sha256')},indent=2))


if __name__=='__main__':main()
