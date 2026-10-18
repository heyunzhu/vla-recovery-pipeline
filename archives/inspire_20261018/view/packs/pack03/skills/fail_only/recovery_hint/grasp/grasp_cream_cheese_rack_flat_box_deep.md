---
id: grasp_cream_cheese_rack_flat_box_deep
name: Cream cheese rack flat-box deep top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 59
when_to_apply: When task10 recovery must grasp the thin cream-cheese box from the table.
when_not_to_apply: Do not use for bowls, plates, mugs, bottles, cans, cartons, books, baskets, trays, or cream-cheese tasks with a non-rack goal.
failure_signature:
  - The skills-off 50-episode baseline never grasped cream_cheese_1_main.
  - With this profile and the corrected rack geometry, seed51 passed pick trajectory, close, 17/17 strict tracking events, and lift_probe before completing placement.
recovery_point: Sample deep top-down grasps for the thin flat box after task10 recovery has fired.
applies_to:
  all:
    - task_language_matches: put.*cream cheese.*on.*rack|cream cheese.*rack
    - target_name_matches: cream_cheese|cream cheese
    - target_name_excludes: butter|chocolate_pudding|book|bowl|mug|can|bottle|milk|orange_juice
    - goal_name_matches: wine_rack|rack
    - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deeper_v2
  target: target
  params:
    source: libero_goal_task10_20260929_deeper_v2
evidence:
  tasks:
    - 'libero_goal_task task10: Put the cream cheese on the rack'
  episodes:
    - t10_sitefix_probe_20260929/B_seed51
---
This skill owns only target grasp sampling; it does not alter grounding, collision policy, or place execution.
