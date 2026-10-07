"""Measured visible proxies in a real TAMPProblem; hidden geometry stays unknown."""
from dataclasses import dataclass
import numpy as np
from .rgbd_observation import RGBDObservation,unproject_world
from .rgbd_scene_provider import _frame_digest
from .visual_planning_input import VisualPlanningInput
from .visual_robot_frames import infer_world_from_base
from .visual_panda_ik import JOINT_LIMITS
from experiments.robot.libero.tiptop_repro.tamp_scene import TAMPObject,TAMPProblem,GroundedAtom


@dataclass(frozen=True)
class VisualTAMPAdapterResult:
    problem: TAMPProblem
    report: dict


def _rows(points):
    points=np.ascontiguousarray(points,dtype=np.float64)
    if points.ndim!=2 or points.shape[1]!=3 or not np.isfinite(points).all():raise ValueError('finite observed xyz points required')
    return points.view(np.dtype([('x','<f8'),('y','<f8'),('z','<f8')])).reshape(-1)


def voxel_boxes(points,voxel_size_m=.02,max_voxels=4000):
    points=np.asarray(points,float)
    if not np.isfinite(voxel_size_m) or not .01<=voxel_size_m<=.04:raise ValueError('bounded voxel size required')
    _rows(points)
    indices=np.unique(np.floor(points/voxel_size_m).astype(np.int64),axis=0)
    if len(indices)>max_voxels:raise ValueError('observed collision voxel budget exceeded; cannot drop obstacles')
    return (indices+.5)*voxel_size_m


def build_visual_tamp_problem(frame,evidence,*,robot_pixels=None,voxel_size_m=.02,padding_m=.003,hand_model_dir=None):
    if type(frame) is not RGBDObservation or type(evidence) is not VisualPlanningInput:raise TypeError('typed current visual evidence required')
    report=evidence.report;snapshot=f'{frame.episode_id}:step{frame.env_step}:{frame.camera_id}'
    if report.get('snapshot_id')!=snapshot or report.get('frame_content_sha256')!=_frame_digest(frame).hex():raise ValueError('visual planning snapshot mismatch')
    if report.get('robot_state')!=frame.robot_state:raise ValueError('planning proprioception changed')
    if not np.isfinite(padding_m) or not .001<=padding_m<=.01:raise ValueError('bounded proxy padding required')
    goal=report.get('desired_goal') or {}
    if goal.get('source')!='language_bound_visual_ids' or goal.get('predicate')!='on' or len(goal.get('args',[]))!=2:raise ValueError('bound visual on-goal required')
    target_id,goal_id=goal['args']
    if target_id==goal_id:raise ValueError('distinct target and goal required')
    surfaces={s['visual_id']:s for s in report['surfaces']}
    if len(surfaces)!=len(report['surfaces']):raise ValueError('duplicate visual object ID')
    if target_id not in surfaces or goal_id not in surfaces:raise ValueError('current visual target and goal geometry required')
    q=np.asarray(frame.robot_state['robot0_joint_pos'],float)
    if q.shape!=(7,) or not np.isfinite(q).all() or np.any(q<JOINT_LIMITS[:,0]) or np.any(q>JOINT_LIMITS[:,1]):raise ValueError('robot joint limits violated')
    base=infer_world_from_base(frame);base_from_world=np.linalg.inv(base)
    hand_inference=None
    if hand_model_dir is not None:
        from .visual_hand_aperture import infer_open_pad_handempty
        hand_inference=infer_open_pad_handempty(frame,hand_model_dir)
    init_atoms=[] if hand_inference is None else hand_inference['initial_atoms']
    hand_state='unknown' if not init_atoms else 'handempty_inferred_under_pad_model'
    current_points=unproject_world(frame)
    observed=np.asarray(evidence.arrays['observed_world_points'],float)
    if not np.isin(_rows(observed),_rows(current_points)).all():raise ValueError('planning points are not current depth samples')
    matched_rows=np.empty(0,dtype=_rows(current_points).dtype)
    if robot_pixels is not None:
        from .visual_path_diagnostic import inspect_pregrasp_path
        inspect_pregrasp_path(frame,dict(episode_id=frame.episode_id,env_step=frame.env_step,camera_id=frame.camera_id,
            waypoints_world_m=[frame.robot_state['robot0_eef_pos']]),robot_pixels=robot_pixels)
        matched_rows=_rows(current_points[robot_pixels.mask[frame.depth_valid]])
    observed=observed[~np.isin(_rows(observed),matched_rows)]
    def to_base(points):return points @ base_from_world[:3,:3].T+base_from_world[:3,3]
    objects=[];object_rows=[];geometry=[]
    for name,surface in surfaces.items():
        if not name.startswith('obj_') or not name[4:].isdigit():raise ValueError('visual ID namespace required')
        points=np.asarray(evidence.arrays[surface['array_key']],float)
        if len(points)!=surface['point_count'] or not np.isin(_rows(points),_rows(current_points)).all():raise ValueError('object visible points mismatch')
        points=points[~np.isin(_rows(points),matched_rows)]
        if len(points)<20:raise ValueError('insufficient observed object geometry after robot filtering')
        # A proxy origin is the observed bounding box centre, never a simulator body origin.
        local=to_base(points);lo=local.min(axis=0)-padding_m;hi=local.max(axis=0)+padding_m
        centre=(lo+hi)/2;half=(hi-lo)/2;role='movable' if name==target_id else 'surface' if name==goal_id else 'static_context'
        descriptor=dict(source='rgbd_visible_aabb_proxy',coordinate_frame='robot_base',half_extents=half.tolist(),
            observed_point_count=len(points),category=surface['category'],hidden_geometry='unknown',
            origin_semantics='observed_proxy_centre_not_body_origin',snapshot_id=snapshot)
        objects.append(TAMPObject(name=name,pos=centre.tolist(),quat=[1.,0.,0.,0.],radius=float(max(half[:2])),
            height=float(2*half[2]),role=role,half_extents=half.tolist(),geometry=descriptor))
        geometry.append(dict(visual_id=name,role=role,**descriptor));object_rows.append(_rows(points))
    # Semantic objects alone do not cover unlabelled obstacles. Preserve all other observed workspace points.
    labelled=np.concatenate(object_rows)
    residual=observed[~np.isin(_rows(observed),labelled)]
    voxel_centres=voxel_boxes(to_base(residual),voxel_size_m)
    voxel_half=voxel_size_m/2+padding_m
    statics=[obj for obj in objects if obj.role=='static_context']
    for index,centre in enumerate(voxel_centres):
        half=[voxel_half]*3
        statics.append(TAMPObject(name=f'rgbd_voxel_{index:05d}',pos=centre.tolist(),quat=[1.,0.,0.,0.],
            radius=voxel_half,height=2*voxel_half,role='static_context',half_extents=half,
            geometry=dict(source='rgbd_observed_voxel',coordinate_frame='robot_base',half_extents=half,
                hidden_geometry='unknown',snapshot_id=snapshot)))
    problem=TAMPProblem(movables=[o for o in objects if o.role=='movable'],surfaces=[o for o in objects if o.role=='surface'],
        statics=statics,goal_atoms=[GroundedAtom('on',(target_id,goal_id))],init_atoms=init_atoms,q_init=q.tolist(),
        q_init_debug=dict(rgbd_snapshot_id=snapshot,frame_content_sha256=_frame_digest(frame).hex(),
            scene_source='rgbd',coordinate_frame='robot_base',world_from_base_candidate=base.tolist(),
            world_from_base_source='static_robot_fk_and_proprio',initial_hand_state=hand_state,
            visual_hand_inference=hand_inference),
        table_geometry={'source':'not_synthesized_from_defaults'})
    return VisualTAMPAdapterResult(problem,dict(status='visual_tamp_problem_prepared',snapshot_id=snapshot,
        frame_content_sha256=_frame_digest(frame).hex(),geometry=geometry,observed_voxel_count=len(voxel_centres),
        residual_observed_point_count=len(residual),filtered_robot_point_count=int(len(evidence.arrays['observed_world_points'])-len(observed)),
        proxy_padding_m=padding_m,voxel_size_m=voxel_size_m,hidden_geometry='unknown',initial_hand_state=hand_state,
        visual_hand_inference=hand_inference,
        independent_base_calibration_verified=False,observed_world_only=True,
        solver_initial_state_ready=bool(init_atoms),execution_allowed=False,unresolved_checks=['physical_hand_state_verification','hidden_geometry',
            'grasp_and_place_candidates','full_path_collision','visual_runtime_verification']))
