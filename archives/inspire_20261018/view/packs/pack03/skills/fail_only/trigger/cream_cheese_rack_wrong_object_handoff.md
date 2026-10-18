---
id: cream_cheese_rack_wrong_object_handoff
name: Cream cheese rack wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 71
when_to_apply: In cream-cheese-to-rack tasks, hand off while the open empty gripper persistently follows a non-target pickable instead of the cream cheese.
when_not_to_apply: Do not use outside cream-cheese-to-rack tasks, after an object is held, or for cream-cheese bowl, drawer, or stove tasks.
failure_signature:
  - The skills-off task10 baseline is 0/50 with recovery_calls=0/50 and no episode ever grasping cream_cheese_1_main.
  - Runtime matcher diagnostics pass the state predicates but reject the previous bowl-only language gate for "Put the cream cheese on the rack".
recovery_point: Fire only after persistent wrong-object intent while the cream cheese remains static and reachable.
applies_to:
  all:
    - task_language_matches: put.*cream cheese.*on.*rack|cream cheese.*rack
    - target_name_matches: cream_cheese|cream cheese
    - goal_name_matches: wine_rack|rack
    - bddl_goal_surface_matches: wine_rack|rack|top_region
trigger:
  all:
    - holding_status_is: handempty_or_unconfirmed
    - aperture_gt: 0.025
    - intent_object_is_target: false
    - nearest_pickable_is_target: false
    - wrong_object_intent_persist_queries_gte: 3
    - wrong_object_intent_margin_gt: 0.03
    - nearest_pickable_distance_lt: 0.28
    - target_ee_distance_lt: 0.265
    - wrong_progress_target_static: true
recovery_hints:
  params:
    repair_profile: entry_topdown_orientation_reset_v1
    source: libero_goal_task10_20260929_topdown_entry_v4
evidence:
  tasks:
    - 'libero_goal_task task10: Put the cream cheese on the rack'
  episodes:
    - gtask_rest task10 seeds1-50 skills-off (2026-09-29)
    - t10 formal seed51 matcher replay (v1 first fired at query12; v2 first fires at query6)
---
This trigger owns only recovery entry. Grounding, geometry, and grasp remain separate skills.
