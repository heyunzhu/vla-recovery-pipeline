"""Replay synchronized dual-camera snapshots to inspect pad-gap depth coverage."""
import argparse
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--model-dir',type=Path,required=True)
    parser.add_argument('--label',action='append',required=True)
    parser.add_argument('--primary-dir',choices=('agentview','observation'),default='agentview')
    parser.add_argument('--out-file',type=Path,required=True)
    args=parser.parse_args()
    if args.out_file.exists():raise FileExistsError(args.out_file)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_hand_aperture import inspect_hand_aperture
        rows=[]
        for label in args.label:
            if Path(label).name!=label or label in ('.','..'):raise ValueError('snapshot label required')
            frames=[load_observation(args.root/label/name) for name in (args.primary_dir,'robot0_eye_in_hand')]
            a,b=frames
            if (a.episode_id!=b.episode_id or a.env_step!=b.env_step or a.timestamp_s!=b.timestamp_s
                    or a.robot_state!=b.robot_state or a.camera_id==b.camera_id):raise ValueError('synchronized distinct views required')
            rows.append(dict(label=label,episode_id=a.episode_id,env_step=a.env_step,
                views=[inspect_hand_aperture(f,args.model_dir) for f in frames]))
        result=dict(scope='observed_pad_gap_not_contact_verification',results=rows,
            environment_actions=0,blocked_oracle_import_attempts=guard.blocked_import_attempts,
            holding_verified=False,initial_atoms=[],execution_allowed=False)
        args.out_file.parent.mkdir(parents=True,exist_ok=True)
        args.out_file.write_text(json.dumps(result,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps([dict(label=r['label'],env_step=r['env_step'],views=[{k:v.get(k) for k in
            ('status','ray_count','free_ray_count','foreground_occluded_ray_count','occupied_or_boundary_ray_count','gripper_measured_open','reason')} for v in r['views']]) for r in rows],indent=2))


if __name__=='__main__':main()
