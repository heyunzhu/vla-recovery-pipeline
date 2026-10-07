"""Compare visual and collision/pad projection at recorded witness pixels."""
import argparse
import json
import sys
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--observation-dir',type=Path,required=True)
    p.add_argument('--model-dir',type=Path,required=True)
    p.add_argument('--out-dir',type=Path,required=True)
    p.add_argument('--point',type=int,nargs=2,action='append',required=True,metavar=('X','Y'))
    args=p.parse_args()
    if args.out_dir.exists():raise FileExistsError(args.out_dir)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_robot_pixels import project_static_gripper
        from experiments.robot.libero.skill_pipeline.rgbd_scene_provider import _frame_digest
        frame=load_observation(args.observation_dir)
        models={mode:project_static_gripper(frame,args.model_dir,geometry_mode=mode) for mode in ('visual','collision')}
        rows=[]
        for x,y in args.point:
            if not 0<=x<frame.rgb.shape[1] or not 0<=y<frame.rgb.shape[0]:raise ValueError('pixel outside frame')
            row=dict(pixel_xy=[x,y],observed_depth_m=float(frame.depth_m[y,x]) if frame.depth_valid[y,x] else None,models={})
            for mode,evidence in models.items():
                d=evidence.mesh_depth_m[y,x]
                lo_y,hi_y=max(0,y-2),min(frame.rgb.shape[0],y+3)
                lo_x,hi_x=max(0,x-2),min(frame.rgb.shape[1],x+3)
                patch=frame.depth_m[lo_y:hi_y,lo_x:hi_x]-evidence.mesh_depth_m[lo_y:hi_y,lo_x:hi_x]
                valid=frame.depth_valid[lo_y:hi_y,lo_x:hi_x]&np.isfinite(patch)
                row['models'][mode]=dict(model_depth_m=float(d) if np.isfinite(d) else None,
                    observed_minus_model_m=float(frame.depth_m[y,x]-d) if frame.depth_valid[y,x] and np.isfinite(d) else None,
                    matched_at_2mm=bool(evidence.mask[y,x]),patch_radius_pixels=2,patch_valid_samples=int(valid.sum()),
                    patch_median_residual_m=float(np.median(patch[valid])) if valid.any() else None)
            rows.append(row)
        args.out_dir.mkdir(parents=True)
        np.savez_compressed(args.out_dir/'surface_projection.npz',observed_depth_m=frame.depth_m,depth_valid=frame.depth_valid,
            **{mode+'_depth_m':evidence.mesh_depth_m for mode,evidence in models.items()})
        report=dict(scope='offline_static_gripper_surface_comparison',frame_content_sha256=_frame_digest(frame).hex(),
                    models={mode:e.report for mode,e in models.items()},witnesses=rows,
                    collision_projection_used_to_remove_points=False,environment_actions=0,
                    blocked_oracle_import_attempts=guard.blocked_import_attempts,execution_allowed=False)
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        print(json.dumps(rows,indent=2))


if __name__=='__main__':main()
