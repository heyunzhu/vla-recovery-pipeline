---
id: grasp_cream_cheese_rack_libero_topdown
name: Cream cheese rack shallow top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 78
when_to_apply: 当任务目标是把 cream_cheese_1_main 放到 wine_rack_1_top_region，且已有 wrong-object
  trigger 已经接管 recovery 时使用。
when_not_to_apply: 不用于 bowl、plate、wine bottle、rack 本体或非 cream cheese 目标；不用于目标已经稳定
  holding 后只剩 release/place 的情形。
failure_signature:
- W1 中 recovery 已触发，但多数 cuTAMP solve 在 Pick/Place 组合优化时出现 `robot_to_world` collision
  0/64 和 `pos_err` 0/64。
- W1 的 problem.json 显示旧 profile `cream_cheese_flat_box_topdown_deep_v1` 对 cream cheese
  给出的 grasp z 在物体中心以下约 3.1mm，而该盒子半高只有约 8.9mm。
- ep03 一度找到 pick 粒子，但执行 Pick 时 `optimized_motion_tracking_stalled`，说明深抓取候选仍可能把手臂/夹爪压进碰撞或不可稳定跟踪区。
recovery_point: After the existing cream-cheese-rack repair trigger fires, before
  cuTAMP samples the Pick grasp.
applies_to:
  all:
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack
recovery_hints:
  grasp_profile: libero_topdown
  target: target
  params:
    source: libero_goal_task10_cream_cheese_rack_w1
evidence:
  tasks:
  - libero_goal_task task10 Put the cream cheese on the rack
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - task10_ep0_seed51_q11
  - task10_ep1_seed52_q5
  - task10_ep2_seed53_q11
  - task10_ep3_seed54_q20
  - task10_ep4_seed55_q8
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
---
这个 hint 用更高优先级覆盖上一轮的 deep flat-box grasp，回到内置 `libero_topdown`。它的目的不是新增抓取算法，而是先验证 W1 的 pick collision / tracking stall 是否来自过深的 cream cheese 抓取点。
