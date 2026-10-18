---
id: geometry_stove_cook_region_surface
name: Stove cook-region virtual surface
kind: recovery_hint
track: fail_only
scope: geometry
priority: 45
when_to_apply: When plate-on-stove recovery targets `flat_stove_1_cook_region`, but the planner only has coarse
  stove objects and therefore cannot sample/place against the cook-region surface.
when_not_to_apply: Do not use for table-side, cabinet, basket, tray, caddy, bowl-stack, or non-stove placement targets.
failure_signature:
- W2 cuTAMP problems listed surfaces such as `flat_stove_1_main` and `flat_stove_1_burner`, but not `flat_stove_1_cook_region`.
- MuJoCo scene geometry contains a `flat_stove_1_cook_region` site with a roughly 7.5 cm half-size square footprint.
- Without a planner surface for that site, the grounding correction has no concrete placement support to sample from.
recovery_point: During TAMP scene construction, create a virtual box support using the cook-region site XY and stove top Z.
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
recovery_hints:
  params:
    geometry_profile: stove_cook_region_surface_v1
    source: libero_goal_task_task02_seed51_65_w3
evidence:
  tasks:
  - 'libero_goal_task task02: Put the plate on the stove'
  episodes:
  - task2_ep0_seed51
  - task2_ep1_seed52
  - task2_ep2_seed53
  - task2_ep3_seed54
  - task2_ep4_seed55
  - task2_ep5_seed56
  - task2_ep6_seed57
  - task2_ep7_seed58
  - task2_ep8_seed59
  - task2_ep9_seed60
  - task2_ep10_seed61
  - task2_ep11_seed62
  - task2_ep12_seed63
  - task2_ep13_seed64
  - task2_ep14_seed65
---
The adapter reads the existing MuJoCo cook-region site and returns a virtual `flat_stove_1_cook_region` surface descriptor in planner frame. This keeps the stove-specific geometry inside the skill pack rather than in the main planner.
