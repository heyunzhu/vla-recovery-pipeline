---
id: cabinet_top_surface_geometry_explicit
name: Cabinet top virtual surface geometry explicit hint
kind: recovery_hint
track: fail_only
scope: geometry
priority: 48
when_to_apply: When a bowl-on-cabinet-top recovery needs the BDDL surface `wooden_cabinet_1_cabinet_top`
  to exist as a concrete cuTAMP placement surface.
when_not_to_apply: Do not use for rack-top, plate, bowl, basket, tray, caddy, shelf,
  stove, or table-side placement goals.
failure_signature:
- W0 did not enter recovery, so the first likely planner blocker after adding a trigger
  is whether the cabinet-top literal is materialized as a placement surface.
- The query traces name `wooden_cabinet_1_cabinet_top` as the BDDL goal surface for
  `akita_black_bowl_1_main`.
recovery_point: During TAMP problem construction, explicitly inject a `placement_region`
  geometry hint that builds `wooden_cabinet_1_cabinet_top` from the current `wooden_cabinet_1_main`
  geometry before cuTAMP enumerates place candidates.
applies_to:
  all:
  - task_language_matches: bowl.*cabinet|cabinet.*bowl
  - target_name_matches: bowl
  - target_name_excludes: white_bowl
  - bddl_goal_surface_matches: cabinet|cabinet_top|wooden_cabinet.*cabinet_top
recovery_hints:
  params:
    geometry_hints:
      placement_region:
        relation: 'on'
        surface_name: wooden_cabinet_1_cabinet_top
        source_object: wooden_cabinet_1_main
        shape: box
        shrink_xy_m: 0.012
        top_offset_m: 0.012
        thickness_m: 0.012
        place_z_offset_m: 0.14
    source: libero_goal_swap_task05_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task05: put the bowl on top of the cabinet'
  - libero_90 task05 put the bowl on top of the cabinet
  episodes:
  - task5_ep0_seed51
  - task5_ep1_seed52
  - task5_ep2_seed53
  - task5_ep3_seed54
  - task5_ep4_seed55
  - task5_ep5_seed56
  - task5_ep6_seed57
  - task5_ep7_seed58
  - task5_ep8_seed59
  - task5_ep9_seed60
  - task5_ep10_seed61
  - task5_ep11_seed62
  - task5_ep12_seed63
  - task5_ep13_seed64
  - task5_ep14_seed65
---
This hint is intentionally narrow. It does not rewrite the BDDL goal; it only makes the cabinet-top support surface available to the planner.
