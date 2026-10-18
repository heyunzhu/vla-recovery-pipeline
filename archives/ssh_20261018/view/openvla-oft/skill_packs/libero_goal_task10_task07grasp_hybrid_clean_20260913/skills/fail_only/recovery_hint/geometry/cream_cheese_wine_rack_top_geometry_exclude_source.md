---
id: cream_cheese_wine_rack_top_geometry_exclude_source
name: Wine-rack top geometry with source collision exclusion
kind: recovery_hint
track: fail_only
scope: geometry
priority: 49
when_to_apply: When the task10 repair entrypoint has already decided to recover and
  the rack top site is the BDDL placement surface.
when_not_to_apply: Do not use for non-rack surfaces, non-cream-cheese targets, or
  broad collision removal outside the target rack support source.
failure_signature:
- W1 validation correctly grounded `on(cream_cheese_1_main, wine_rack_1_top_region)`
  and created the virtual rack top surface.
- The W1 planner problem excluded only `wine_rack_1_top_region`; `wine_rack_1_main`
  remained a static collision object.
- All W1 cuTAMP solves with recovery failed at zero satisfying particles, with repeated
  `robot_to_world` collision and final `pos_err` failures.
recovery_point: After an existing repair or trigger skill has already decided to call
  recovery.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
  - bddl_goal_surface_matches: '*wine_rack*top_region'
recovery_hints:
  params:
    geometry_profile: wine_rack_top_site_descriptor_exclude_source_v2
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - mine_val_task10_w1_fix_registry_ep0
  - mine_val_task10_w1_fix_registry_ep3
  - mine_val_task10_w1_fix_registry_ep4
  - task10_ep1_seed51
  - task10_ep2_seed51
---
## Intent

This policy contributes only geometry. It keeps the same rack-top site
descriptor as W1 and adds source-object collision exclusion for the target rack
support, matching the backend's existing `exclude_source_collision` contract.
It does not change grasp sampling, trigger timing, or place release behavior.
