"""Offline arm diagnostics for a saved RGB-D IK candidate."""
import argparse,hashlib,json,sys
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observation-dir',type=Path,required=True)
    p.add_argument('--planning-json',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--out-file',type=Path,required=True)
    p.add_argument('--full-arm-pixels',action='store_true')
    p.add_argument('--attribute-current-hits',action='store_true')
    p.add_argument('--gripper-arm-pairs',action='store_true')
    args=p.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    pixels_file=args.out_file.with_suffix('.pixels.npz')
    if args.full_arm_pixels and pixels_file.exists():raise FileExistsError(pixels_file)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_robot_pixels import project_static_gripper
        from experiments.robot.libero.skill_pipeline.visual_arm_path import inspect_arm_joint_trajectory
        frame=load_observation(args.observation_dir)
        planning_bytes=args.planning_json.read_bytes()
        planning=json.loads(planning_bytes.decode('utf-8'))
        if args.full_arm_pixels:
            from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
            pixels=project_static_arm_gripper(frame,args.model_dir)
        else:pixels=project_static_gripper(frame,args.model_dir)
        report=inspect_arm_joint_trajectory(frame,planning['panda_joint_trajectory_candidate'],args.model_dir,robot_pixels=pixels)
        if args.attribute_current_hits:
            from experiments.robot.libero.skill_pipeline.visual_arm_followup import attribute_current_arm_hits
            report['current_hit_attribution']=attribute_current_arm_hits(frame,args.model_dir,pixels)
        if args.gripper_arm_pairs:
            from experiments.robot.libero.skill_pipeline.visual_arm_followup import inspect_gripper_arm_pairs
            report['gripper_arm_pairs']=inspect_gripper_arm_pairs(frame,planning['panda_joint_trajectory_candidate'],args.model_dir)
            report['gripper_arm_nonattachment_pairs_checked']=True
        report['blocked_oracle_import_attempts']=guard.blocked_import_attempts
        report['planning_source_sha256']=hashlib.sha256(planning_bytes).hexdigest()
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        if args.full_arm_pixels:
            np.savez_compressed(pixels_file,mask=pixels.mask,mesh_depth_m=pixels.mesh_depth_m)
            report['robot_pixel_artifact']=dict(file=pixels_file.name,sha256=hashlib.sha256(pixels_file.read_bytes()).hexdigest())
        args.out_file.write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(json.dumps({key:value for key,value in report.items() if key not in ('samples','model_source_sha256','robot_pixel_evidence','world_from_base_candidate','current_hit_attribution','gripper_arm_pairs')},indent=2))


if __name__=='__main__':main()
