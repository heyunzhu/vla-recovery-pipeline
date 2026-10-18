# C4：单 task 使用与语义/触发重叠统计

## 口径

范围：C4 冻结 pack 全部 36 条 skill，300 episodes，8,107 queries，594 次实际接管。Task 定义为 suite + task ID；Trigger 使用是 winner，Hint 使用是接管配置来源中实际被合并。单 task 使用不等于只在该 task 语义匹配，更不等于严格证明不能泛化。同一指令的两个 task ID 计为两个 task，因此此口径可能高估语义使用广度。

## 1. 使用 task 数分布

| 类型 | 0 task | 仅 1 task | 至少 2 tasks | 总数 |
| --- | ---: | ---: | ---: | ---: |
| Trigger | 2 | 9 | 7 | 18 |
| Recovery hint | 1 | 9 | 8 | 18 |
| 全部 | 3 | 18 | 15 | 36 |

仅 1 task：18/36 = 50.0%；排除 3 条未使用 skill 后，为 18/33 = 54.5%。包括未使用条目在内，最多 1 task 的有 21/36 = 58.3%，但不能将其称作“21 条只在一个 task 使用”。

### 18 条单 task skill 的完整清单

| Skill ID | 类型 | 唯一实际使用 task |
| --- | --- | --- |
| cream_cheese_bowl_wrong_object_intent | Trigger | libero_goal_swap/task07 |
| grasp_cream_cheese_bowl_flat_box_topdown_deep | Hint | libero_goal_swap/task07 |
| cream_cheese_bowl_support_grounding | Hint | libero_goal_swap/task07 |
| cream_cheese_bowl_support_geometry | Hint | libero_goal_swap/task07 |
| cream_cheese_bowl_hover_drop_budget | Hint | libero_goal_swap/task07 |
| plate_stove_open_wrong_intent_pregrasp_handoff | Trigger | libero_goal_task/task05 |
| wine_bottle_plate_wrong_object_handoff | Trigger | libero_goal_task/task04 |
| grasp_wine_bottle_plate_topdown_close_guard | Hint | libero_goal_task/task04 |
| black_bowl_not_between_wrong_object_handoff | Trigger | libero_spatial_task/task01 |
| bowl_plate_hover_drop_budget | Hint | libero_spatial_task/task01 |
| black_bowl_next_to_plate_wrong_object_handoff | Trigger | libero_spatial_task/task02 |
| black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | Trigger | libero_spatial_task/task03 |
| object_basket_cream_cheese_precontact_wrong_intent | Trigger | libero_object_swap/task05 |
| object_basket_tomato_persistent_wrong_intent | Trigger | libero_object_swap/task10 |
| cream_cheese_rack_wrong_object_handoff | Trigger | libero_goal_task/task08 |
| ground_cream_cheese_rack_top_region | Hint | libero_goal_task/task08 |
| geometry_cream_cheese_rack_top_region | Hint | libero_goal_task/task08 |
| grasp_cream_cheese_rack_flat_box_deep | Hint | libero_goal_task/task08 |

## 2. 语义相近的判断

本次是基于 pack 定义的定性审计，不是 embedding 相似度分数。分别比较任务对象、goal、空间关系、失败模式、动态触发门限及引用实现；不能仅凭 skill ID 含相同词就判为功能重复。

- Bowl→plate 族：通用 bowl trigger 与 not-between、next-to-plate、cabinet-top、wooden-cabinet-top、cookies-box 专用 trigger 共享目标物体与 goal；专用规则进一步限定空间关系。通用规则实际要求目标距离与预测距离较近，而 cabinet 规则要求预测距离较远，动态条件并不相同。
- Cabinet-top 与 wooden-cabinet-top early：目标/goal/失败模式高度相近，后者语言范围更窄，距离与 intent 门限不同，优先级 78 vs 72；存在一次实际竞争。
- Basket 族：多数针对持续 wrong-object intent，但对象白名单不同；cream-cheese 专用规则与 cream/tomato q5 规则对象重合。前者 nearest-pickable distance 为 (0.10,0.16)，后者为 (0.20,0.24)，同一状态不可能同时满足这两个距离区间。
- Wine bottle→bowl/plate：对象与 wrong-object handoff 相近，但 goal 不同；语义族相近不等于相同 query 可匹配。
- Hint：同一任务的 grasp、grounding、geometry、place 是不同职责的配套组件，不能因为一起使用就判为重复。Flat-box bowl/basket 两条 grasp hint 共享 `cream_cheese_flat_box_topdown_deep_v1`；wine bottle bowl/plate 两条 grasp hint 共享 `libero_topdown` 与 close guard，是实现复用/可能抽象合并的候选，但其 goal 范围不同。

## 3. 两层触发重叠

`applies_to` 共同通过表示规则同时适用于当前任务/对象/goal，即语义/适用范围重叠。`would_fire` 共同通过表示同一个 query 的状态还同时满足动态接管门限，即真实触发竞争候选。Winner 一般只有一个，不能用“两个 winner 是否同时出现”统计竞争。

| 层次 | 统计 |
| --- | --- |
| 至少两个 Trigger 的 applies_to 通过 | 1,664/8,107 queries（20.5%） |
| 出现过共同 applies_to 的不同 Trigger pair | 8 对，涉及 9 条 Trigger |
| 至少两个 Trigger 同时 would_fire | 1/8,107 queries（约 0.012%） |
| 已发生接管中存在另一 would_fire 候选 | 1/594（约 0.17%） |

### 全部 8 对实测重叠

| Trigger A | Trigger B | 共同 applies_to queries | 共同 would_fire queries |
| --- | --- | ---: | ---: |
| black_bowl_cabinet_top_to_plate_wrong_object_handoff | bowl_plate_pick_lost_or_wrong_intent | 588 | 0 |
| black_bowl_cabinet_top_to_plate_wrong_object_handoff | black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | 404 | 1 |
| black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | bowl_plate_pick_lost_or_wrong_intent | 404 | 0 |
| bowl_cookie_box_wrong_bowl_handoff | bowl_plate_pick_lost_or_wrong_intent | 383 | 0 |
| object_basket_cream_cheese_precontact_wrong_intent | object_basket_cream_tomato_q5_wrong_intent_window | 264 | 0 |
| black_bowl_next_to_plate_wrong_object_handoff | bowl_plate_pick_lost_or_wrong_intent | 183 | 0 |
| black_bowl_not_between_wrong_object_handoff | bowl_plate_pick_lost_or_wrong_intent | 178 | 0 |
| object_basket_cream_tomato_q5_wrong_intent_window | object_basket_tomato_persistent_wrong_intent | 68 | 0 |

Pair 次数不能相加当作不同 query 数：同一个 query 可同时适用三个 Trigger，贡献三个 pair。

唯一共同 would_fire 的记录：`libero_spatial_task/task03/ep03`，query 6。Cabinet-top 与 wooden-cabinet-top early 两条都满足动态条件；winner 为 wooden-cabinet early（priority 78），另一条为 priority 72。通用 bowl Trigger 在该 query 也通过 applies_to，但没有 would_fire。

## 4. Hint 的重叠不能解释为 Trigger 竞争

594 次接管的 hint provenance 中，同类 hint（按 pack 路径 grasp/grounding/geometry/place 分类）同时选中两个或以上的 query 数为 0；存在跨职责共同选用，例如 bowl grasp + next-to-plate place 共 40 次、bowl grasp + not-between place 共 15 次、wine→bowl 的四条配套 hint 各共用 9 次。这些是组合执行配置，不是抢接管资格。

日志中的合并冲突只记录到 `params.source` 164 次和 `params.notes` 16 次；未出现已记录的执行参数覆盖冲突。这不证明不存在职责重复或错误组合，也不代表对全部非接管 query 做过 hint 静态共匹配审计。

## 结论与限制

已有证据支持“相当一部分条目本轮使用范围窄、语义相近规则的适用范围确有重叠”，但不支持“严重的实时触发竞争”：共同动态触发仅一次。更符合数据的工作假设是：多个语义相近的专用规则被不同对象/空间关系/距离和时间窗条件切分，形成局部覆盖。是否存在可合并冗余，以及是否造成泛化弱，仍须合并/移除规则消融与 held-out 测试验证。

来源：`tmp/inspire/skill_overlap_c4.json`、冻结 pack 的 skill frontmatter、`docs/results/libero_pro_c4_recovery_hint_usage.json`。本次仅分析本地已核验产物，没有启动实例或新增评测。
