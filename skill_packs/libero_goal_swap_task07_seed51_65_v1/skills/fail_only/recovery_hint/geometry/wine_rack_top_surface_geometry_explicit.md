---
id: wine_rack_top_surface_geometry_explicit
name: Wine rack top virtual surface geometry explicit hint
kind: recovery_hint
track: fail_only
scope: geometry
priority: 69
when_to_apply: When a wine-bottle-on-rack recovery needs the BDDL surface `wine_rack_1_top_region`
  to exist as an actual cuTAMP placement surface.
when_not_to_apply: Do not use for non-rack goals, cabinet-top goals, bowls, baskets,
  trays, caddies, shelves, or table-side placement goals.
failure_signature:
- W2 grounding rewrote the recovery goal to `wine_rack_1_top_region`, but cuTAMP full-goal
  solves still failed with unknown surface literal `wine_rack_1_top_region`.
- W2 problem JSON contained `wine_rack_1_main` but did not contain the rack-top virtual
  surface, so execution fell back to holding-only Pick plans.
recovery_point: During TAMP problem construction, explicitly inject a `placement_region`
  geometry hint that builds `wine_rack_1_top_region` from the current `wine_rack_1_main`
  geometry before cuTAMP enumerates place candidates.
applies_to:
  all:
  - task_language_matches: wine bottle.*rack|rack.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: wine_rack.*top_region|rack.*top_region
recovery_hints:
  params:
    geometry_profile: wine_rack_top_surface_v1
    geometry_hints:
      placement_region:
        geometry_profile: wine_rack_top_surface_v1
        relation: 'on'
        surface_name: wine_rack_1_top_region
        source_object: wine_rack_1_main
        shape: box
        shrink_xy_m: 0.012
        top_offset_m: 0.018
        thickness_m: 0.012
        place_z_offset_m: 0.15
    source: libero_goal_swap_task10_seed51_65_w3
evidence:
  tasks:
  - 'libero_goal_swap task10: put the wine bottle on the rack'
  - libero_90 task10 put the wine bottle on the rack
  episodes:
  - task10_seed51_w2_ep00
  - task10_seed52_w2_ep01
  - task10_seed53_w2_ep02
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
This hint is intentionally narrow. It does not change the trigger, grasp profile, or
grounding rule; it only makes the rack-top surface materialize in the TAMP problem.
