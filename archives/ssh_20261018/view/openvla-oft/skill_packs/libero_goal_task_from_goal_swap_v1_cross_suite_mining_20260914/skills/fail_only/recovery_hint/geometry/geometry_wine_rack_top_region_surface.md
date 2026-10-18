---
id: geometry_wine_rack_top_region_surface
name: Wine-rack top-region virtual surface
kind: recovery_hint
track: fail_only
scope: geometry
priority: 77
when_to_apply: 当 cream cheese 的恢复 goal 指向 rack top region，或者 planner 对 coarse rack
  body 没有可满足 place 粒子时使用。
when_not_to_apply: 不用于 bowl、plate、drawer、cabinet、caddy、stove、桌面侧区，或没有 `wine_rack_1_top_region`
  site 的任务。
failure_signature:
- W0 中现有 entrypoint 与 cream-cheese grasp hint 已经触发，但 ep00/ep02/ep04 仍是 `num_satisfying=0`。
- ep01 有少量 satisfying particles 但 motion planning failed，说明目标 surface 的几何/碰撞代理仍然太粗或不稳定。
- '`wine_rack_1_top_region` 在 BDDL/scene metadata 中存在，但当前 fail-only 库还没有把对应 geometry
  hint ingest 进 `_index.yaml`。'
recovery_point: During TAMP scene construction, create a thin virtual `wine_rack_1_top_region`
  box from the rack top-region MuJoCo site in planner frame.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  params:
    geometry_profile: wine_rack_top_region_surface_v1
    source: libero_goal_task10_cream_cheese_rack_geometry_w0
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - task10_ep00_seed51
  - task10_ep01_seed52
  - task10_ep02_seed53
  - task10_ep03_seed54
  - task10_ep04_seed55
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
---
这个 hint 使用当前 pack 已注册的 `wine_rack_top_region_surface_v1`。adapter 会从 `wine_rack_1_main` 的 `wine_rack_1_top_region` site 读取位置和尺寸，生成一个薄的 `box` virtual surface，并标记 planner-frame bounds。
