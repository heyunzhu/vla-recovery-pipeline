# Task01 Mining Notes

Task: `libero_spatial_task` task01.

Language: Pick the akita black bowl not between the plate and the ramekin and
place it on the plate.

Target and goal from BDDL:

- Target: `akita_black_bowl_2_main`
- Goal surface: `plate_1_main`
- Goal atom: `on(akita_black_bowl_2_main, plate_1_main)`

## Baseline

Run: `baseline_seed71_73_n3_egl`

Result: 0/3 success, 0 recovery calls.

Failure signature:

- ep01 and ep02 showed sustained intent toward `akita_black_bowl_1_main`.
- ep00 had a narrower q6 wrong-object intent margin while the target bowl was
  still static.
- Late q12 forced recovery was too late once the wrong object was held.

## Forced Recovery

`forced_q12_empty_pack_seed71_73_n3` failed because two episodes had unsupported
simulator holding reconstruction after the policy already held the wrong object.

`forced_q6_empty_pack_seed71_73_n3` could find target-holding plans, but the
full on-plate plan did not have satisfying particles with all static context
enabled.

`forced_q6_static_none_seed71_n1` found a full Pick+Place executable plan when
static-context collisions were disabled. This motivated a task-local
`collision_world_profile` instead of adding grasp, grounding, geometry, or place
profiles first.

## Grasp Diagnosis

The first online pack validation (`online_task01_collision_world_v1_seed71_73_n3_max200`)
triggered correctly but returned 0/3 success. The recovery hints and capability
audit showed that `real_cutamp_ignore_objects` was passed into cuTAMP.

The earlier forced-q6 empty-pack run showed that full placement was infeasible,
but holding fallback could be feasible. Execution then failed at close/lift:
`gripper_closed_but_not_holding`, with close precheck near the rim and transient
bilateral contact followed by no contact during dwell. This points to a
task-local black-bowl grasp profile rather than more trigger tuning.

`forced_q6_grasp_collision_v1_seed71_n1_max200` used
`task01_black_bowl_inward_diagonal_rim_v1` plus the collision-world profile. It
failed before execution: both full-goal and holding fallback solves returned
`num_satisfying=0`, and cuTAMP stderr first eliminated all particles on
`robot_to_movables`.

`forced_q6_collision_only_seed71_n1_max200` still merged the v1 grasp hint
because the pack manifest default index was loaded by the mining path, but it
was informative: two solves each found 1/64 satisfying particles and produced
Pick+Place plans, then execution stalled before the close step on the second
Pick trajectory (`optimized_motion_tracking_stalled`, final position error about
1.6-1.8 cm). This suggests v1 was too deep / too near the target collision
boundary rather than purely missing a collision-world relaxation.

The active grasp hint now uses
`task01_black_bowl_stable_outer_topdown_v2`: outer-rim candidates, higher z, and
eight world top-down yaw choices while retaining a narrower bowl width than the
generic `libero_topdown` profile. After the first v2 forced-q6 replay, higher /
more outward probes removed all satisfying particles (0.88 half-extent with
about 1.5-1.9 cm local z, and 0.84 half-extent with about 1.15-1.55 cm local z).
The active v2 is therefore reverted to the only setting that produced holding
plans in this seed: 0.82 half-extent, about 0.75-1.35 cm local z. Its remaining
failure is execution-side pick reach at q6 (1.56-1.66 cm error versus a 1.5 cm
pick reach gate), so the next diagnostic is earlier forced recovery rather than
more aggressive grasp geometry.

`forced_q5_grasp_collision_v2_seed71_n1_max200` showed q5 is a better recovery
point than q6: the holding fallback found a 1/64 feasible plan, both pick
trajectories passed the reach handoff, and close precheck was near the target
with transient bilateral contact. The grasp still failed after dwell
(`gripper_closed_but_not_holding`, `object_lift_m=0`), so the active hint now
uses `task01_black_bowl_low_rim_contact_v3`: it preserves the v2 outer-rim
radius/yaw basin but lowers the local contact height to test whether the close
step stops slipping into a contact-free pose. The repair margin was also lowered
from 0.05 to 0.015 because q5 would otherwise not naturally fire despite stable
wrong-bowl intent, target static, nearest pickable already being the target, and
target future distance still above 15 cm.
