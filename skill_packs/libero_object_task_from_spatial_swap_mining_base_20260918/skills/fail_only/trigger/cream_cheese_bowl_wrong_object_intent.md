---
id: cream_cheese_bowl_wrong_object_intent
name: Cream cheese wrong object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 60
when_to_apply: In cream-cheese-to-bowl tasks, hand off once the VLA repeatedly aims
  away from the cream cheese while the target has not moved.
when_not_to_apply: Do not use outside cream cheese and bowl placement tasks. Do not
  use when the intent object is already the cream cheese, when the target is in the
  near approach window, or when another task-specific higher-priority trigger has
  already taken ownership.
failure_signature:
- Baseline seed51-65 is 0/15 for LIBERO-PRO goal-swap task07.
- Query traces show the target `cream_cheese_1_main` remains static while the VLA
  intent object is usually `wine_bottle_1_main` and sometimes `akita_black_bowl_1_main`.
- In ep00 and ep06 the controller eventually interacts with the stove/button area
  while the cream cheese remains near the bowl.
recovery_point: Fire after the first legal q5 window once the arm has moved into a
  meaningful approach range, the target remains far from the predicted VLA path, and
  the intended object is still not the cream cheese.
applies_to:
  all:
  - task_language_matches: cream cheese.*bowl|bowl.*cream cheese
  - target_name_matches: cream_cheese|cream cheese
  - bddl_goal_surface_matches: bowl|akita_black_bowl
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - target_ee_distance_lt: 0.37
  - target_future_min_xy_distance_gt: 0.18
  - wrong_object_intent_margin_gt: 0.1
recovery_hints:
  params:
    source: libero_goal_swap_task07_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task07: put the cream cheese in the bowl'
  - libero_90 task07 put the cream cheese in the bowl
  - libero_90 task01 Pick the akita black bowl not between the plate and the ramekin
    and place it on the plate
  - libero_90 task03 Pick the akita black bowl next to the plate and place it on the
    plate
  - libero_90 task04 Pick the akita black bowl on the top of the cabinet and place
    it on the plate
  - libero_90 task05 Pick the akita black bowl on the top of the wooden cabinet and
    place it on the plate
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
  - task7_ep0_seed51
  - task7_ep1_seed52
  - task7_ep2_seed53
  - task7_ep3_seed54
  - task7_ep4_seed55
  - task7_ep5_seed56
  - task7_ep6_seed57
  - task7_ep7_seed58
  - task7_ep8_seed59
  - task7_ep9_seed60
  - task7_ep10_seed61
  - task7_ep11_seed62
  - task7_ep12_seed63
  - task7_ep13_seed64
  - task7_ep14_seed65
  - task1_ep1_seed52
  - task1_ep2_seed53
  - task1_ep3_seed54
  - task1_ep4_seed55
  - task1_ep5_seed56
  - task1_ep6_seed57
  - task1_ep7_seed58
  - task1_ep8_seed59
  - task1_ep9_seed60
  - task1_ep10_seed61
  - task1_ep11_seed62
  - task1_ep12_seed63
  - task1_ep13_seed64
  - task1_ep14_seed65
  - task3_ep0_seed51
  - task3_ep1_seed52
  - task3_ep3_seed54
  - task3_ep4_seed55
  - task3_ep5_seed56
  - task3_ep6_seed57
  - task3_ep7_seed58
  - task3_ep8_seed59
  - task3_ep9_seed60
  - task3_ep10_seed61
  - task3_ep11_seed62
  - task3_ep13_seed64
  - task3_ep14_seed65
  - task4_ep0_seed51
  - task4_ep1_seed52
  - task4_ep2_seed53
  - task4_ep3_seed54
  - task4_ep4_seed55
  - task4_ep5_seed56
  - task4_ep6_seed57
  - task4_ep7_seed58
  - task4_ep8_seed59
  - task4_ep9_seed60
  - task4_ep10_seed61
  - task4_ep11_seed62
  - task4_ep12_seed63
  - task4_ep13_seed64
  - task4_ep14_seed65
  - task5_ep1_seed52
  - task5_ep2_seed53
  - task5_ep4_seed55
  - task5_ep8_seed59
  - task5_ep11_seed62
  - task5_ep13_seed64
  - task5_ep14_seed65
---
This repair skill is deliberately narrow: it requires the cream-cheese target,
a bowl goal surface, an empty hand, and repeated non-target intent. It
contributes only the recovery entrypoint; grasp and placement semantics are
supplied by separate hint skills.
