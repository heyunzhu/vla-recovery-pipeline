---
id: vla_wrong_object_pick_intent
name: VLA wrong-object pick intent
kind: repair
track: pair
hook: after_pi0_query
priority: 76
when_to_apply: When the VLA action chunk predicts a pick trajectory toward a non-target object while the parsed target remains unmanipulated.
when_not_to_apply: Do not use when the predicted trajectory is closest to the target, when the target is already manipulated, or when only object motion is observed without trajectory intent.
failure_signature:
  - Future end-effector trajectory is closer to a non-target pickable object than to the task target.
  - The non-target intent persists across queries, or the same non-target object starts moving while the target stays still.
  - The gripper aperture may be open, half-open, or blocked; closure is not required evidence.
recovery_point: Immediately after a VLA query indicates wrong-object pick intent, before the VLA commits more motion.
trigger:
  any:
    - vla_pick_target_status_is: non_target_intent
    - vla_pick_target_status_is: non_target_intent_with_motion
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task50/task53 wrong grocery-object pick attempts
  episodes:
    - online_skill_regression_tasks48_50_52_53_54_57_58_grasp_profiles_20260824 task53 ep00-ep04
---

## Intent

This repair skill catches wrong-object pick attempts from VLA trajectory intent,
not from gripper closure alone. Runner diagnostics classify a query as
`non_target_intent` only when the action chunk path is closer to a non-target
pickable object than to the parsed target for a persistent window. It upgrades
to `non_target_intent_with_motion` when that same non-target object also moves
while the target stays still.

Object response is therefore confirmatory evidence, not a standalone trigger:
accidental bumps do not fire this skill unless the action trajectory is already
pointing at the non-target object.

The skill only decides when to enter `cutamp_recover`. Grasp profiles,
grounding, and geometry remain owned by separate recovery-hint skills.
