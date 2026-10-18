# C4 pack：全部 36 条 skill 使用总表

最新补充：[全 36 条条件匹配、决策选择与实际 recovery 入口总表](libero_pro_c4_hint_shadow_report.md)，包含全部 18 条 hint 的 task 级旁路统计、同职责/跨职责重叠。下表保留原决策计数口径。

口径补充（旁路审计确认）：本表使用次数是 hook winner 决策或 hint 配置合并次数，不等于实际恢复执行。C4 共 594 条 hook 决策 query，但只有 269 条 query 的 mode=recovery，涉及 223 个 episode。参见 [旁路统计报告](libero_pro_c4_shadow_overlap_report.md)。

数据：C4，六个 LIBERO-PRO suites × 10 tasks × 5 episodes = 300 episodes；8,107 queries，594 次接管决策（269 次实际 recovery 入口）。按冻结 pack 的 `_index.yaml` 核对，18 条 trigger + 18 条 recovery hint，共 36 条。每条单独一行，零使用条目保留。

“实际使用次数”：trigger 为成为接管 winner 的 query 次数；hint 为接管配置中 `hint_sources` 记录的合并次数。Hint 被选择不等于其物理执行阶段已完成。Task 数按 suite + task ID 计；同指令不同 ID 仍计为不同 task。

“最终成功/使用 ep”是使用过该条 skill 的 episode 最终结果，不是单条 skill 的独立成功率；同一 episode 可出现在多行，不能相加。表中未列的 task 实际使用次数为零，不代表没有静态语义匹配。

| 编号 | 完整 skill ID | 类型 | 实际使用次数 | 使用 task 数 | 实际使用 task | 最终成功/使用 ep |
| ---: | --- | --- | ---: | ---: | --- | ---: |
| 1 | black_bowl_cabinet_top_to_plate_wrong_object_handoff | Trigger | 6 | 2 | spatial_task: T07,T09 | 6/6 |
| 2 | black_bowl_next_to_plate_wrong_object_handoff | Trigger | 16 | 1 | spatial_task: T02 | 2/3 |
| 3 | black_bowl_not_between_wrong_object_handoff | Trigger | 3 | 1 | spatial_task: T01 | 1/3 |
| 4 | black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | Trigger | 5 | 1 | spatial_task: T03 | 4/5 |
| 5 | bowl_cabinet_target_holding_handoff | Trigger | 0 | 0 | 无 | — |
| 6 | bowl_cookie_box_wrong_bowl_handoff | Trigger | 0 | 0 | 无 | — |
| 7 | bowl_plate_pick_lost_or_wrong_intent | Trigger | 428 | 21 | goal_swap: T04；spatial_swap: T01–T10；spatial_task: T01–T10 | 63/92 |
| 8 | cream_cheese_bowl_wrong_object_intent | Trigger | 5 | 1 | goal_swap: T07 | 4/5 |
| 9 | cream_cheese_rack_wrong_object_handoff | Trigger | 5 | 1 | goal_task: T08 | 5/5 |
| 10 | object_basket_bbq_orange_precontact_wrong_intent | Trigger | 20 | 4 | object_swap: T02,T08；object_task: T03,T10 | 20/20 |
| 11 | object_basket_cream_cheese_precontact_wrong_intent | Trigger | 4 | 1 | object_swap: T05 | 2/4 |
| 12 | object_basket_cream_tomato_q5_wrong_intent_window | Trigger | 9 | 2 | object_task: T01,T09 | 9/9 |
| 13 | object_basket_persistent_wrong_intent_group_a | Trigger | 47 | 9 | object_swap: T01,T03,T04,T06,T07；object_task: T02,T06,T07,T08 | 38/45 |
| 14 | object_basket_salad_dressing_precontact_wrong_intent | Trigger | 10 | 2 | object_swap: T09；object_task: T04 | 9/10 |
| 15 | object_basket_tomato_persistent_wrong_intent | Trigger | 5 | 1 | object_swap: T10 | 5/5 |
| 16 | plate_stove_open_wrong_intent_pregrasp_handoff | Trigger | 19 | 1 | goal_task: T05 | 0/5 |
| 17 | wine_bottle_bowl_wrong_object_handoff | Trigger | 9 | 2 | goal_task: T07,T09 | 7/9 |
| 18 | wine_bottle_plate_wrong_object_handoff | Trigger | 3 | 1 | goal_task: T04 | 3/3 |
| 19 | bowl_plate_hover_drop_budget | Hint | 15 | 1 | spatial_task: T01 | 2/4 |
| 20 | bowl_plate_next_to_plate_hover_drop_budget | Hint | 40 | 2 | spatial_swap: T05；spatial_task: T02 | 9/10 |
| 21 | cabinet_top_surface_geometry_explicit | Hint | 0 | 0 | 无 | — |
| 22 | cream_cheese_bowl_hover_drop_budget | Hint | 5 | 1 | goal_swap: T07 | 4/5 |
| 23 | cream_cheese_bowl_support_geometry | Hint | 5 | 1 | goal_swap: T07 | 4/5 |
| 24 | cream_cheese_bowl_support_grounding | Hint | 5 | 1 | goal_swap: T07 | 4/5 |
| 25 | geometry_cream_cheese_rack_top_region | Hint | 5 | 1 | goal_task: T08 | 5/5 |
| 26 | geometry_wine_bottle_bowl_inner_floor | Hint | 9 | 2 | goal_task: T07,T09 | 7/9 |
| 27 | grasp_bowl_plate_hollow_rim_topdown | Hint | 458 | 21 | goal_swap: T04；spatial_swap: T01–T10；spatial_task: T01–T10 | 73/103 |
| 28 | grasp_carton_upright_body_side | Hint | 20 | 4 | object_swap: T07,T08；object_task: T03,T06 | 20/20 |
| 29 | grasp_cream_cheese_bowl_flat_box_topdown_deep | Hint | 5 | 1 | goal_swap: T07 | 4/5 |
| 30 | grasp_cream_cheese_rack_flat_box_deep | Hint | 5 | 1 | goal_task: T08 | 5/5 |
| 31 | grasp_object_basket_flat_box_topdown_deep | Hint | 30 | 6 | object_swap: T03,T04,T05；object_task: T01,T07,T08 | 19/28 |
| 32 | grasp_wine_bottle_plate_topdown_close_guard | Hint | 3 | 1 | goal_task: T04 | 3/3 |
| 33 | grasp_wine_bottle_topdown_close_guard | Hint | 9 | 2 | goal_task: T07,T09 | 7/9 |
| 34 | ground_cream_cheese_rack_top_region | Hint | 5 | 1 | goal_task: T08 | 5/5 |
| 35 | ground_wine_bottle_bowl_inner_floor | Hint | 9 | 2 | goal_task: T07,T09 | 7/9 |
| 36 | place_wine_bottle_bowl_drop_budget | Hint | 9 | 2 | goal_task: T07,T09 | 7/9 |

核验：36 个不同 skill ID；trigger 使用次数合计 594，与接管 query 总数一致；18 个 hint 的 query 来源计数与原始逐 query 明细一致。16/18 条 trigger 与 17/18 条 hint 被使用过，即 33/36 有本轮实际使用证据。

来源：`tmp/inspire/skill_overlap_c4.json`（trigger 逐 task 聚合）与 `docs/results/libero_pro_c4_recovery_hint_usage.json`（hint 实际来源记录）。Hint 与 profile 的逐 task 次数见 [详细报告](libero_pro_c4_recovery_hint_usage_report.md)；trigger 的逐 task 次数见 `libero_pro_c4_skill_task_level_trigger_matrix.csv`。
