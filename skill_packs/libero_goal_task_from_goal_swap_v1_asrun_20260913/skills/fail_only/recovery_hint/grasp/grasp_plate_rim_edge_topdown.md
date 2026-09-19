---
id: grasp_plate_rim_edge_topdown
name: Plate rim edge top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 46
when_to_apply: 当任务要求把 plate_1_main 放到 stove / cook_region，且 recovery 已经在 q5/q6 左右正确介入，但 native/default plate grasp 仍出现 no satisfying particles 或 motion planning failed 时使用。
when_not_to_apply: 不用于 bowl、cream cheese、bottle、cabinet、drawer 或非 plate 目标；也不用于只剩 release/验收问题的情形。
failure_signature:
- >-
  W4 中 plate_stove_open_wrong_intent_pregrasp_handoff 已稳定在 q5/q6 触发，说明当前主要问题不再是触发时机。
- >-
  W4 大多数 episode 在目标已经被 grounding 到 flat_stove_1_cook_region 后仍返回 No satisfying particles found after optimizing all 1 plan(s)。
- >-
  现有 plate hint 只切到 cutamp_native，没有为薄盘子的 rim / edge 几何提供任务内 grasp 候选。
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
recovery_hints:
  grasp_profile: plate_rim_edge_topdown_v1
  target: target
  params:
    source: libero_goal_task_task02_seed51_65_w5
evidence:
  tasks:
  - libero_goal_task task02 Put the plate on the stove
  episodes:
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
---
这个 hint 只替换 grasp profile，不改变 trigger、grounding 或 stove cook-region geometry。`plate_rim_edge_topdown_v1` 在 plate 外缘附近采样 top-down 抓取点，并提供径向/切向 yaw 候选，让 cuTAMP 可以从盘子边缘而不是中心去生成 pick skeleton。
