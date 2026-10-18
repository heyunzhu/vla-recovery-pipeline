# C4：18 条 recovery hint 与 profile 实际使用统计

口径补充：此处“选用”指 hook 决策配置来源，不保证实际执行 recovery。旁路审计确认 C4 的 594 条 hook 决策 query 中，269 条实际进入 recovery；详见 [旁路统计报告](libero_pro_c4_shadow_overlap_report.md)。

统计日期：2026-10-10。补齐 pack 中此前未做全量使用统计的 18 条 recovery hints。

## 数据与口径

- 条件：C4 `libero_object_task_from_spatial_swap_mining_base_20260918`；六个 suite、每 suite 10 个 task、每 task 5 个 episode，共 300 episodes。
- 扫描 8,107 条 query，其中 594 条 `hook_fired=true`。594 条均有 `hint_sources`，无未知 hint 来源。
- “选用次数”指接管 query 的最终合并配置中，`hint_sources` 列出了该 hint。不是静态 applies_to 次数，也不是物理抓取/放置执行次数。
- “使用 episodes”按 suite/task/episode 去重；“最终成功”是其中 episode 最终成功数。一个 episode 可以使用多个 hint，因此各行不能相加，也不能把最终成功归因给单条 hint。
- “task 数”按 suite + task ID 计数；同一句任务指令出现在不同 ID 时仍分别计数，不等于独立语义模板数。
- Profile 指最终配置选中的命名 profile；执行是否到达该阶段尚未全量审计。没有命名 profile 的 hint 仍可能通过 executor 参数参与方案。
- 以下是已测任务中的使用/复用证据，不是严格 held-out 泛化成绩；尚未系统排除这些任务参与历史 mining 或调参。

## 全部 18 条 hint

| Hint ID | 选用次数 | 使用 task 数 | 使用 episodes | 其中最终成功 |
| --- | ---: | ---: | ---: | ---: |
| grasp_cream_cheese_bowl_flat_box_topdown_deep | 5 | 1 | 5 | 4/5 |
| cream_cheese_bowl_support_grounding | 5 | 1 | 5 | 4/5 |
| cream_cheese_bowl_support_geometry | 5 | 1 | 5 | 4/5 |
| cream_cheese_bowl_hover_drop_budget | 5 | 1 | 5 | 4/5 |
| cabinet_top_surface_geometry_explicit | 0 | 0 | 0 | — |
| grasp_bowl_plate_hollow_rim_topdown | 458 | 21 | 103 | 73/103 |
| grasp_wine_bottle_topdown_close_guard | 9 | 2 | 9 | 7/9 |
| grasp_wine_bottle_plate_topdown_close_guard | 3 | 1 | 3 | 3/3 |
| ground_wine_bottle_bowl_inner_floor | 9 | 2 | 9 | 7/9 |
| geometry_wine_bottle_bowl_inner_floor | 9 | 2 | 9 | 7/9 |
| place_wine_bottle_bowl_drop_budget | 9 | 2 | 9 | 7/9 |
| bowl_plate_hover_drop_budget | 15 | 1 | 4 | 2/4 |
| bowl_plate_next_to_plate_hover_drop_budget | 40 | 2 | 10 | 9/10 |
| grasp_object_basket_flat_box_topdown_deep | 30 | 6 | 28 | 19/28 |
| grasp_carton_upright_body_side | 20 | 4 | 20 | 20/20 |
| ground_cream_cheese_rack_top_region | 5 | 1 | 5 | 5/5 |
| geometry_cream_cheese_rack_top_region | 5 | 1 | 5 | 5/5 |
| grasp_cream_cheese_rack_flat_box_deep | 5 | 1 | 5 | 5/5 |

17/18 被选中过；9 条仅在 1 个 task 使用，5 条在 2 个 task 使用，3 条分别覆盖 4、6、21 个 task，1 条未使用。未使用的 `cabinet_top_surface_geometry_explicit` 只能判为本轮没有使用证据，不能判为能力失败。

## 每条 hint 的逐 task 结果与 trigger 配合

简称：goal_task/goal_swap、spatial_task/spatial_swap、object_task/object_swap 对应六个 LIBERO-PRO suites；T01–T10 对应日志 task01–task10。

每条 hint 只列非零使用 task；该 hint 在六 suite 的其余 task 上，实际选用次数和使用 episodes 均为 0。每个 task 总共测了 5 个 episode，表中分母是使用过该 hint 的 episode 数。

### grasp_cream_cheese_bowl_flat_box_topdown_deep

配合 trigger（query 次数）：`cream_cheese_bowl_wrong_object_intent`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_swap/T07 | Put the cream cheese on the bowl | 5 | 5 | 4/5 |

### cream_cheese_bowl_support_grounding

配合 trigger（query 次数）：`cream_cheese_bowl_wrong_object_intent`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_swap/T07 | Put the cream cheese on the bowl | 5 | 5 | 4/5 |

### cream_cheese_bowl_support_geometry

配合 trigger（query 次数）：`cream_cheese_bowl_wrong_object_intent`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_swap/T07 | Put the cream cheese on the bowl | 5 | 5 | 4/5 |

### cream_cheese_bowl_hover_drop_budget

配合 trigger（query 次数）：`cream_cheese_bowl_wrong_object_intent`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_swap/T07 | Put the cream cheese on the bowl | 5 | 5 | 4/5 |

### cabinet_top_surface_geometry_explicit

六个 suite 共 60 个 task 全为 0。

### grasp_bowl_plate_hollow_rim_topdown

配合 trigger（query 次数）：`bowl_plate_pick_lost_or_wrong_intent`：428；`black_bowl_not_between_wrong_object_handoff`：3；`black_bowl_next_to_plate_wrong_object_handoff`：16；`black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff`：5；`black_bowl_cabinet_top_to_plate_wrong_object_handoff`：6。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_swap/T04 | Put the bowl on the plate | 6 | 5 | 5/5 |
| spatial_swap/T01 | Pick the akita black bowl between the plate and the ramekin and place it on the plate | 7 | 5 | 5/5 |
| spatial_swap/T02 | Pick the akita black bowl from table center and place it on the plate | 6 | 5 | 5/5 |
| spatial_swap/T03 | Pick the akita black bowl in the top layer of the wooden cabinet and place it on the plate | 60 | 5 | 0/5 |
| spatial_swap/T04 | Pick the akita black bowl next to the cookies box and place it on the plate | 7 | 5 | 3/5 |
| spatial_swap/T05 | Pick the akita black bowl next to the plate and place it on the plate | 13 | 5 | 5/5 |
| spatial_swap/T06 | Pick the akita black bowl next to the ramekin and place it on the plate | 7 | 5 | 4/5 |
| spatial_swap/T07 | Pick the akita black bowl on the cookies box and place it on the plate | 157 | 5 | 0/5 |
| spatial_swap/T08 | Pick the akita black bowl on the ramekin and place it on the plate | 14 | 5 | 3/5 |
| spatial_swap/T09 | Pick the akita black bowl on the stove and place it on the plate | 6 | 5 | 4/5 |
| spatial_swap/T10 | Pick the akita black bowl on the wooden cabinet and place it on the plate | 5 | 5 | 4/5 |
| spatial_task/T01 | Pick the akita black bowl not between the plate and the ramekin and place it on the plate | 15 | 4 | 2/4 |
| spatial_task/T02 | Pick the akita black bowl next to the plate and place it on the plate | 27 | 5 | 4/5 |
| spatial_task/T03 | Pick the akita black bowl on the top of the wooden cabinet and place it on the plate | 23 | 5 | 4/5 |
| spatial_task/T04 | Pick the akita black bowl on the stove and place it on the plate | 7 | 5 | 4/5 |
| spatial_task/T05 | Pick the akita black bowl next to the ramekin and place it on the plate | 13 | 4 | 2/4 |
| spatial_task/T06 | Pick the akita black bowl next to the cookie box and place it on the plate | 18 | 5 | 4/5 |
| spatial_task/T07 | Pick the akita black bowl on the top of the cabinet and place it on the plate | 6 | 5 | 5/5 |
| spatial_task/T08 | Pick the akita black bowl on the cookie box and place it on the plate | 46 | 5 | 3/5 |
| spatial_task/T09 | Pick the akita black bowl on the top of the cabinet and place it on the plate | 6 | 5 | 3/5 |
| spatial_task/T10 | Pick the akita black bowl on the stove and place it on the plate | 9 | 5 | 4/5 |

### grasp_wine_bottle_topdown_close_guard

配合 trigger（query 次数）：`wine_bottle_bowl_wrong_object_handoff`：9。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T07 | put the wine bottle in the bowl | 4 | 4 | 4/4 |
| goal_task/T09 | put the wine bottle in the bowl | 5 | 5 | 3/5 |

### grasp_wine_bottle_plate_topdown_close_guard

配合 trigger（query 次数）：`wine_bottle_plate_wrong_object_handoff`：3。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T04 | Put the wine bottle on the plate | 3 | 3 | 3/3 |

### ground_wine_bottle_bowl_inner_floor

配合 trigger（query 次数）：`wine_bottle_bowl_wrong_object_handoff`：9。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T07 | put the wine bottle in the bowl | 4 | 4 | 4/4 |
| goal_task/T09 | put the wine bottle in the bowl | 5 | 5 | 3/5 |

### geometry_wine_bottle_bowl_inner_floor

配合 trigger（query 次数）：`wine_bottle_bowl_wrong_object_handoff`：9。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T07 | put the wine bottle in the bowl | 4 | 4 | 4/4 |
| goal_task/T09 | put the wine bottle in the bowl | 5 | 5 | 3/5 |

### place_wine_bottle_bowl_drop_budget

配合 trigger（query 次数）：`wine_bottle_bowl_wrong_object_handoff`：9。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T07 | put the wine bottle in the bowl | 4 | 4 | 4/4 |
| goal_task/T09 | put the wine bottle in the bowl | 5 | 5 | 3/5 |

### bowl_plate_hover_drop_budget

配合 trigger（query 次数）：`black_bowl_not_between_wrong_object_handoff`：3；`bowl_plate_pick_lost_or_wrong_intent`：12。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| spatial_task/T01 | Pick the akita black bowl not between the plate and the ramekin and place it on the plate | 15 | 4 | 2/4 |

### bowl_plate_next_to_plate_hover_drop_budget

配合 trigger（query 次数）：`black_bowl_next_to_plate_wrong_object_handoff`：16；`bowl_plate_pick_lost_or_wrong_intent`：24。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| spatial_swap/T05 | Pick the akita black bowl next to the plate and place it on the plate | 13 | 5 | 5/5 |
| spatial_task/T02 | Pick the akita black bowl next to the plate and place it on the plate | 27 | 5 | 4/5 |

### grasp_object_basket_flat_box_topdown_deep

配合 trigger（query 次数）：`object_basket_cream_tomato_q5_wrong_intent_window`：4；`object_basket_persistent_wrong_intent_group_a`：22；`object_basket_cream_cheese_precontact_wrong_intent`：4。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| object_swap/T03 | Pick the butter and place it in the basket | 5 | 5 | 4/5 |
| object_swap/T04 | Pick the chocolate pudding and place it in the basket | 6 | 5 | 3/5 |
| object_swap/T05 | Pick the cream cheese and place it in the basket | 4 | 4 | 2/4 |
| object_task/T01 | Pick the cream cheese and place it in the basket | 4 | 4 | 4/4 |
| object_task/T07 | Pick the butter and place it in the basket | 6 | 5 | 1/5 |
| object_task/T08 | Pick the chocolate pudding and place it in the basket | 5 | 5 | 5/5 |

### grasp_carton_upright_body_side

配合 trigger（query 次数）：`object_basket_bbq_orange_precontact_wrong_intent`：10；`object_basket_persistent_wrong_intent_group_a`：10。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| object_swap/T07 | Pick the milk and place it in the basket | 5 | 5 | 5/5 |
| object_swap/T08 | Pick the orange juice and place it in the basket | 5 | 5 | 5/5 |
| object_task/T03 | Pick the orange juice and place it in the basket | 5 | 5 | 5/5 |
| object_task/T06 | Pick the milk and place it in the basket | 5 | 5 | 5/5 |

### ground_cream_cheese_rack_top_region

配合 trigger（query 次数）：`cream_cheese_rack_wrong_object_handoff`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T08 | Put the cream cheese on the rack | 5 | 5 | 5/5 |

### geometry_cream_cheese_rack_top_region

配合 trigger（query 次数）：`cream_cheese_rack_wrong_object_handoff`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T08 | Put the cream cheese on the rack | 5 | 5 | 5/5 |

### grasp_cream_cheese_rack_flat_box_deep

配合 trigger（query 次数）：`cream_cheese_rack_wrong_object_handoff`：5。

| Suite/task | 实际任务指令 | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| goal_task/T08 | Put the cream cheese on the rack | 5 | 5 | 5/5 |

## 命名 profile 的实际选用

Profile 统计包含 trigger 本身提供的 profile（例如 repair），不限于 18 条 hint。相同名字但不同类别分开统计。

| Profile（类别:名称） | 选用次数 | task 数 | 使用 episodes | 其中最终成功 |
| --- | ---: | ---: | ---: | ---: |
| geometry_profiles:cream_cheese_bowl_support_geometry_v1 | 5 | 1 | 5 | 4/5 |
| geometry_profiles:wine_bottle_bowl_inner_floor_v1 | 9 | 2 | 9 | 7/9 |
| geometry_profiles:wine_rack_top_region_surface_v1 | 5 | 1 | 5 | 5/5 |
| grasp_profiles:carton_upright_body_side_v1 | 20 | 4 | 20 | 20/20 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | 35 | 7 | 33 | 23/33 |
| grasp_profiles:cream_cheese_flat_box_topdown_deeper_v2 | 5 | 1 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | 458 | 21 | 103 | 73/103 |
| grasp_profiles:libero_topdown | 12 | 3 | 12 | 10/12 |
| grounding_profiles:cream_cheese_bowl_support_v1 | 5 | 1 | 5 | 4/5 |
| grounding_profiles:wine_bottle_bowl_inner_floor_v1 | 9 | 2 | 9 | 7/9 |
| grounding_profiles:wine_rack_top_region_v1 | 5 | 1 | 5 | 5/5 |
| place_profiles:cream_cheese_bowl_hover_drop_budget_v1 | 5 | 1 | 5 | 4/5 |
| place_profiles:wine_bottle_bowl_drop_budget_v1 | 9 | 2 | 9 | 7/9 |
| repair_profiles:entry_lift_open_hand_small_v1 | 42 | 8 | 29 | 23/29 |
| repair_profiles:entry_topdown_orientation_reset_v1 | 5 | 1 | 5 | 5/5 |

### Profile 逐 task 明细

| Profile | Suite/task | 选用次数 | 使用 episodes | 其中最终成功 |
| --- | --- | ---: | ---: | ---: |
| geometry_profiles:cream_cheese_bowl_support_geometry_v1 | goal_swap/T07 | 5 | 5 | 4/5 |
| geometry_profiles:wine_bottle_bowl_inner_floor_v1 | goal_task/T07 | 4 | 4 | 4/4 |
| geometry_profiles:wine_bottle_bowl_inner_floor_v1 | goal_task/T09 | 5 | 5 | 3/5 |
| geometry_profiles:wine_rack_top_region_surface_v1 | goal_task/T08 | 5 | 5 | 5/5 |
| grasp_profiles:carton_upright_body_side_v1 | object_swap/T07 | 5 | 5 | 5/5 |
| grasp_profiles:carton_upright_body_side_v1 | object_swap/T08 | 5 | 5 | 5/5 |
| grasp_profiles:carton_upright_body_side_v1 | object_task/T03 | 5 | 5 | 5/5 |
| grasp_profiles:carton_upright_body_side_v1 | object_task/T06 | 5 | 5 | 5/5 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | goal_swap/T07 | 5 | 5 | 4/5 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | object_swap/T03 | 5 | 5 | 4/5 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | object_swap/T04 | 6 | 5 | 3/5 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | object_swap/T05 | 4 | 4 | 2/4 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | object_task/T01 | 4 | 4 | 4/4 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | object_task/T07 | 6 | 5 | 1/5 |
| grasp_profiles:cream_cheese_flat_box_topdown_deep_v1 | object_task/T08 | 5 | 5 | 5/5 |
| grasp_profiles:cream_cheese_flat_box_topdown_deeper_v2 | goal_task/T08 | 5 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | goal_swap/T04 | 6 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T01 | 7 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T02 | 6 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T03 | 60 | 5 | 0/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T04 | 7 | 5 | 3/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T05 | 13 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T06 | 7 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T07 | 157 | 5 | 0/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T08 | 14 | 5 | 3/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T09 | 6 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_swap/T10 | 5 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T01 | 15 | 4 | 2/4 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T02 | 27 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T03 | 23 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T04 | 7 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T05 | 13 | 4 | 2/4 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T06 | 18 | 5 | 4/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T07 | 6 | 5 | 5/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T08 | 46 | 5 | 3/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T09 | 6 | 5 | 3/5 |
| grasp_profiles:hollow_bowl_rim_topdown | spatial_task/T10 | 9 | 5 | 4/5 |
| grasp_profiles:libero_topdown | goal_task/T04 | 3 | 3 | 3/3 |
| grasp_profiles:libero_topdown | goal_task/T07 | 4 | 4 | 4/4 |
| grasp_profiles:libero_topdown | goal_task/T09 | 5 | 5 | 3/5 |
| grounding_profiles:cream_cheese_bowl_support_v1 | goal_swap/T07 | 5 | 5 | 4/5 |
| grounding_profiles:wine_bottle_bowl_inner_floor_v1 | goal_task/T07 | 4 | 4 | 4/4 |
| grounding_profiles:wine_bottle_bowl_inner_floor_v1 | goal_task/T09 | 5 | 5 | 3/5 |
| grounding_profiles:wine_rack_top_region_v1 | goal_task/T08 | 5 | 5 | 5/5 |
| place_profiles:cream_cheese_bowl_hover_drop_budget_v1 | goal_swap/T07 | 5 | 5 | 4/5 |
| place_profiles:wine_bottle_bowl_drop_budget_v1 | goal_task/T07 | 4 | 4 | 4/4 |
| place_profiles:wine_bottle_bowl_drop_budget_v1 | goal_task/T09 | 5 | 5 | 3/5 |
| repair_profiles:entry_lift_open_hand_small_v1 | goal_task/T04 | 3 | 3 | 3/3 |
| repair_profiles:entry_lift_open_hand_small_v1 | goal_task/T07 | 4 | 4 | 4/4 |
| repair_profiles:entry_lift_open_hand_small_v1 | goal_task/T09 | 5 | 5 | 3/5 |
| repair_profiles:entry_lift_open_hand_small_v1 | spatial_task/T01 | 3 | 3 | 1/3 |
| repair_profiles:entry_lift_open_hand_small_v1 | spatial_task/T02 | 16 | 3 | 2/3 |
| repair_profiles:entry_lift_open_hand_small_v1 | spatial_task/T03 | 5 | 5 | 4/5 |
| repair_profiles:entry_lift_open_hand_small_v1 | spatial_task/T07 | 5 | 5 | 5/5 |
| repair_profiles:entry_lift_open_hand_small_v1 | spatial_task/T09 | 1 | 1 | 1/1 |
| repair_profiles:entry_topdown_orientation_reset_v1 | goal_task/T08 | 5 | 5 | 5/5 |

## 可以得到的结论

1. **不能再把整个 pack 描述为“都只在单 task 使用”。** Bowl 抓取 hint 被 5 个 trigger 复用，覆盖 21 个 task、103 个 episode。Carton hint 在 milk/orange juice 的 task 与 swap 共 4 个 task 使用，20/20 episodes 最终成功；flat-box basket hint 覆盖 cream cheese/butter/pudding 的 6 个 task。
2. **确实存在很强的任务专用组件。** Cream cheese→bowl 的 grasp/grounding/geometry/place 四条均只在 goal-swap T07 使用；cream cheese→rack 的三条均只在 goal-task T08 使用；wine bottle→bowl 的四条覆盖 T07/T09，但两者指令相同。多个组件同时出现不等于多份独立泛化证据。
3. **复用广不等于效果稳定。** 同一个 hollow-bowl profile，在 spatial-swap T03（柜子上层）为 0/5，在 T07（cookies box 上）为 0/5；选用次数分别为 60、157。Between、table-center、next-to-plate 则分别为 5/5。这说明失败任务不是完全没选到通用 grasp hint；配置已选中，但整条 recovery 链仍失败。不能据此单独定位为 grasp profile 错误。
4. **Flat-box profile 同样存在对象/布局敏感性。** Basket butter：object-task T07 为 1/5、object-swap T03 为 4/5；pudding：task T08 为 5/5、swap T04 为 3/5。相同 profile 的选择，并未消除 task/swap 效果差异。它还被 cream cheese→bowl hint 使用，总计 7 个 task、33 episodes、23 个最终成功，属于跨 hint/goal 复用证据。
5. **本轮没有执行参数覆盖冲突证据。** `hint_conflicts` 仅出现 `params.source` 164 次与 `params.notes` 16 次，属于来源/说明字段；未记录 grasp/place/geometry 等执行参数冲突。但这不排除语义层面的职责重复或参数组合不合适。

下一步若要评估每个组件的泛化与独立贡献，应固定同一个 trigger 和接管前状态，在 held-out 对象/布局/goal 上比较默认 profile、当前 profile、替换/移除 hint，并分别记录 grounding、grasp、lift、place 的阶段结果。

## 审计产物与复现

- 原始逐 query 选择、18 条定义、逐 task 数据：`libero_pro_c4_recovery_hint_usage.json`。
- 统计脚本：`tmp/inspire/analyze_recovery_hint_usage.py`；取数桥接：`tmp/inspire/run_hint_audit_jupyter.py`。
- 启智只使用 `可上网GPU资源` 的 `xinghanbo-eval`，未修改 checkpoint、评测代码或重跑 episode。
- SSH 初始化失败后，使用已安装 Inspire 包的 Jupyter terminal transport 读取同实例日志；不涉及其他实例。
