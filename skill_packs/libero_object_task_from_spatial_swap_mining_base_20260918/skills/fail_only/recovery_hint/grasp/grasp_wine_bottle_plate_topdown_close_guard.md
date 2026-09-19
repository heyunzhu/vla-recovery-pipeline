---
id: grasp_wine_bottle_plate_topdown_close_guard
name: Wine bottle plate top-down close-height guard
kind: recovery_hint
track: fail_only
scope: grasp
priority: 59
when_to_apply: Use when wine-bottle-to-plate recovery must pick the wine bottle
  and cuTAMP has a feasible top-down pick.
when_not_to_apply: Do not use for bowls, plates as the picked target, boxes,
  cream cheese, mugs, or rack/cabinet/bowl goals.
failure_signature:
- The forced q5 probe on task09 selected a feasible libero_topdown pick plan for
  wine_bottle_1_main (14 satisfying particles), so the sampler itself is usable.
- Task03 W1 evidence for the same fallen tall bottle showed the default
  grasp_close_max_above_m=0.12 rejecting an otherwise feasible close at about
  0.153 m above the bottle center; raising the guard to 0.18 m allowed the
  confirmed close/lift chain that now passes task03/task07 at 14/15.
recovery_point: After a matching repair entrypoint fires, keep the feasible
  top-down wine-bottle grasp and allow close when the gripper is above the tall
  bottle body.
applies_to:
  all:
  - task_language_matches: put.*wine bottle.*on.*plate|wine bottle.*on.*plate
  - target_name_matches: wine_bottle|wine bottle
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
recovery_hints:
  grasp_profile: libero_topdown
  target: target
  params:
    executor:
      grasp_close_max_above_m: 0.18
    source: libero_goal_task09_20260916_w1
evidence:
  tasks:
  - 'libero_goal_task task09: Put the wine bottle on the plate'
  - 'libero_goal_task task03/task07: put the wine bottle in the bowl (same fallen bottle geometry)'
  episodes:
  - probe_force_q5_seed51_55 ep00-ep04 (2026-09-15 reference run)
  - task03 W1/W3 close-guard history recorded in grasp_wine_bottle_topdown_close_guard
---
This hint does not decide when to recover and does not alter the placement
goal. It keeps the feasible generic top-down grasp and raises the close-height
guard for the tall bottle, mirroring the validated task03 recipe for the same
object geometry under a plate goal.