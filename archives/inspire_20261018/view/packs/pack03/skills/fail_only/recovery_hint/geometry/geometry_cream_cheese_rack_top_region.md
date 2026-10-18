---
id: geometry_cream_cheese_rack_top_region
name: Cream cheese rack top-region surface with bowl-contact allowance
kind: recovery_hint
track: fail_only
scope: geometry
priority: 67
when_to_apply: When the task10 rack-top goal is grounded correctly but needs its MuJoCo site geometry and a task-approved contact allowance for the nearby movable black bowl.
when_not_to_apply: Do not use outside cream-cheese-to-rack tasks, without wine_rack_1_top_region, or when contact with the black bowl is not acceptable.
failure_signature:
  - The old adapter missed top-level geometry.sites and placed the virtual surface about 0.08 m off in Y and 0.215 m too low, causing place_hover tracking stalls.
  - After site lookup was corrected, static_context=none completed seed51 end to end; official collision mode still had 0/64 because the nearby akita_black_bowl_1_main was the unique blocking static object.
  - Offline ablation was feasible when only the black bowl was removed, but remained infeasible when only the wine bottle was removed.
recovery_point: Materialize wine_rack_1_top_region from the MuJoCo site and exclude only the explicitly allowed movable black bowl from this goal's planner collision world.
applies_to:
  all:
    - task_language_matches: put.*cream cheese.*on.*rack|cream cheese.*rack
    - target_name_matches: cream_cheese|cream cheese
    - goal_name_matches: wine_rack|rack
    - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  params:
    geometry_profile: wine_rack_top_region_surface_v1
    source: libero_goal_task10_20260929
evidence:
  tasks:
    - 'libero_goal_task task10: Put the cream cheese on the rack'
  episodes:
    - t10_sitefix_probe_20260929/B_seed51
    - t10_sitefix_probe_20260929/A_seed51
    - t10_sitefix_probe_20260929/static_ablation
---
The engine accepts this exclusion only for a named movable static-context object. Table, rack, cabinet, and other fixtures remain collision obstacles.
