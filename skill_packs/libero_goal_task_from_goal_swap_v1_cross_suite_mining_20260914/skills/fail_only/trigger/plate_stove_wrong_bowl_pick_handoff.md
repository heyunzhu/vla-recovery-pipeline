---
id: plate_stove_wrong_bowl_pick_handoff
name: Plate stove wrong-bowl pick handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 64
when_to_apply: 当任务要求把 plate 放到 stove 上，解析目标是 plate_1_main，但 VLA 持续把意图和夹爪闭合放到非目标 akita_black_bowl_1_main
  时使用。
when_not_to_apply: 不用于 bowl-on-plate、bowl-on-cabinet、cream-cheese、drawer、cabinet-top
  或非 stove 目标；不在只有早期接近、没有非目标可抓物接近/闭合/误持证据时触发；如果 plate 已经被确认抓起或正在被跟随，也不要触发。
failure_signature:
- 本轮 15 个 same-init validation episode 全部失败，且 recovery_events 均为 0。
- trace 的 BDDL goal 为 on(plate_1_main, flat_stove_1_cook_region)，但 VLA 从早期 query 起持续把
  intent_object_name 指向 akita_black_bowl_1_main。
- 多数 episode 在 q9-q13 已经进入 non_target_near 或错误物体闭合/误持状态，最近可抓物不是 plate，目标 plate 没有被拾取。
- ep00 关键帧显示黑碗被搬到 stove/plate 区域，而 plate 仍不是被操控目标。
recovery_point: 在 VLA 已经对非目标黑碗形成稳定 pick 企图或闭合后，尽早交给 cutamp_recover 重新规划 plate-to-stove
  的 pick-and-place。
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
trigger:
  all:
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - nearest_pickable_is_target: false
  - nearest_pickable_distance_lt: 0.26
  - target_ee_distance_gt: 0.12
  any:
  - vla_pick_target_status_is: non_target_near
  - vla_pick_target_status_is: off_target_unknown
  - wrong_progress_object_is_held: true
  - wrong_progress_object_total_motion_gt: 0.06
  - aperture_lt: 0.015
recovery_hints:
  params:
    source: libero_goal_task02_plate_stove_wrong_bowl_w0
evidence:
  tasks:
  - 'libero_90 task02: Put the plate on the stove'
  - libero_90 task02 Put the plate on the stove
  - libero_90 task01 Pick the akita black bowl not between the plate and the ramekin
    and place it on the plate
  - libero_90 task03 Pick the akita black bowl next to the plate and place it on the
    plate
  episodes:
  - task02_seed51_ep00
  - task02_seed52_ep01
  - task02_seed53_ep02
  - task02_seed54_ep03
  - task02_seed55_ep04
  - task02_seed56_ep05
  - task02_seed57_ep06
  - task02_seed58_ep07
  - task02_seed59_ep08
  - task02_seed60_ep09
  - task02_seed61_ep10
  - task02_seed62_ep11
  - task02_seed63_ep12
  - task02_seed64_ep13
  - task02_seed65_ep14
  - task2_ep0_seed51
  - task2_ep1_seed52
  - task2_ep2_seed53
  - task2_ep3_seed54
  - task2_ep4_seed55
  - task2_ep5_seed56
  - task2_ep6_seed57
  - task2_ep7_seed58
  - task2_ep8_seed59
  - task2_ep9_seed60
  - task2_ep10_seed61
  - task2_ep11_seed62
  - task2_ep12_seed63
  - task2_ep13_seed64
  - task2_ep14_seed65
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
  - task3_ep10_seed61
  - task3_ep11_seed62
  - task3_ep13_seed64
  - task3_ep14_seed65
---
这个触发器只解决 recovery 没有启动的问题。它要求有持续 wrong-object intent，并且最近可抓物不是目标 plate，同时出现 non-target pick 状态、误持、错误物体移动或闭合夹爪之一；因此它不是单纯的目标接近触发器。
