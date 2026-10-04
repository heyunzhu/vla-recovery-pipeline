"""Audit saved synchronized query RGB-D and real policy IPC artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-dir', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    from experiments.robot.libero.skill_pipeline.visual_oracle_import_guard import OracleImportGuard
    with OracleImportGuard() as guard:
        import numpy as np
        from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation
        from experiments.robot.libero.skill_pipeline.perception_artifact import load_detections, rgb_sha256
        from experiments.robot.libero.skill_pipeline.visual_mask_depth_diagnostic import validate_synchronized_views
        episode = json.loads((args.input_dir/'episode.json').read_text())
        trace = [json.loads(line) for line in (args.input_dir/'visual_query_trace.jsonl').read_text().splitlines() if line.strip()]
        if len(trace) != episode['queries'] or not trace:
            raise ValueError('completed nonempty query trace required')
        if episode['recovery_actions'] != 0 or episode['production_recovery_integrated']:
            raise ValueError('expected visual diagnostic with no recovery execution')
        pairs=[];previous=None
        for index,row in enumerate(trace):
            step=row['env_step'];directory=args.input_dir/'frames'/f'step{step:06d}'
            primary=load_observation(directory/'observation')
            wrist=load_observation(directory/'robot0_eye_in_hand')
            validate_synchronized_views(primary,wrist)
            if (primary.env_step != step or primary.episode_id != episode['episode_id']
                    or primary.camera_id != 'agentview' or wrist.camera_id != 'robot0_eye_in_hand'
                    or row['query_idx'] != index or not row['synchronized_query_wrist_saved']):
                raise ValueError('query frame provenance mismatch')
            identity,detections=load_detections(primary,directory/'detector')
            if identity != row['artifact_detector_id'] or row['execution_readiness']['execution_allowed']:
                raise ValueError('detector identity or execution readiness mismatch')
            result=dict(env_step=step,timestamp_s=primary.timestamp_s,synchronized=True,
                agentview_rgb_sha256=rgb_sha256(primary),wrist_rgb_sha256=rgb_sha256(wrist),
                agentview_valid_depth_pixels=int(primary.depth_valid.sum()),wrist_valid_depth_pixels=int(wrist.depth_valid.sum()),
                visual_status=row['visual_status'],execution_allowed=False,recovery_decision=row['recovery_decision'])
            if previous:
                a,b=previous
                if primary.timestamp_s <= a.timestamp_s or step <= a.env_step:
                    raise ValueError('query time did not advance')
                result['changes_from_previous']=dict(
                    eef_displacement_m=float(np.linalg.norm(np.array(primary.robot_state['robot0_eef_pos'])-np.array(a.robot_state['robot0_eef_pos']))),
                    agentview_rgb_changed=not np.array_equal(primary.rgb,a.rgb),wrist_rgb_changed=not np.array_equal(wrist.rgb,b.rgb),
                    agentview_depth_changed=not np.array_equal(primary.depth_m,a.depth_m),wrist_depth_changed=not np.array_equal(wrist.depth_m,b.depth_m),
                    agentview_extrinsics_unchanged=bool(np.array_equal(primary.T_world_camera,a.T_world_camera)),
                    wrist_camera_translation_m=float(np.linalg.norm(wrist.T_world_camera[:3,3]-b.T_world_camera[:3,3])),
                    wrist_camera_rotation_matrix_delta=float(np.linalg.norm(wrist.T_world_camera[:3,:3]-b.T_world_camera[:3,:3])),
                    wrist_intrinsics_unchanged=bool(np.array_equal(wrist.K,b.K)))
            previous=(primary,wrist);pairs.append(result)
        final_primary=load_observation(args.input_dir/'final_observation/agentview')
        final_wrist=load_observation(args.input_dir/'final_observation/robot0_eye_in_hand')
        validate_synchronized_views(final_primary,final_wrist)
        if final_primary.env_step != episode['final_env_step'] or final_primary.episode_id != episode['episode_id']:
            raise ValueError('final observation provenance mismatch')
        policy=[];closed=[]
        for path in sorted((args.input_dir/'policy_ipc').glob('worker_*/request_*.json')):
            request=json.loads(path.read_text());response_path=path.with_name(path.name.replace('request_','response_'))
            response=json.loads(response_path.read_text())
            if response['status']!='ok' or response['sequence']!=request['sequence']:
                raise ValueError('policy request/response mismatch')
            if request['command']=='infer':
                with np.load(response_path.with_suffix('.npz'),allow_pickle=False) as arrays:
                    actions=arrays['actions']
                if actions.ndim!=2 or actions.shape[1]!=7 or not len(actions) or not np.isfinite(actions).all():
                    raise ValueError('invalid policy action array')
                policy.append(dict(sequence=request['sequence'],shape=list(actions.shape),all_finite=True))
            elif request['command']=='close':
                closed.append(request['sequence'])
        if len(policy)!=len(trace) or len(closed)!=1:
            raise ValueError('policy query count or close ACK mismatch')
        report=dict(scope='real_policy_synchronized_query_camera_audit',episode=episode,query_pairs=pairs,
            final_synchronized_env_step=final_primary.env_step,policy_outputs=policy,worker_close_ack_sequences=closed,
            blocked_oracle_import_attempts=guard.blocked_import_attempts,identity_fused=False,production_compatible=False,
            artifact_sha256={str(p.relative_to(args.input_dir)):hashlib.sha256(p.read_bytes()).hexdigest() for p in args.input_dir.rglob('*') if p.is_file()},
            audit_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        args.out.write_text(json.dumps(report,indent=2,allow_nan=False)+'\n')
        print(json.dumps(dict(query_pairs=len(pairs),policy_actions=episode['policy_actions'],final_step=final_primary.env_step,changes=pairs[-1].get('changes_from_previous'))))


if __name__=='__main__':
    main()
