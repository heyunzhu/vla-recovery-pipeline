---
id: grasp_wine_bottle_topdown_close_guard
name: Wine bottle top-down close-height guard
kind: recovery_hint
track: fail_only
scope: grasp
priority: 59
when_to_apply: Use when recovery must pick the wine bottle before placing it in
  the bowl and cuTAMP has a feasible top-down pick.
when_not_to_apply: Do not use for bowls, plates, boxes, cream cheese, mugs, or
  rack/cabinet goals.
failure_signature:
- W1 task03 traces selected feasible `libero_topdown` Pick/Place plans for
  `wine_bottle_1_main`.
- Execution reached the planned close pose with XY error about 0.008 m, but the
  end effector stayed about 0.153 m above the bottle center. The default
  `grasp_close_max_above_m=0.12` rejected the close as
  `grasp_target_not_near_precheck`.
- W2 showed that forcing a lower body-mid bottle grasp made planning infeasible
  (`No satisfying particles`), so this hint keeps the feasible top-down sampler
  and only relaxes the close-height guard for this object/task family.
recovery_point: After a matching repair entrypoint fires, keep the default
  top-down wine-bottle grasp but allow close when the gripper is above the tall
  bottle body.
applies_to:
  all:
  - task_language_matches: put.*wine bottle.*in.*bowl|wine bottle.*in.*bowl
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: akita_black_bowl|black_bowl|bowl
recovery_hints:
  grasp_profile: libero_topdown
  target: target
  params:
    executor:
      grasp_close_max_above_m: 0.18
    source: libero_goal_task03_seed51_55_w3
evidence:
  tasks:
  - 'libero_goal_task task03: put the wine bottle in the bowl'
  episodes:
  - w1_inner_floor_seed51_ep00
  - w1_inner_floor_seed52_ep01
  - w1_inner_floor_seed53_ep02
  - w1_inner_floor_seed54_ep03
  - w1_inner_floor_seed55_ep04
---
This hint does not decide when to recover and does not alter the placement
goal. It only keeps the feasible generic top-down grasp and raises the
close-height guard for the tall bottle.
