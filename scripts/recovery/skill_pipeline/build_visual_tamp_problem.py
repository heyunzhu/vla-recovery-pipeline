"""Export a real TAMPProblem from a replayed RGB-D frame, without solving/actions."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('observation-dir','planning-dir','model-dir','out-file'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_planning_input import VisualPlanningInput
        from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
        from experiments.robot.libero.skill_pipeline.visual_tamp_adapter import build_visual_tamp_problem
        from experiments.robot.libero.tiptop_repro.real_cutamp_backend import RealCuTAMPBackendConfig
        from dataclasses import asdict
        frame=load_observation(args.observation_dir)
        planning_bytes=(args.planning_dir/'planning_input.json').read_bytes();report=json.loads(planning_bytes)
        geometry=args.planning_dir/'visible_geometry.npz'
        if hashlib.sha256(geometry.read_bytes()).hexdigest()!=report['geometry_npz_sha256']:raise ValueError('planning geometry artifact changed')
        with np.load(geometry,allow_pickle=False) as stored:arrays={k:stored[k] for k in stored.files}
        evidence=VisualPlanningInput(report,arrays);pixels=project_static_arm_gripper(frame,args.model_dir)
        built=build_visual_tamp_problem(frame,evidence,robot_pixels=pixels)
        cfg=RealCuTAMPBackendConfig(initial_state_source='rgbd_observed',apply_simulator_truth_initial_state=False,
            enable_initial_holding_prebinding=False,grasp_sampler_profile='cutamp_native',grasp_dof=6,
            curobo_plan=True,serialize_trajectories=True,accept_optimized_plan_if_motiongen_fails=False,
            project_motiongen_start_joint_limits=False,dummy_obstacle_if_empty=False)
        result=dict(report=built.report,problem=built.problem.to_dict(),config=asdict(cfg),
            planning_input_sha256=hashlib.sha256(planning_bytes).hexdigest(),robot_pixel_evidence=pixels.report,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,solver_called=False,environment_actions=0)
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps(dict(report=built.report,movable_count=len(built.problem.movables),surface_count=len(built.problem.surfaces),
            static_count=len(built.problem.statics),blocked_oracle_import_attempts=guard.blocked_import_attempts),indent=2))


if __name__=='__main__':main()
