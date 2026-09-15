---
id: ground_cream_cheese_wine_rack_top_region
name: Cream cheese wine-rack top-region grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 78
when_to_apply: '当 cream-cheese-to-rack recovery 已经触发，但 cuTAMP problem 把目标编译成 `on(cream_cheese_1_main, wine_rack_1_main)`，而 BDDL 实际目标 surface 是 `wine_rack_1_top_region` 时使用。'
when_not_to_apply: '不用于 bowl、plate、wine bottle、drawer、cabinet、caddy、stove 或非 rack placement；也不用于目标已经稳定在 `wine_rack_1_top_region`、只剩 release 计分抖动的情形。'
failure_signature:
  - 'W1 五个 same-init validation episode 全部失败；上一轮 wrong-object entrypoint 和 `cream_cheese_flat_box_topdown_deep_v1` grasp 已经进入 recovery，因此不是单纯 trigger 缺失。'
  - 'cutamp_debug 中 18 个 solve 里 12 个是 `No satisfying particles found after optimizing all 1 plan(s)`，另有 4 个有 3/4/5 satisfying particles 但 motion planning failed。'
  - '代表性 problem 的 fluent goal 仍是 `on(cream_cheese_1_main, wine_rack_1_main)`，但场景 metadata 暴露了 `wine_rack_1_top_region` site，说明 goal 被粗粒度 rack body 吃掉。'
recovery_point: During recovery goal compilation, rewrite rack placement from the coarse rack body to the explicit BDDL top-region surface.
applies_to:
  all:
    - task_language_matches: cream cheese.*rack|rack.*cream cheese
    - target_name_matches: cream_cheese
    - goal_name_matches: wine_rack|rack
    - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  params:
    grounding_profile: wine_rack_top_region_v1
    source: libero_goal_task_task10_seed51_65_w1
evidence:
  tasks:
    - "libero_goal_task task10: Put the cream cheese on the rack"
  episodes:
    - task10_ep0_seed51
    - task10_ep1_seed52
    - task10_ep2_seed53
    - task10_ep3_seed54
    - task10_ep4_seed55
---
这个 hint 只做语义绑定：它让恢复目标使用 BDDL 指定的 `wine_rack_1_top_region`，而不是把整个 `wine_rack_1_main` 当成支撑面。真正的 rack top 几何由配套的 geometry hint 生成。
