---
id: ground_cream_cheese_rack_top_region
name: Cream cheese rack top-region grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 68
when_to_apply: When cream-cheese-to-rack recovery must preserve the BDDL wine_rack_1_top_region goal instead of the coarse rack body.
when_not_to_apply: Do not use for bowl, plate, drawer, cabinet, stove, caddy, wine-bottle, or non-rack goals.
failure_signature:
  - Rule traces originally folded the semantic goal to wine_rack_1_main although bddl_goal_surfaces contained wine_rack_1_top_region.
  - With this hint active, traces compile Place(cream_cheese_1_main, ..., wine_rack_1_top_region, ...), proving the rewrite is effective.
recovery_point: Rebind the placement atom to the explicit rack top region during recovery-goal compilation.
applies_to:
  all:
    - task_language_matches: put.*cream cheese.*on.*rack|cream cheese.*rack
    - target_name_matches: cream_cheese|cream cheese
    - goal_name_matches: wine_rack|rack
    - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  params:
    grounding_profile: wine_rack_top_region_v1
    source: libero_goal_task10_20260929
evidence:
  tasks:
    - 'libero_goal_task task10: Put the cream cheese on the rack'
  episodes:
    - t10_probe_abc_20260929 arm B seeds51-55
---
This hint changes only semantic surface binding; the paired geometry hint materializes the surface.
