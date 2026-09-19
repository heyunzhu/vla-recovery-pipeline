---
id: wine_bottle_high_grasp_close_guard
name: Wine bottle high-grasp close guard
kind: recovery_hint
track: fail_only
scope: repair
priority: 66
when_to_apply: When task03 recovery uses a high body grasp for the wine bottle and
  the close precheck reports good XY alignment but `z_delta_m` is above the default
  generic close guard.
when_not_to_apply: Do not use for bowls, mugs, cream cheese, flat boxes, books, cans,
  cartons, or non-wine-bottle targets. Do not use when the goal is not a cabinet-top
  placement.
failure_signature:
- W2 validation no longer fails at cuTAMP optimization; Pick trajectories are produced.
- Close precheck repeatedly reports `grasp_target_not_near` with `xy_m <= 0.01` but
  `z_delta_m ~= 0.148-0.166`, above the default `max_above_m=0.12`.
- The high bottle-body grasp is intentional, so this is a guard compatibility issue,
  not a reason to lower the grasp point again.
recovery_point: During recovery execution, keep the existing entry lift but allow the
  close guard to accept high bottle-body top-down grasps up to 18cm above object center.
applies_to:
  all:
  - task_language_matches: wine bottle.*cabinet|cabinet.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: cabinet|cabinet_top
recovery_hints:
  params:
    repair_profile: wine_bottle_high_grasp_close_guard_v1
    source: libero_goal_swap_task03_seed51_65_w3
evidence:
  tasks:
  - 'libero_goal_swap task03: put the wine bottle on top of the cabinet'
  episodes:
  - task3_ep0_seed51_w2
  - task3_ep1_seed52_w2
  - task3_ep2_seed53_w2
  - task3_ep3_seed54_w2
  - task3_ep4_seed55_w2
---
This repair hint is deliberately narrow. It does not alter trigger timing, target grounding,
place geometry, or grasp candidates; it only raises the close-precheck vertical guard for
wine-bottle high-body recovery while preserving the existing recovery entry lift.
