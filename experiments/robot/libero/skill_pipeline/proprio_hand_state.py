"""Panda hand state from measured joints, independent of image visibility."""
import numpy as np


def infer_panda_hand_state(robot_state, *, snapshot_id=None):
    q = np.asarray(robot_state.get('robot0_gripper_qpos', []), dtype=float)
    if q.shape != (2,) or not np.isfinite(q).all():
        raise ValueError('finite two-finger Panda proprioception required')
    if not (-.002 <= q[0] <= .045 and -.045 <= q[1] <= .002):
        raise ValueError('Panda signed finger positions outside calibrated range')
    opened = bool(q[0] >= .035 and q[1] <= -.035)
    assumptions = ['rigid_nonadhesive_objects', 'holding_requires_opposed_pad_pinch']
    source = 'panda_measured_open_fingers'
    atoms = [dict(predicate='handempty', args=[], source=source,
                  snapshot_id=snapshot_id, assumptions=assumptions)] if opened else []
    return dict(status='handempty_inferred_from_proprioception' if opened else 'unknown',
                reason=None if opened else 'finger_opening_does_not_resolve_holding',
                source=source, measured_finger_qpos_m=q.tolist(),
                minimum_signed_opening_m=.035, assumptions=assumptions,
                initial_atoms=atoms, holding_verified=False, release_verified=False)
