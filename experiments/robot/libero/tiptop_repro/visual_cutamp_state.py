"""Explicit RGB-D facts for cuTAMP, without its default HandEmpty assumption."""
import numpy as np


def build_observed_initial_state(env,problem,name_map,cfg):
    from cutamp.tamp_domain import all_tamp_fluents
    fluents={f.name.lower():f for f in all_tamp_fluents}
    types=dict(env.type_to_objects)
    names=lambda kind:{str(getattr(obj,'name',obj)) for obj in types.get(kind,[])}
    movables=names('Movable');surfaces=names('Surface');snapshot=problem.q_init_debug.get('rgbd_snapshot_id')
    debug=dict(initial_state_source='rgbd_observed_only',default_initial_state_used=False,
        snapshot_id=snapshot,applied_fluents=[],structural_fluents=[],dropped_fluents=[])
    def refuse(reason):return frozenset(),debug,reason
    if not isinstance(snapshot,str) or not snapshot:return refuse('rgbd_initial_snapshot_missing')
    if names('Stick') or names('Button'):return refuse('unsupported_visual_articulation')
    observed=[];handempty=False
    for atom in problem.init_atoms:
        if not isinstance(atom,dict):return refuse('invalid_rgbd_initial_atom')
        source=atom.get('source');confidence=atom.get('confidence')
        if source=='rgbd_open_visible_pad_gap_inference':
            if not cfg.initial_state_allow_pad_model_inference:return refuse('visual_pad_model_inference_disabled')
            inference=problem.q_init_debug.get('visual_hand_inference') or {}
            evidence=inference.get('evidence') or {}
            digest=problem.q_init_debug.get('frame_content_sha256')
            if (not digest or atom.get('frame_content_sha256')!=digest or evidence.get('frame_content_sha256')!=digest
                    or inference.get('status')!='handempty_inferred_under_pad_model'
                    or inference.get('initial_atoms')!=[atom] or evidence.get('snapshot_id')!=snapshot
                    or evidence.get('status')!='resolved_box_observed_free' or evidence.get('gripper_measured_open') is not True):
                return refuse('visual_pad_model_evidence_mismatch')
            debug['hand_state_semantics']='planning_inference_under_explicit_pad_model_not_physical_verification'
            debug['hand_state_assumptions']=inference['assumptions']
            debug['hand_confidence_definition']=inference['confidence_definition']
        if not isinstance(source,str) or not (source=='rgbd' or source.startswith('rgbd_')) or atom.get('snapshot_id')!=snapshot:
            return refuse('rgbd_initial_atom_provenance_mismatch')
        if not isinstance(confidence,(int,float)) or not np.isfinite(confidence) or not cfg.initial_state_min_confidence<=confidence<=1:
            debug['dropped_fluents'].append(dict(atom=atom,reason='confidence_below_threshold'))
            continue
        predicate=str(atom.get('predicate','')).lower();args=atom.get('args')
        if not isinstance(args,(list,tuple)) or any(not isinstance(a,str) for a in args):return refuse('invalid_rgbd_initial_atom')
        if predicate in ('holding','holdingwithgrasp'):return refuse('visual_initial_holding_not_yet_supported')
        if predicate=='handempty' and len(args)==0:
            handempty=True;ground=fluents['handempty'].ground()
        elif predicate=='on' and len(args)==2 and args[0] in name_map and args[1] in name_map:
            mapped=tuple(name_map[a] for a in args)
            if mapped[0] not in movables or mapped[1] not in surfaces:return refuse('invalid_rgbd_on_roles')
            ground=fluents['on'].ground(*mapped)
        else:return refuse('unsupported_rgbd_initial_predicate')
        observed.append(ground);debug['applied_fluents'].append(dict(predicate=predicate,args=list(args),source=source,confidence=confidence))
    if not handempty:return refuse('visual_hand_state_unknown')
    # These are planning-domain roles/configuration tokens, not scene-state observations.
    structural=[fluents['at'].ground('q0'),fluents['canmove'].ground()]
    for name in sorted(movables):
        structural.extend((fluents['ismovable'].ground(name),fluents['hasnotpickedup'].ground(name)))
    for name in sorted(surfaces):structural.append(fluents['issurface'].ground(name))
    debug['structural_fluents']=[str(f) for f in structural]
    state=frozenset(structural+observed)
    debug['applied_initial_state']=[str(f) for f in state]
    return state,debug,None
