---
id: object_basket_cream_tomato_q5_wrong_intent_window
name: Cream-cheese and tomato basket q5 wrong-intent window
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 79
when_to_apply: In cream-cheese or tomato-sauce basket tasks, hand off after a
  wrong target has persisted into the q5-scale approach window while the true
  target remains outside the predicted approach.
when_not_to_apply: Do not fire before q5, after an object is held, for target
  intent, for weak/transient margins, or outside the bounded 0.20-0.24 m nearest
  wrong-object distance window.
failure_signature:
- In all five object_task cream-cheese failures, q5 has non-target milk intent,
  a margin above 0.11 m, target future distance above 0.196 m, and nearest wrong
  object distance 0.204-0.231 m, but the original persistence threshold of four
  is unreachable (observed maximum two).
- 'Two uncovered tomato failures show the same q5 geometry; their only failed
  original predicate is wrong_object_intent_persist_queries_gte: 4.'
recovery_point: Enter recovery at the first stable q5-scale wrong-object approach,
  before the gripper closes on the distractor.
applies_to:
  all:
  - task_language_matches: pick the (cream cheese|tomato sauce) and place it in the basket
  - target_name_matches: cream_cheese|cream cheese|tomato_sauce|tomato sauce
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - ee_stalled:
      window: 6
      max_disp_m: 0.35
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 1
  - wrong_object_intent_margin_gt: 0.10
  - intent_min_xy_distance_lt: 0.085
  - target_future_min_xy_distance_gt: 0.19
  - nearest_pickable_is_target: false
  - nearest_pickable_distance_gt: 0.20
  - nearest_pickable_distance_lt: 0.24
recovery_hints:
  params:
    source: object_task_q5_wrong_intent_gap_20260920
evidence:
  tasks:
  - 'libero_object_task task01: Pick the cream cheese and place it in the basket'
  - 'libero_object_task task03: Pick the tomato sauce and place it in the basket'
  episodes:
  - object_task_w0_triggers_graspcand_5ep/task01/ep00
  - object_task_w0_triggers_graspcand_5ep/task01/ep01
  - object_task_w0_triggers_graspcand_5ep/task01/ep02
  - object_task_w0_triggers_graspcand_5ep/task01/ep03
  - object_task_w0_triggers_graspcand_5ep/task01/ep04
  - object_task_w0_triggers_graspcand_5ep/task03/ep00
  - object_task_w0_triggers_graspcand_5ep/task03/ep04
---
This draft adds a narrow complementary window. It does not weaken or replace the
existing persistent and precontact triggers. The six-query history guard makes
q<5 firing impossible; its displacement cap only rejects discontinuous/reset
histories and is not intended to diagnose a stationary end effector.
