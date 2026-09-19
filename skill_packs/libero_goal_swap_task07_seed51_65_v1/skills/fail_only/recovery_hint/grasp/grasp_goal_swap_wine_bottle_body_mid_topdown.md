---
id: grasp_goal_swap_wine_bottle_body_mid_topdown
name: Goal-swap wine bottle mid body top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 62
when_to_apply: When task03 recovery reaches the wine bottle but the higher W2 grasp
  candidates touch the bottle without reliably lifting it.
when_not_to_apply: Do not use for bowls, mugs, cream cheese, flat boxes, books, cans,
  cartons, or non-wine-bottle targets. Do not use for non-cabinet-top goals.
failure_signature:
- W3 validation improves to 8/15 but failures show the wine bottle AABB remains on
  the table after close/lift, while successful episodes lift the AABB above cabinet top.
- W3 failures often close at `z_delta_m ~= 0.166-0.181`; successful effective closes
  are more often around `0.145-0.151`.
recovery_point: During cuTAMP recovery planning, prefer mid-height bottle-body top-down
  candidates that are lower than W2's high sampler but still above the W1 infeasible low
  candidates.
applies_to:
  all:
  - task_language_matches: wine bottle.*cabinet|cabinet.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: cabinet|cabinet_top
recovery_hints:
  grasp_profile: goal_swap_wine_bottle_body_mid_topdown_v3
  target: target
  params:
    source: libero_goal_swap_task03_seed51_65_w4
evidence:
  tasks:
  - 'libero_goal_swap task03: put the wine bottle on top of the cabinet'
  episodes:
  - task3_seed54_w3_failed_not_lifted
  - task3_seed55_w3_failed_not_lifted
  - task3_seed58_w3_failed_not_lifted
  - task3_seed59_w3_failed_not_lifted
  - task3_seed60_w3_failed_not_lifted
  - task3_seed63_w3_failed_not_lifted
  - task3_seed64_w3_failed_not_lifted
---
This hint only changes the wine-bottle grasp candidate height. It intentionally leaves
W1 trigger timing and W3 close-guard repair unchanged.
