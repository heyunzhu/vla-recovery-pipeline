"""Replay bounded approach alternatives on one fixed RGB-D snapshot."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
import numpy as np


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('observation-dir','planning-json','model-dir','out-dir'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    if args.out_dir.exists():raise FileExistsError(args.out_dir)
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.visual_arm_pixels import project_static_arm_gripper
        from experiments.robot.libero.skill_pipeline.visual_approach_search import compare_approaches
        frame=load_observation(args.observation_dir);source=args.planning_json.read_bytes();planning=json.loads(source)
        pixels=project_static_arm_gripper(frame,args.model_dir)
        result,artifacts=compare_approaches(frame,planning['grasp_candidate']['approach_proposal']['proposal'],args.model_dir,pixels)
        args.out_dir.mkdir(parents=True)
        for name,arrays in artifacts.items():
            path=args.out_dir/(name+'.memberships.npz');np.savez_compressed(path,**arrays)
            next(r for r in result['candidates'] if r['name']==name)['artifact']=dict(file=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        result.update(planning_source_sha256=hashlib.sha256(source).hexdigest(),robot_pixel_evidence=pixels.report,
            blocked_oracle_import_attempts=guard.blocked_import_attempts)
        (args.out_dir/'report.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(dict(ranking=result['ranking'],candidates=[dict(name=r['name'],ik_status=r['ik']['status'],score=r.get('score')) for r in result['candidates']]),indent=2))


if __name__=='__main__':main()
