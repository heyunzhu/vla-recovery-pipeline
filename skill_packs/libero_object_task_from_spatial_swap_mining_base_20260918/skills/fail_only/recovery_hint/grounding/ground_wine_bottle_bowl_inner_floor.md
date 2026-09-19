---
id: ground_wine_bottle_bowl_inner_floor
name: Wine bottle bowl inner-floor grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 49
when_to_apply: When recovery must place the wine bottle in the black bowl but the
  BDDL goal is the coarse bowl object.
when_not_to_apply: Do not use for plate, stove, rack, cabinet, cream-cheese, or
  non-bowl placement tasks.
failure_signature:
- The task language says `put the wine bottle in the bowl`.
- The runtime BDDL atom is `on(wine_bottle_1_main, akita_black_bowl_1_main)`,
  which the recovery start goal check can mark satisfied even though the bottle
  is only near the bowl on the table.
recovery_point: After a matching repair trigger has entered recovery, rewrite the
  coarse bowl placement surface to the bowl inner-floor proxy.
applies_to:
  all:
  - task_language_matches: wine bottle.*in.*bowl|put.*wine bottle.*in.*bowl
  - target_name_matches: wine_bottle|wine bottle
  - goal_name_matches: akita_black_bowl|bowl
  - bddl_goal_surface_matches: akita_black_bowl|bowl
recovery_hints:
  params:
    grounding_profile: wine_bottle_bowl_inner_floor_v1
    source: libero_goal_task03_w1_wrong_object_inner_floor
evidence:
  tasks:
  - 'libero_goal_task task03: put the wine bottle in the bowl'
  episodes:
  - probe_forced_q3_seed51_55 ep00-ep04
---
This hint contributes only goal-surface grounding. The matching geometry hint
creates the actual virtual inner-floor support.
