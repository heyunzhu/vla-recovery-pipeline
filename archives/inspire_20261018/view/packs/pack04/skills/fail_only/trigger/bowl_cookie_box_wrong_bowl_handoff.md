---
id: bowl_cookie_box_wrong_bowl_handoff
name: Bowl-on-cookie-box wrong-bowl handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 71
when_to_apply: In bowl-on-cookie-box-to-plate tasks, hand off to recovery while the
  VLA still has an open empty hand but keeps fixating on the second (decoy) bowl
  instead of the target bowl on the box.
when_not_to_apply: Do not use outside the bowl-on-cookie-box wording (the next-to
  cookie box and cabinet/stove/ramekin wordings do not match). Do not use once the
  hand already holds an object.
failure_signature:
- Skills-off and W0 validation for libero_spatial_swap task04 are both 0/15
  (2026-09-16 round, seeds 51-65); W0 has zero recovery calls.
- The scene contains two black bowls; the target akita_black_bowl_1_main sits on
  the cookie box while the policy's dominant intent is akita_black_bowl_2_main.
- GS09 (bowl_plate_pick_lost_or_wrong_intent) never fires because the end
  effector never enters its 0.16 m target-approach window (min target distance
  0.19-0.26 m in this scene family).
- Baseline traces show admission-safe q13+ wrong-object windows in 9/15 episodes
  under this trigger's predicates; the wrong object is always akita_black_bowl_2_main.
recovery_point: Fire after wrong-object intent persists for four queries and the
  open gripper is within 0.25 m of the wrongly fixated pickable, before the VLA
  closes on the decoy bowl.
applies_to:
  all:
  - task_language_matches: bowl.*on the cookies? box.*place it on the plate|bowl.*on the cookies? box.*on the plate
  - target_name_matches: akita_black_bowl_1|black_bowl|bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.03
  - nearest_pickable_distance_lt: 0.25
  - target_ee_distance_lt: 0.35
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_spatial_swap_task04_20260916_w1
evidence:
  tasks:
  - 'libero_spatial_swap task04: Pick the akita black bowl on the cookie box and place it on the plate'
  episodes:
  - baseline_task04_seed51_65_skills_off ep00-ep14 (2026-09-16 run)
  - w0_task04_seed51_65_new_pack ep00-ep14 (2026-09-16 run)
---
This trigger only decides when to enter recovery. The pack's existing
hollow_bowl_rim_topdown grasp hint and default place chain own the pick and
placement; the registered entry-lift repair profile unblocks trajectory tracking
from the policy's decoy-approach pose.