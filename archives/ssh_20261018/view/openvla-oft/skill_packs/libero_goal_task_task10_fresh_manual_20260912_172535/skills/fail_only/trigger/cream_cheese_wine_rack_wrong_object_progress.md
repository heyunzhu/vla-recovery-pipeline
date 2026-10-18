---
id: cream_cheese_wine_rack_wrong_object_progress
name: Cream cheese rack wrong-object progress handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 70
when_to_apply: In the cream-cheese-to-rack task, hand off only after the fresh skills-off
  trace shows a non-target object being transported while the cream cheese target
  remains static and the hand is still empty or unconfirmed.
when_not_to_apply: Do not use for bowl, cabinet, table, or drawer goals; correctly
  bound cream-cheese progress; confirmed holding; or ordinary early target approach
  before measurable wrong-object transport.
failure_signature:
- The task language is `Put the cream cheese on the rack`, but the VLA intent trace
  repeatedly selects a non-target object.
- Across fresh seeds 51-65, the target remains static, no target-near window is reached,
  and the wrong object eventually reaches transport or goal status.
- A forced real-cuTAMP recovery at query 5 fails because the rack top site is absent
  from planner surfaces and the fallback goal becomes holding-only.
recovery_point: Fire after wrong-object progress is measurable, with the target still
  outside the VLA path and the hand empty or unconfirmed.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
  - bddl_goal_surface_matches: '*wine_rack*top_region'
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - intent_object_is_target: false
  - wrong_progress_target_static: true
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_progress_object_is_intent: true
  - wrong_progress_object_total_motion_gt: 0.06
  - target_ee_distance_gt: 0.18
  - target_future_min_xy_distance_gt: 0.1
  any:
  - vla_wrong_object_progress_status_is: wrong_object_transported
  - vla_wrong_object_progress_status_is: wrong_object_at_goal
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
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

This skill is the recovery entrypoint only. It does not choose a grasp or
invent a place policy. Matching fail-only grounding and geometry hints provide
the fresh pack profiles needed by cuTAMP for the BDDL rack-top site.
