---
id: object_basket_persistent_wrong_intent_group_a
name: Object basket persistent wrong-intent handoff group A
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 76
when_to_apply: In basket placement tasks for alphabet soup, butter, chocolate pudding,
  ketchup, or milk, hand off after a non-target object has remained the inferred
  pick intent for four consecutive queries while the gripper is still open and empty.
when_not_to_apply: Do not use for other target objects, outside basket-placement
  tasks, after an object is held, or for transient wrong intent shorter than four
  consecutive queries.
failure_signature:
- Across the 600-episode object-task/object-swap corpus, these five targets have
  persistent non-target intent in 270 of 272 failed episodes after the q0-q4
  exclusion window.
- None of the 28 successful episodes match this persistent-wrong-intent condition.
recovery_point: Enter recovery at the first persistent wrong-object pregrasp state,
  before the policy closes on the distractor.
applies_to:
  all:
  - task_language_matches: pick the (alphabet soup|butter|chocolate pudding|ketchup|milk) and place it in the basket
  - target_name_matches: alphabet_soup|butter|chocolate_pudding|ketchup|milk
  - bddl_goal_surface_matches: basket
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.0
recovery_hints:
  params:
    source: object_axes_offline_trigger_group_a_20260919
evidence:
  tasks:
  - libero_object_task and libero_object_swap basket-placement tasks for alphabet
    soup, butter, chocolate pudding, ketchup, and milk
  episodes:
  - libero_screening_20260918 object axes, baseline and W0, seeds 51-65
---
This draft only decides when to hand off. It does not select a grasp or place profile.
