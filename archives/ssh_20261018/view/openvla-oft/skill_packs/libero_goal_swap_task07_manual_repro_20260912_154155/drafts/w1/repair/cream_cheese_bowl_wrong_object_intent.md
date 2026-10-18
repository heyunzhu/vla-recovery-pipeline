---
id: cream_cheese_bowl_wrong_object_intent
name: Cream cheese wrong object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 60
when_to_apply: In cream-cheese-to-bowl tasks, hand off once the VLA repeatedly aims away from the cream cheese while the target has not moved.
when_not_to_apply: Do not use outside cream cheese and bowl placement tasks. Do not use when the intent object is already the cream cheese, when the target is in the near approach window, or when another task-specific higher-priority trigger has already taken ownership.
failure_signature:
  - Baseline seed51-65 is 0/15 for LIBERO-PRO goal-swap task07.
  - Query traces show the target `cream_cheese_1_main` remains static while the VLA intent object is usually `wine_bottle_1_main` and sometimes `akita_black_bowl_1_main`.
  - In ep00 and ep06 the controller eventually interacts with the stove/button area while the cream cheese remains near the bowl.
recovery_point: Fire after the first legal q5 window once the arm has moved into a meaningful approach range, the target remains far from the predicted VLA path, and the intended object is still not the cream cheese.
applies_to:
  all:
    - task_language_matches: "cream cheese.*bowl|bowl.*cream cheese"
    - target_name_matches: "cream_cheese|cream cheese"
    - bddl_goal_surface_matches: "bowl|akita_black_bowl"
trigger:
  all:
    - holding_status_is: handempty_or_unconfirmed
    - aperture_gt: 0.025
    - intent_object_is_target: false
    - target_ee_distance_lt: 0.37
    - target_future_min_xy_distance_gt: 0.18
    - wrong_object_intent_margin_gt: 0.10
recovery_hints:
  params:
    source: libero_goal_swap_task07_seed51_65_w1
evidence:
  tasks:
    - "libero_goal_swap task07: put the cream cheese in the bowl"
  episodes:
    - task07_seed51_ep00
    - task07_seed52_ep01
    - task07_seed53_ep02
    - task07_seed54_ep03
    - task07_seed55_ep04
    - task07_seed56_ep05
    - task07_seed57_ep06
    - task07_seed58_ep07
    - task07_seed59_ep08
    - task07_seed60_ep09
    - task07_seed61_ep10
    - task07_seed62_ep11
    - task07_seed63_ep12
    - task07_seed64_ep13
    - task07_seed65_ep14
---
This repair skill is deliberately narrow: it requires the cream-cheese target,
a bowl goal surface, an empty hand, and repeated non-target intent. It
contributes only the recovery entrypoint; grasp and placement semantics are
supplied by separate hint skills.
