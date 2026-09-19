---
id: wine_rack_top_surface_geometry
name: Wine rack top virtual surface geometry
kind: recovery_hint
track: fail_only
scope: geometry
priority: 67
when_to_apply: When a wine-bottle-on-rack recovery needs to plan placement on `wine_rack_1_top_region`,
  which appears in BDDL but is not a normal scene object.
when_not_to_apply: Do not use for cabinet-top, bowl, basket, tray, caddy, shelf, or
  table-side placement goals.
failure_signature:
- Task10 W1 rule traces showed the BDDL surface `wine_rack_1_top_region`, but the
  full BDDL placement goal was absent from `recovery_goals`.
- The planner therefore attempted `wine_rack_1_main` placement or holding-only fallback,
  neither of which solved the rack-top task.
recovery_point: During TAMP problem construction, add a thin virtual surface descriptor
  at the current `wine_rack_1_main` top so `wine_rack_1_top_region` is a usable cuTAMP
  surface with place candidates.
applies_to:
  all:
  - task_language_matches: wine bottle.*rack|rack.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: wine_rack.*top_region|rack.*top_region
recovery_hints:
  params:
    geometry_profile: wine_rack_top_surface_v1
    source: libero_goal_swap_task10_seed51_65_w2
evidence:
  tasks:
  - 'libero_goal_swap task10: put the wine bottle on the rack'
  - libero_90 task10 put the wine bottle on the rack
  episodes:
  - task10_seed51_w1_ep00
  - task10_seed52_w1_ep01
  - task10_seed53_w1_ep02
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
This hint owns only the virtual rack-top surface. It is paired with
`wine_rack_top_region_grounding` so the planner sees the same target surface that BDDL
requires.
