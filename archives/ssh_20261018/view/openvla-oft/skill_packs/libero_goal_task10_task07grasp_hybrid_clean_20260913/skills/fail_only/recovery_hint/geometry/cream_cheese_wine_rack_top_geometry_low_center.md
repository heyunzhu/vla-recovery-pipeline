---
id: cream_cheese_wine_rack_top_geometry_low_center
name: Wine-rack top low-center placement geometry
kind: recovery_hint
track: fail_only
scope: geometry
priority: 58
when_to_apply: When task10 recovery is placing cream cheese on the BDDL wine-rack
  top site and earlier rack-top geometry produced only no-satisfying cuTAMP solves.
when_not_to_apply: Do not use for other rack relations, other target objects, or non-rack
  surfaces.
failure_signature:
- W2 validation generated the correct `place_on(cream_cheese_1_main, wine_rack_1_top_region)`
  schema and 36 cream-cheese grasp candidates.
- W2 geometry exclusion worked: both `wine_rack_1_top_region` and `wine_rack_1_main`
    were marked `excluded_target_support_surface` in backend geometry diagnostics.
- W2 still failed 0/5 with all recovery solves infeasible, repeated `robot_to_world`
  collision filtering, and final `KinematicConstraint pos_err` zero-satisfying particles.
- The serialized rack-top place candidate remained at z=0.34545 m, derived from site_z
  + default 0.12 m, while the cream-cheese single-box height is about 0.081 m.
recovery_point: After an existing repair or trigger skill has already decided to call
  recovery.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
  - bddl_goal_surface_matches: '*wine_rack*top_region'
recovery_hints:
  params:
    geometry_profile: wine_rack_top_site_descriptor_low_center_v3
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - mine_val_task10_w2_ep0
  - mine_val_task10_w2_ep2
  - mine_val_task10_w2_ep3
  - mine_val_task10_w2_ep4
  - task10_ep1_seed51
---
## Intent

This policy contributes only geometry. It keeps the dynamic MuJoCo rack-top site descriptor and source-object collision exclusion from W2, but serializes inner bounds and a lower center-height placement candidate for the rack top. It does not alter the repair trigger, grounding, grasp sampling, executor options, or online skill set.
