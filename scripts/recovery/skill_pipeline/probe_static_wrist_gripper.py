"""Offline static gripper mesh projection; no simulator or object-state inputs."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

import numpy as np


def quaternion_wxyz(q):
    q = np.asarray(q, dtype=float)
    if q.shape != (4,) or not np.isfinite(q).all() or np.linalg.norm(q) < 1e-12:
        raise ValueError('invalid quaternion')
    w, x, y, z = q / np.linalg.norm(q)
    return np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
                     [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
                     [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])


def pose(element):
    if any(k in element.attrib for k in ('euler', 'axisangle', 'xyaxes', 'zaxis')):
        raise ValueError('unsupported orientation encoding')
    t = np.eye(4)
    t[:3, :3] = quaternion_wxyz([float(x) for x in element.get('quat', '1 0 0 0').split()])
    t[:3, 3] = [float(x) for x in element.get('pos', '0 0 0').split()]
    return t


def read_stl(path):
    data = path.read_bytes()
    count = int.from_bytes(data[80:84], 'little')
    if len(data) != 84 + count*50:
        raise ValueError('expected binary STL')
    dtype = np.dtype([('normal', '<f4', (3,)), ('vertices', '<f4', (3, 3)), ('attr', '<u2')])
    triangles = np.frombuffer(data, dtype=dtype, count=count, offset=84)['vertices'].astype(float)
    if not np.isfinite(triangles).all():
        raise ValueError('nonfinite mesh')
    return triangles


def raster_depth(triangles, K, shape):
    """Pixel-center sampling and perspective-correct optical-Z z-buffer."""
    depth = np.full(shape, np.inf)
    skipped = 0
    for tri in triangles:
        if np.any(tri[:, 2] <= 1e-6):
            skipped += 1  # No clipping: partial near-plane triangles are excluded.
            continue
        uv = tri @ K.T
        uv = uv[:, :2] / uv[:, 2:3]
        lo = np.maximum(np.floor(uv.min(axis=0)-.5).astype(int), 0)
        hi = np.minimum(np.ceil(uv.max(axis=0)-.5).astype(int), [shape[1]-1, shape[0]-1])
        if np.any(hi < lo):
            continue
        x, y = np.meshgrid(np.arange(lo[0], hi[0]+1)+.5, np.arange(lo[1], hi[1]+1)+.5)
        (x0,y0),(x1,y1),(x2,y2) = uv
        den = (y1-y2)*(x0-x2)+(x2-x1)*(y0-y2)
        if abs(den) < 1e-12:
            continue
        a = ((y1-y2)*(x-x2)+(x2-x1)*(y-y2))/den
        b = ((y2-y0)*(x-x2)+(x0-x2)*(y-y2))/den
        c = 1-a-b
        inside = (a >= -1e-9) & (b >= -1e-9) & (c >= -1e-9)
        inv = a/tri[0,2]+b/tri[1,2]+c/tri[2,2]
        z = np.divide(1, inv, out=np.full_like(inv,np.inf), where=inside & (inv>0))
        view = depth[lo[1]:hi[1]+1, lo[0]:hi[0]+1]
        np.minimum(view,z,out=view)
    return depth, skipped


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('input-dir','model-dir','reference-json','out-dir'):
        p.add_argument('--'+name,required=True,type=Path)
    args=p.parse_args()
    sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
    from experiments.robot.libero.skill_pipeline.perception_artifact import rgb_sha256
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    sha=lambda path:hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=json.loads((args.model_dir/'manifest.json').read_text())
    for name,expected in manifest['source_sha256'].items():
        if sha(args.model_dir/name)!=expected:raise ValueError('static source changed: '+name)
    arm=ET.parse(args.model_dir/'models/assets/robots/panda/robot.xml')
    gripper=ET.parse(args.model_dir/'models/assets/grippers/panda_gripper.xml')
    camera=arm.find('.//body[@name="right_hand"]/camera[@name="eye_in_hand"]')
    T_hand_camera=pose(camera) @ np.diag([1,-1,-1,1])
    root=gripper.find('./worldbody/body');site=gripper.find('.//body[@name="eef"]/site[@name="grip_site"]')
    T_hand_site=pose(root) @ pose(gripper.find('.//body[@name="eef"]')) @ pose(site)
    meshes={e.get('name'):read_stl(args.model_dir/'models/assets/grippers'/e.get('file')) for e in gripper.findall('./asset/mesh')}
    refs=json.loads(args.reference_json.read_text());ref_by_step={r['env_step']:r for r in refs['frames']}
    args.out_dir.mkdir(parents=True,exist_ok=False)
    results=[];input_hashes={str(args.reference_json):sha(args.reference_json)}
    with OracleImportGuard() as guard:
        for folder in sorted((args.input_dir/'frames').glob('step*')):
            obsdir=folder/'robot0_eye_in_hand';f=load_observation(obsdir)
            for name in ('metadata.json','rgbd.npz'):input_hashes[str(obsdir/name)]=sha(obsdir/name)
            q=f.robot_state['robot0_gripper_qpos']
            if len(q)!=2 or not np.isfinite(q).all():raise ValueError('invalid gripper state')
            qmap=dict(zip(('finger_joint1','finger_joint2'),q))
            triangles=[]
            def visit(body,parent):
                t=parent @ pose(body)
                for joint in body.findall('./joint'):
                    if joint.get('type')!='slide' or joint.get('name') not in qmap:raise ValueError('unsupported joint')
                    jt=np.eye(4);jt[:3,3]=np.array([float(x) for x in joint.get('axis').split()])*qmap[joint.get('name')];t=t @ jt
                for geom in body.findall('./geom'):
                    if geom.get('group')!='1' or geom.get('type')!='mesh':continue
                    gt=np.linalg.inv(T_hand_camera) @ t @ pose(geom)
                    v=meshes[geom.get('mesh')];triangles.append(v @ gt[:3,:3].T+gt[:3,3])
                for child in body.findall('./body'):visit(child,t)
            visit(root,np.eye(4))
            d,skipped=raster_depth(np.concatenate(triangles),f.K,f.depth_m.shape)
            projected=np.isfinite(d);delta=f.depth_m-d
            masks={str(mm):projected & f.depth_valid & (np.abs(delta)<=mm/1000) for mm in (2,5,10)}
            # Independent consistency check: camera mounting vs whitelisted proprioception.
            hand=f.T_world_camera @ np.linalg.inv(T_hand_camera)
            expected=(hand @ T_hand_site)[:3,3]
            xyzw=f.robot_state['robot0_eef_quat'];observed_rot=quaternion_wxyz([xyzw[3],*xyzw[:3]])
            pos_error=float(np.linalg.norm(expected-f.robot_state['robot0_eef_pos']))
            angle=float(np.arccos(np.clip((np.trace(observed_rot.T @ hand[:3,:3])-1)/2,-1,1)))
            row=dict(env_step=f.env_step,position_residual_m=pos_error,rotation_residual_deg=float(np.degrees(angle)),
                     projected_pixels=int(projected.sum()),triangles_skipped_near_plane=skipped,
                     depth_consistent_pixels={k:int(v.sum()) for k,v in masks.items()},point_checks=None,
                     planning_allowed=False,execution_allowed=False,identity_verified=False)
            if f.env_step in ref_by_step:
                ref=ref_by_step[f.env_step]
                if ref['rgb_sha256']!=rgb_sha256(f) or ref['episode_id']!=f.episode_id:raise ValueError('reference mismatch')
                def score(xy):
                    x,y=xy
                    return dict(point_xy=xy,projected=bool(projected[y,x]),observed_depth_m=float(f.depth_m[y,x]) if f.depth_valid[y,x] else None,
                                mesh_depth_m=float(d[y,x]) if projected[y,x] else None,consistent={k:bool(v[y,x]) for k,v in masks.items()})
                row['point_checks']=dict(objects=[dict(reference_id=o['reference_id'],**score(o['point_xy'])) for o in ref['objects']],robot=[score(xy) for xy in ref['robot_points_xy']])
            target=args.out_dir/f'step{f.env_step:06d}';target.mkdir()
            np.savez_compressed(target/'gripper_projection.npz',mesh_depth_m=d,projected_mask=projected,**{'consistent_'+k+'mm':v for k,v in masks.items()})
            results.append(row);print(json.dumps(row),flush=True)
        report=dict(scope='offline_wrist_static_gripper_visual_mesh_only',results=results,model_manifest=manifest,input_sha256=input_hashes,
                    source_sha256={str(Path(__file__)):sha(Path(__file__))},annotation_status=refs['review_status'],
                    arm_mesh_projected=False,point_inputs_used_for_projection=False,environment_actions=0,policy_inferences=0,
                    blocked_oracle_import_attempts=guard.blocked_import_attempts,production_compatible=False)
        (args.out_dir/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')


if __name__=='__main__':main()
