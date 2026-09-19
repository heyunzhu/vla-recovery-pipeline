---
id: cream_cheese_rack_wrong_object_pregrasp_handoff
name: Cream cheese rack wrong-object pregrasp handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 72
when_to_apply: 当任务目标是把 cream_cheese_1_main 放到 wine_rack_1_top_region，但 VLA 在 open-hand
  pregrasp 阶段持续把 intent 和 nearest pickable 指向非目标物体时使用。
when_not_to_apply: 不用于 plate、bowl、cabinet、stove、drawer 或非 rack 目标；不在 intent_object_is_target
  为 true、nearest pickable 已是目标、目标已被确认 holding、或只是普通目标接近阶段时触发。
failure_signature:
- task10 w0 的 5 个 same-init validation 失败均没有 recovery event，recovery_trace.jsonl 为
  0 行，cutamp_debug 目录为空。
- 目标 `cream_cheese_1_main` 的 `target_total_motion_m` 在全程接近 0，`wrong_progress_target_static`
  为 true，说明 cream cheese 没有被实际操控。
- q5-q11 之间 `intent_object_is_target=false`、`nearest_pickable_is_target=false`、`wrong_object_intent_persist_queries>=3`，且
  `vla_pick_target_status` 进入 `non_target_intent` 或 `non_target_intent_with_motion`。
- 命中行的错物体先后是 `akita_black_bowl_1_main` 或 `wine_bottle_1_main`，后续 ep01、ep02、ep04 进入
  holding 状态但仍不是目标 cream cheese。
recovery_point: Fire in the open-hand wrong-object pregrasp window so cutamp_recover
  owns the full cream_cheese_1_main pick and wine_rack_1_top_region place sequence
  before a non-target object is held.
applies_to:
  all:
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - wrong_progress_target_static: true
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - nearest_pickable_distance_lt: 0.25
  - wrong_object_intent_persist_queries_gte: 3
  - wrong_object_intent_margin_gt: 0.05
  - target_future_min_xy_distance_gt: 0.11
  - target_ee_distance_gt: 0.18
  any:
  - vla_pick_target_status_is: non_target_intent
  - vla_pick_target_status_is: non_target_intent_with_motion
recovery_hints:
  params:
    source: libero_goal_task10_cream_cheese_rack_wrong_object_w0
evidence:
  tasks:
  - libero_goal_task task10 Put the cream cheese on the rack
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - task10_ep0_seed51_q11
  - task10_ep1_seed52_q5
  - task10_ep2_seed53_q5
  - task10_ep3_seed54_q8
  - task10_ep4_seed55_q7
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
---
这个 trigger 只解决 recovery 没有启动的问题。它要求目标 cream cheese 静止、非目标 intent 已持续、nearest pickable 不是目标，并且夹爪仍处在 open-hand pregrasp 窗口；因此它不是简单的目标接近触发，也不会把已在正确抓取目标的轨迹交给 recovery。
