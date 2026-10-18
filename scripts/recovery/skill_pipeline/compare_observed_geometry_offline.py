"""Offline comparison only: never call this from sensor geometry inference."""
import argparse
import itertools
import json
from pathlib import Path
import sys
import numpy as np
from scipy.spatial.transform import Rotation


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--geometry-dir',type=Path,required=True)
    p.add_argument('--oracle-problem',type=Path,required=True)
    p.add_argument('--sensor',type=Path,required=True)
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.visual_robot_frames import infer_world_from_base
    frame=load_observation(args.sensor)
    world_base=infer_world_from_base(frame)
    problem=json.loads(args.oracle_problem.read_text())['problem']
    target=next(o for o in problem['movables'] if o['role']=='target_movable')
    # This reference task contains one box collision part. No target asset is
    # loaded, selected or used to tune the sensor fit.
    parts=target['geometry']['metadata']['collision_parts']
    assert len(parts)==1 and parts[0]['shape']=='box'
    truth=parts[0]
    truth_r=Rotation.from_quat(np.r_[truth['quat'][1:],truth['quat'][0]]).as_matrix()
    truth_center=world_base[:3,:3]@np.array(truth['pos'])+world_base[:3,3]
    truth_r=world_base[:3,:3]@truth_r
    models={}
    for name in ['agentview_target','robot0_eye_in_hand_target','fused_target']:
        model=json.loads((args.geometry_dir/(name+'.json')).read_text())
        if 'dimensions_m' not in model:
            models[name]=dict(comparable=False,reasons=model['reasons']);continue
        obs_r=np.array(model['rotation_world_from_object'])
        angles=[]
        for perm in itertools.permutations(range(3)):
            for signs in itertools.product((-1,1),repeat=3):
                sym=np.eye(3)[:,perm]*np.array(signs)
                if np.linalg.det(sym)<0:continue
                angles.append(Rotation.from_matrix(obs_r.T@truth_r@sym).magnitude())
        models[name]=dict(comparable=True,planning_allowed=model['planning_allowed'],
            observed_sorted_dimensions_m=sorted(model['dimensions_m']),
            truth_sorted_dimensions_m=sorted(2*np.array(truth['size'])),
            sorted_dimension_error_m=(np.sort(model['dimensions_m'])-np.sort(2*np.array(truth['size']))).tolist(),
            center_error_m=float(np.linalg.norm(np.array(model['center_world_m'])-truth_center)),
            cuboid_axis_rotation_error_degrees=float(np.degrees(min(angles))),
            caveat='center error includes FK/base inference uncertainty; dimensions use collision box reference')
    surface=next(o for o in problem['surfaces'] if o['name']=='wine_rack_1_top_region')
    md=surface['geometry']['metadata']
    report=dict(purpose='offline_evaluation_only',truth_was_input_to_geometry_inference=False,
        reference=str(args.oracle_problem),models=models,
        historical_support=dict(name=surface['name'],source=surface['geometry']['source'],
            kind=surface['geometry']['kind'],planner_primitive=md['planner_primitive'],
            inner_bounds=md['inner_bounds'],place_z_offset_m=md['place_z_offset_m'],
            exclude_source_collision=md['exclude_source_collision'],allowed_contact_objects=md['allowed_contact_objects']),
        note='Historical success used a named-site region and geometry profile, not a sensor-fitted planar rack surface')
    (args.geometry_dir/'offline_truth_comparison.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report),flush=True)


if __name__=='__main__':main()
