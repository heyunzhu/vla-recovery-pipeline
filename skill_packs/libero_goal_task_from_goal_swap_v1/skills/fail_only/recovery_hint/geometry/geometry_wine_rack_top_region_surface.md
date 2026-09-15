---
id: geometry_wine_rack_top_region_surface
name: Wine-rack top-region virtual surface
kind: recovery_hint
track: fail_only
scope: geometry
priority: 77
when_to_apply: '当 cream cheese 的恢复 goal 已经指向 rack top region，或者 debug 显示 coarse rack body 造成 `robot_to_world`/`pos_err` zero-satisfying 约束时使用。'
when_not_to_apply: '不用于 bowl、plate、drawer、cabinet、caddy、stove、桌面侧区，或没有 `wine_rack_1_top_region` site 的任务。'
failure_signature:
  - 'W1 debug 中所有 solve 都使用了 `cream_cheese_flat_box_topdown_deep_v1`，说明 grasp hint 已生效；剩余失败集中在 planner grounding/geometry。'
  - 'dominant stderr 约束包含 12 次 `[Collision] robot_to_world <= 0.001 has 0/64 satisfying` 和 6 次 `[KinematicConstraint] pos_err <= 0.005 has 0/64 satisfying`。'
  - '`wine_rack_1_main` 的 AABB 顶部约在 0.336m，但 `wine_rack_1_top_region` site 位于约 0.225m；若继续用 rack body 或桌面矩形，会把支撑高度和碰撞代理放错。'
recovery_point: During TAMP scene construction, create a thin virtual `wine_rack_1_top_region` box from the rack top-region MuJoCo site in planner frame.
applies_to:
  all:
    - task_language_matches: cream cheese.*rack|rack.*cream cheese
    - target_name_matches: cream_cheese
    - goal_name_matches: wine_rack|rack
    - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  params:
    geometry_profile: wine_rack_top_region_surface_v1
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
这个 hint 使用新的 pack-local `wine_rack_top_region_surface_v1`。adapter 从 `wine_rack_1_main` 的 `wine_rack_1_top_region` site 读取位置和尺寸，生成一个薄的 `box` virtual surface，并标记 `exclude_source_collision`，让 planner 不再把整只 rack 的粗 AABB 当成最终支撑面。
