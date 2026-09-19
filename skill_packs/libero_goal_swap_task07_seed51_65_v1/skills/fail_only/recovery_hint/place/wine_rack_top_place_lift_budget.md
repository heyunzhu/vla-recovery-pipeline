---
id: wine_rack_top_place_lift_budget
name: Wine rack top place lift budget
kind: recovery_hint
track: fail_only
scope: place
priority: 71
when_to_apply: When a wine-bottle-on-rack recovery has a feasible full Pick/Place
  plan to `wine_rack_1_top_region`, but the executor stops before opening because
  the held bottle is still too low over the rack.
when_not_to_apply: Do not use for cabinet-top, bowl, basket, tray, caddy, shelf, table-side,
  or non-rack placement goals.
failure_signature:
- W3 solved full cuTAMP plans containing `Place(wine_bottle_1_main, ..., wine_rack_1_top_region,
  q2)`.
- Failed episodes ep00/ep02/ep03 reached the place phase but reported `place_lift`
  error `trajectory_tracking_budget_exhausted` followed by `place_lift_too_low`.
- The default place-lift budget was 30 env steps, while the rack-top target required
  a much higher lift before the release guard would permit opening.
recovery_point: During the place executor phase, give the pre-release lift enough
  time to reach the rack-top clearance before checking the release guard.
applies_to:
  all:
  - task_language_matches: wine bottle.*rack|rack.*wine bottle
  - target_name_matches: wine_bottle|wine bottle
  - bddl_goal_surface_matches: wine_rack.*top_region|rack.*top_region
recovery_hints:
  params:
    executor:
      place_lift_max_steps: 80
      place_lift_reached_m: 0.015
    source: libero_goal_swap_task10_seed51_65_w4
evidence:
  tasks:
  - 'libero_goal_swap task10: put the wine bottle on the rack'
  - libero_90 task10 put the wine bottle on the rack
  episodes:
  - task10_seed51_w3_ep00
  - task10_seed53_w3_ep02
  - task10_seed54_w3_ep03
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
This hint only adjusts the executor budget for the rack-top release path. It does
not change the trigger, grasp profile, grounding, or virtual rack surface.
