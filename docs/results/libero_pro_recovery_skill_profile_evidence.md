# Recovery skill 与 profile：使用证据与泛化边界

## 口径

C4 含 18 个 trigger 与 18 个 recovery hints。Trigger 决定何时接管；hint 也有 `applies_to`，匹配后提供抓取、放置、grounding 或 geometry 参数；profile 是这些参数引用的实现。多个 hint 会合并，标量覆盖与列表合并记录在 `hint_conflicts` 中。

此前“hint 没有自己的 applies_to”的说法错误。Hint 不独立成为接管 winner，但可以独立匹配并被多个 trigger 复用。

Trigger 的逐 task 数值见 `libero_pro_c4_skill_task_level_trigger_matrix.csv`。其中 winner-success 是该 skill 在 episode 中至少一次成为 winner后，episode 最终成功的数量；同一 episode 可包含多个 trigger，不能相加当作独立 rescue 数。

当前未系统核对全部评测任务是否参与过历史 mining、调参或 hint 构建，所以以下是使用范围和效果，不能直接当作 held-out 泛化成绩。

## 18 个 trigger 的实测范围

| Trigger（简写） | 实际 winner 范围 | 最终成功 / winner episodes | 可以说什么 |
| --- | --- | ---: | --- |
| bowl_plate_pick_lost_or_wrong_intent | goal-swap T4；spatial-task/swap 各 T1–T10 | 63/92 | 使用范围最广，布局效果差异大 |
| black_bowl_not_between_wrong_object_handoff | spatial-task T1 | 1/3 | 单模板，执行不稳 |
| black_bowl_next_to_plate_wrong_object_handoff | spatial-task T2 | 2/3 | 单模板；swap T5 不触发 |
| black_bowl_cabinet_top_to_plate_wrong_object_handoff | spatial-task T7/T9（相同指令） | 6/6 | 同语义模板的两个 task ID |
| black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | spatial-task T3 | 4/5 | 单模板；swap T3/T10 不触发 |
| bowl_cookie_box_wrong_bowl_handoff | 无 | — | 383 applicable queries，但未触发 |
| bowl_cabinet_target_holding_handoff | 无 | — | 当前样本中没有 applicability coverage |
| cream_cheese_bowl_wrong_object_intent | goal-swap T7 | 4/5 | 单 object-goal 模板 |
| cream_cheese_rack_wrong_object_handoff | goal-task T8 | 5/5 | 单 object-goal 模板 |
| plate_stove_open_wrong_intent_pregrasp_handoff | goal-task T5 | 0/5 | 触发后无成功证据 |
| wine_bottle_bowl_wrong_object_handoff | goal-task T7/T9（相同指令） | 7/9 | 同语义模板的两个 task ID |
| wine_bottle_plate_wrong_object_handoff | goal-task T4 | 3/3 | 单 object-goal 模板 |
| object_basket_persistent_wrong_intent_group_a | object-task 4种对象、object-swap 5种对象 | 38/45 | 跨多对象与 task/swap 使用，非 held-out object 证据 |
| object_basket_bbq_orange_precontact_wrong_intent | 两 suite 各 BBQ/orange | 20/20 | 当前已测变体表现强 |
| object_basket_salad_dressing_precontact_wrong_intent | 两 suite 各 salad dressing | 9/10 | 当前已测变体表现好 |
| object_basket_cream_cheese_precontact_wrong_intent | object-swap cream cheese | 2/4 | 单变体，效果有限 |
| object_basket_tomato_persistent_wrong_intent | object-swap tomato | 5/5 | 单变体；task 版本靠另一 trigger |
| object_basket_cream_tomato_q5_wrong_intent_window | object-task cream cheese/tomato | 9/9 | 同 suite 两对象；swap 中不触发 |

## 18 个 recovery hints 的定义与复用范围

这里描述静态匹配定义，不能把定义范围当作已执行范围。全量实际选用统计已补齐，见 [18 条 hint 与 profile 逐 task 使用报告](libero_pro_c4_recovery_hint_usage_report.md)。C4 的 300 episodes / 594 次接管 query 中，17/18 条 hint 被选中过；下方静态表保留作为定义对照。

| Hint | 输出或引用实现 | 定义覆盖范围 |
| --- | --- | --- |
| grasp_bowl_plate_hollow_rim_topdown | hollow_bowl_rim_topdown | 黑 bowl→plate，跨空间关系 |
| grasp_carton_upright_body_side | carton_upright_body_side_v1 | upright milk/orange juice；没有限定 goal |
| grasp_object_basket_flat_box_topdown_deep | cream_cheese_flat_box_topdown_deep_v1 | cream cheese/butter/pudding→basket |
| grasp_cream_cheese_bowl_flat_box_topdown_deep | cream_cheese_flat_box_topdown_deep_v1 | cream cheese→bowl |
| grasp_cream_cheese_rack_flat_box_deep | cream_cheese_flat_box_topdown_deeper_v2 | cream cheese→rack |
| grasp_wine_bottle_topdown_close_guard | libero_topdown + grasp_close_max_above_m=0.18 | wine bottle→bowl |
| grasp_wine_bottle_plate_topdown_close_guard | libero_topdown + grasp_close_max_above_m=0.18 | wine bottle→plate |
| cream_cheese_bowl_support_grounding | cream_cheese_bowl_support_v1 | cream cheese→bowl |
| ground_wine_bottle_bowl_inner_floor | wine_bottle_bowl_inner_floor_v1 | wine bottle→bowl |
| ground_cream_cheese_rack_top_region | wine_rack_top_region_v1 | cream cheese→rack |
| cream_cheese_bowl_support_geometry | cream_cheese_bowl_support_geometry_v1 | cream cheese→bowl |
| geometry_wine_bottle_bowl_inner_floor | wine_bottle_bowl_inner_floor_v1 | wine bottle→bowl |
| geometry_cream_cheese_rack_top_region | wine_rack_top_region_surface_v1 | cream cheese→rack |
| cabinet_top_surface_geometry_explicit | 显式 cabinet-top placement region | bowl→cabinet top |
| cream_cheese_bowl_hover_drop_budget | cream_cheese_bowl_hover_drop_budget_v1 | cream cheese→bowl |
| place_wine_bottle_bowl_drop_budget | wine_bottle_bowl_drop_budget_v1 | wine bottle→bowl |
| bowl_plate_hover_drop_budget | place_* executor 参数 | not-between bowl→plate |
| bowl_plate_next_to_plate_hover_drop_budget | place_* executor 参数 | next-to-plate bowl→plate |

## 已直接核对的 profile 使用样本

C4 spatial-task T1/ep00，query 5：

- Trigger：`black_bowl_not_between_wrong_object_handoff`。
- 合并 hint：`grasp_bowl_plate_hollow_rim_topdown` 与 `bowl_plate_hover_drop_budget`。
- Grasp profile：`hollow_bowl_rim_topdown`。
- Repair profile：`entry_lift_open_hand_small_v1`。
- Place：显式 place lift/hover/drop/release budget 参数，无需独立 place_profile 名称。
- `hint_sources` 明确记录以上来源；该 query 的冲突只涉及 provenance 的 `params.source`，不能据此声称执行参数冲突。

Profile 被合并进方案表示被选用；实际是否走到其执行阶段还需结合 recovery_trace 与规划器日志确认。一次成功也不能证明每个组件独立有效。

## 最强的失败证据及仍未知的内容

通用 bowl trigger 在 spatial-swap T3（柜子上层）与 T7（cookies box）均成为 winner 5/5，但最终均为0/5。相对地，同一 trigger 在 between、table-center、next-to-plate 任务均为5/5。这是整个 recovery 链对布局高度敏感的实测证据；无法仅凭它定位到 trigger 或 grasp profile。

BBQ/orange 是20/20；group-A 是38/45，但 butter 的 task/swap 分别为1/5、4/5。这证明即使共享一个 trigger，组合执行效果仍可随对象与布局明显变化。

每个 trigger 的未见语言、对象、goal、组合泛化都仍未知。每个 profile 的独立贡献与泛化也仍未知，需要固定 trigger与触发前状态，对 profile 做替换或移除消融，记录 grasp/lift/place阶段成功，而不是直接用最终 episode success 归功于某个 profile。
