---
id: wine_bottle_bowl_wrong_object_handoff
name: Wine bottle bowl wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 72
when_to_apply: In wine-bottle-in-bowl tasks, hand off while the VLA still has an
  open empty hand but repeatedly aims at the bowl or another non-target object.
when_not_to_apply: Do not use outside wine-bottle-to-bowl tasks. Do not use once
  the hand is already holding an object, because the common failure has already
  become a wrong-object carry.
failure_signature:
- Skills-off and W0 validation for LIBERO-Pro goal-task task03 are both 0/15.
- Query traces for seeds 51-65 show q2-q8 wrong-object intent while
  `wine_bottle_1_main` remains effectively static.
- Forced q3 recovery reached the rule layer but no-opped under the coarse BDDL
  `on(wine_bottle_1_main, akita_black_bowl_1_main)` start goal check.
recovery_point: Fire after the wrong-object intent persists into the admission-safe
  q5+ window, before the VLA closes on `akita_black_bowl_1_main` or cream cheese.
applies_to:
  all:
  - task_language_matches: wine bottle.*in.*bowl|put.*wine bottle.*in.*bowl
  - target_name_matches: wine_bottle|wine bottle
  - goal_name_matches: akita_black_bowl|bowl
  - bddl_goal_surface_matches: akita_black_bowl|bowl
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.04
  - target_ee_distance_lt: 0.25
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_goal_task03_w1_wrong_object_inner_floor
evidence:
  tasks:
  - 'libero_goal_task task03: put the wine bottle in the bowl'
  episodes:
  - baseline_seed51_65_skills_off ep00-ep14
  - w0_existing_pack_seed51_65 ep00-ep14
  - probe_forced_q3_seed51_55 ep00-ep04
---
This trigger only decides when to enter recovery. The matching grounding and
geometry hints rewrite the coarse bowl goal into a bowl inner-floor proxy.
