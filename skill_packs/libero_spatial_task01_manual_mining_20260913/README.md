# LIBERO spatial task01 manual mining pack

Fresh task-local skill pack for `libero_spatial_task` task 1.

Task language: Pick the akita black bowl not between the plate and the ramekin and place it on the plate.

This pack intentionally starts with no online skills and no reused legacy profiles. Mining notes and learned task-local skills should be added only after evidence from task01 rollouts.

## Mined recovery

Baseline seed 71-73 failed 0/3 without recovery. The common failure was early
wrong-object intent toward `akita_black_bowl_1_main` while the BDDL target
`akita_black_bowl_2_main` stayed static.

Forced q6 recovery showed that cuTAMP could often reach a target-holding plan,
but the full `on(akita_black_bowl_2_main, plate_1_main)` plan had no satisfying
particles under the full static collision world. A static-context ablation made
a full Pick+Place plan feasible at least once, so this pack adds a task-local
early wrong-bowl repair plus a `collision_world_profile` that ignores non-goal
static context while keeping the target bowl and goal plate protected.

Follow-up forced-q6 traces showed that default `libero_topdown` could sometimes
produce a holding solve, but execution still failed at close/lift with
`gripper_closed_but_not_holding`. The pack therefore also adds a task-local
black-bowl inward diagonal rim grasp profile.
