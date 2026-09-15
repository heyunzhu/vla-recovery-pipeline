---
id: ground_plate_stove_cook_region
name: Plate stove cook-region grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 46
when_to_apply: When the task asks to put the plate on the stove and BDDL names `flat_stove_1_cook_region`
  as the final support, but recovery has compiled the goal to the coarse `flat_stove_1_main` object.
when_not_to_apply: Do not use for bowl-on-stove, objects other than plate, non-stove goals, basket/tray/cabinet/caddy tasks,
  or when BDDL does not expose a stove cook region.
failure_signature:
- W2 validation fired the plate-stove repair trigger in all 15 episodes, so the entrypoint was not the primary blocker.
- The generated cuTAMP problems still used `on(plate_1_main, flat_stove_1_main)` while the BDDL goal atom was
  `on(plate_1_main, flat_stove_1_cook_region)`.
- Several solves had satisfying particles but failed motion planning, and many had no satisfying particles, consistent with a coarse/misbound stove support.
recovery_point: During recovery goal compilation, rewrite the plate placement target from the coarse stove body to the explicit cook-region surface.
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
recovery_hints:
  params:
    grounding_profile: plate_stove_cook_region_v1
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
This hint is intentionally narrow: it does not create a trigger and does not change the grasp profile. It only makes the symbolic goal match the BDDL cook-region target that the task actually requests.
