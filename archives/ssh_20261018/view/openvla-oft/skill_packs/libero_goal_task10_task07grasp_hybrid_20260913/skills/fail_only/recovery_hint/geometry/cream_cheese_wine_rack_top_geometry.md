---
id: cream_cheese_wine_rack_top_geometry
name: Wine-rack top site geometry
kind: recovery_hint
track: fail_only
scope: geometry
priority: 47
when_to_apply: When the task10 repair entrypoint has already decided to recover and
  the rack top site needs an executable planner surface.
when_not_to_apply: Do not use for table regions, bowl stacks, cabinet drawers, or
  any task without the named rack top site.
failure_signature:
- The forced real-cuTAMP problem contains `wine_rack_1_main` as static context but
  omits `wine_rack_1_top_region` from surfaces.
- The rack geometry metadata contains a named MuJoCo site with center, quaternion,
  and half-extents that can define a rotated-box virtual surface.
recovery_point: After a repair or trigger skill has already decided to call recovery.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
  - bddl_goal_surface_matches: '*wine_rack*top_region'
recovery_hints:
  params:
    geometry_profile: wine_rack_top_site_descriptor_v1
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - forced_q5_seed51_real
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
  - task10_ep5_seed56
  - task10_ep6_seed57
  - task10_ep7_seed58
  - task10_ep8_seed59
  - task10_ep9_seed60
  - task10_ep10_seed61
  - task10_ep11_seed62
  - task10_ep12_seed63
  - task10_ep13_seed64
  - task10_ep14_seed65
---
## Intent

This policy contributes only planner geometry. The pack-local adapter reads the
already transformed rack site from the current scene and emits a rotated-box
descriptor in planner frame; it does not hardcode episode world coordinates or
change grasp or release behavior.
