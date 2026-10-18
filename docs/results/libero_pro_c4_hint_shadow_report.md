# C4 全 36 条 skill：补齐 recovery hint 的匹配、选择和恢复入口

## 先读这一段

Trigger 决定“是否请求接管”；recovery hint 决定“若接管，用什么抓取/定位/几何/放置配置”。Hint 没有独立的动态 trigger，因此不能把 hint 条件匹配称为已经触发机器人动作。

本次补读 BASELINE 与 C4 各 300 个 episode，共 600 个。用同一个冻结 C4 pack 在每个记录的 VLA query 上旁路匹配，不派发 backend、不执行动作。BASELINE 的匹配仅是假设 C4 pack 在这些状态上会适用，不是 BASELINE 真用了 hint。

## 指标是什么意思

| 指标 | 简单含义 |
| --- | --- |
| 匹配 task/episode/query | 至少一次满足该 hint 的 applies_to；query 是一次 VLA 预测检查点 |
| 无 trigger 的匹配 | hint 适用，但这个检查点没有任何 trigger 满足动态条件，因此不会因此接管 |
| 决策选择 | hook 请求接管后，hint ID 被记录在 hint_sources 中 |
| 实际恢复入口 | 上述 hint 被选用，且该 query 的 mode=recovery；不代表抓取或放置阶段一定执行到/成功 |
| 配置保留 | hint 声明的执行字段在最终合并配置中仍保持原值；排除 source、notes、target 元数据，不是物理阶段成功率 |
| 同职责重叠 | 同一个检查点有两个 scope 相同的 hint 匹配，是候选冗余/冲突信号 |
| 跨职责共同匹配 | 例如 grasp+geometry+place 同时匹配，可能是正常组合，不直接视为重复 |

## 总体统计

| 项目 | BASELINE 旁路 | C4 |
| --- | ---: | ---: |
| 检查点总数 | 15112 | 8107 |
| 有 hint 匹配的检查点 | 8590 | 3704 |
| hint 匹配但无 trigger 的检查点 | 6034 | 3174 |
| 多个 hint 共同匹配的检查点 | 1819 | 729 |
| 同职责多个 hint 共同匹配的检查点 | 0 | 0 |
| 至少一个 trigger 满足动态条件的检查点 | 3321 | 594 |
| 实际恢复入口数 | 0 | 269 |
| 实际进入恢复的 episode 数 | 0 | 223 |
| 至少一个 hint 条件不可判定的检查点 | 300 | 300 |

次数按检查点计，不是 task 数；同一 hint 可以在一个长 episode 内反复匹配。BASELINE/C4 轨迹长度不同，不把两组原始 query 数之差解释为能力变化。

## 当前能得到的结论

1. Hint 的适用并不等于接管：C4 的 3,704 个有 hint 匹配的检查点中，3,174 个（85.7%）没有 trigger 满足动态条件。这些可能只是正常运行状态，不能据此说触发机制漏救。
2. Hint 的范围窄不只是 trigger 不放行：两组轨迹上，18 条 hint 都是 1 条零匹配、9 条只匹配一个 task、8 条匹配多个 task；C4 每条 hint 的匹配 task 集合与选择/实际恢复 task 集合相同。现有数据中未发现“匹配了新 task，但只因 trigger 未触发而完全没用到”的 task 级落差。
3. 检查全部 153 对 hint，两组都是 0 对同职责共同匹配、17 对跨职责共同匹配。条件有分区、职责有组合，是本次观察；不证明语义无重复，也不证明 profile 具有强泛化。
4. 宽范围例子：grasp_bowl_plate_hollow_rim_topdown 匹配 21 个 task，C4 有 2,265 次匹配、458 次决策选择、145 次实际恢复入口（103 个 episode）；不能把 458 当作物理恢复次数。窄范围例子：cream-cheese→bowl 的四条 hint 都只匹配 goal_swap/task07，90 次匹配、5 次选择/恢复入口；四条分属 grasp/grounding/geometry/place，是同任务的配置组合。
5. 所有实际恢复入口中被选用的 hint，其声明的执行字段均保持在合并配置中，未发现字段覆盖；尚不能证明每个字段对应的动作阶段真正执行到了。
6. 不可判定只涉及 grasp_carton_upright_body_side，在 goal_swap/task01（Open the middle layer of the drawer）上两组各 300 个 query（5 个 episode）；目标物体相关信息缺失，不将此情况当成确定不匹配。其余 hint 在这些检查点为确定不匹配，因此未制造潜在的同职责双匹配。

## 18 条 hint 完整表（零使用也保留）

| Hint 完整 ID | 职责 | B 匹配 task 数 | C4 匹配 task 数 | C4 匹配 query | C4 匹配但无 trigger | C4 决策选择 | C4 实际恢复入口 | 恢复 episode | 恢复 task 数 | 配置完整保留入口 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| bowl_plate_hover_drop_budget | place | 1 | 1 | 178 | 163 | 15 | 8 | 4 | 1 | 8 |
| bowl_plate_next_to_plate_hover_drop_budget | place | 2 | 2 | 183 | 143 | 40 | 16 | 10 | 2 | 16 |
| cabinet_top_surface_geometry_explicit | geometry | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| cream_cheese_bowl_hover_drop_budget | place | 1 | 1 | 90 | 85 | 5 | 5 | 5 | 1 | 5 |
| cream_cheese_bowl_support_geometry | geometry | 1 | 1 | 90 | 85 | 5 | 5 | 5 | 1 | 5 |
| cream_cheese_bowl_support_grounding | grounding | 1 | 1 | 90 | 85 | 5 | 5 | 5 | 1 | 5 |
| geometry_cream_cheese_rack_top_region | geometry | 1 | 1 | 42 | 37 | 5 | 5 | 5 | 1 | 5 |
| geometry_wine_bottle_bowl_inner_floor | geometry | 2 | 2 | 236 | 227 | 9 | 9 | 9 | 2 | 9 |
| grasp_bowl_plate_hollow_rim_topdown | grasp | 21 | 21 | 2265 | 1807 | 458 | 145 | 103 | 21 | 145 |
| grasp_carton_upright_body_side | grasp | 4 | 4 | 131 | 111 | 20 | 20 | 20 | 4 | 20 |
| grasp_cream_cheese_bowl_flat_box_topdown_deep | grasp | 1 | 1 | 90 | 85 | 5 | 5 | 5 | 1 | 5 |
| grasp_cream_cheese_rack_flat_box_deep | grasp | 1 | 1 | 42 | 37 | 5 | 5 | 5 | 1 | 5 |
| grasp_object_basket_flat_box_topdown_deep | grasp | 6 | 6 | 800 | 770 | 30 | 30 | 28 | 6 | 30 |
| grasp_wine_bottle_plate_topdown_close_guard | grasp | 1 | 1 | 140 | 137 | 3 | 3 | 3 | 1 | 3 |
| grasp_wine_bottle_topdown_close_guard | grasp | 2 | 2 | 236 | 227 | 9 | 9 | 9 | 2 | 9 |
| ground_cream_cheese_rack_top_region | grounding | 1 | 1 | 42 | 37 | 5 | 5 | 5 | 1 | 5 |
| ground_wine_bottle_bowl_inner_floor | grounding | 2 | 2 | 236 | 227 | 9 | 9 | 9 | 2 | 9 |
| place_wine_bottle_bowl_drop_budget | place | 2 | 2 | 236 | 227 | 9 | 9 | 9 | 2 | 9 |

## Hint 之间共同匹配：同职责与跨职责分开看

### BASELINE

检查了全部 153 对 hint：有共同匹配的同职责组合 0 对，跨职责组合 17 对。未列出的组合共同匹配为零。

| A | B | 同职责？ | 共同匹配 query | 共同匹配 ep | task | 有 trigger | 共同被选用 | 共同实际恢复入口 |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| geometry_wine_bottle_bowl_inner_floor | grasp_wine_bottle_topdown_close_guard | 否 | 600 | 10 | goal_task:T07；goal_task:T09 | 50 | 0 | 0 |
| geometry_wine_bottle_bowl_inner_floor | ground_wine_bottle_bowl_inner_floor | 否 | 600 | 10 | goal_task:T07；goal_task:T09 | 50 | 0 | 0 |
| geometry_wine_bottle_bowl_inner_floor | place_wine_bottle_bowl_drop_budget | 否 | 600 | 10 | goal_task:T07；goal_task:T09 | 50 | 0 | 0 |
| grasp_wine_bottle_topdown_close_guard | ground_wine_bottle_bowl_inner_floor | 否 | 600 | 10 | goal_task:T07；goal_task:T09 | 50 | 0 | 0 |
| grasp_wine_bottle_topdown_close_guard | place_wine_bottle_bowl_drop_budget | 否 | 600 | 10 | goal_task:T07；goal_task:T09 | 50 | 0 | 0 |
| ground_wine_bottle_bowl_inner_floor | place_wine_bottle_bowl_drop_budget | 否 | 600 | 10 | goal_task:T07；goal_task:T09 | 50 | 0 | 0 |
| bowl_plate_next_to_plate_hover_drop_budget | grasp_bowl_plate_hollow_rim_topdown | 否 | 379 | 10 | spatial_swap:T05；spatial_task:T02 | 71 | 0 | 0 |
| cream_cheese_bowl_hover_drop_budget | cream_cheese_bowl_support_geometry | 否 | 300 | 5 | goal_swap:T07 | 90 | 0 | 0 |
| cream_cheese_bowl_hover_drop_budget | cream_cheese_bowl_support_grounding | 否 | 300 | 5 | goal_swap:T07 | 90 | 0 | 0 |
| cream_cheese_bowl_hover_drop_budget | grasp_cream_cheese_bowl_flat_box_topdown_deep | 否 | 300 | 5 | goal_swap:T07 | 90 | 0 | 0 |
| cream_cheese_bowl_support_geometry | cream_cheese_bowl_support_grounding | 否 | 300 | 5 | goal_swap:T07 | 90 | 0 | 0 |
| cream_cheese_bowl_support_geometry | grasp_cream_cheese_bowl_flat_box_topdown_deep | 否 | 300 | 5 | goal_swap:T07 | 90 | 0 | 0 |
| cream_cheese_bowl_support_grounding | grasp_cream_cheese_bowl_flat_box_topdown_deep | 否 | 300 | 5 | goal_swap:T07 | 90 | 0 | 0 |
| geometry_cream_cheese_rack_top_region | grasp_cream_cheese_rack_flat_box_deep | 否 | 300 | 5 | goal_task:T08 | 41 | 0 | 0 |
| geometry_cream_cheese_rack_top_region | ground_cream_cheese_rack_top_region | 否 | 300 | 5 | goal_task:T08 | 41 | 0 | 0 |
| grasp_cream_cheese_rack_flat_box_deep | ground_cream_cheese_rack_top_region | 否 | 300 | 5 | goal_task:T08 | 41 | 0 | 0 |
| bowl_plate_hover_drop_budget | grasp_bowl_plate_hollow_rim_topdown | 否 | 240 | 5 | spatial_task:T01 | 110 | 0 | 0 |
### C4

检查了全部 153 对 hint：有共同匹配的同职责组合 0 对，跨职责组合 17 对。未列出的组合共同匹配为零。

| A | B | 同职责？ | 共同匹配 query | 共同匹配 ep | task | 有 trigger | 共同被选用 | 共同实际恢复入口 |
| --- | --- | --- | ---: | ---: | --- | ---: | ---: | ---: |
| geometry_wine_bottle_bowl_inner_floor | grasp_wine_bottle_topdown_close_guard | 否 | 236 | 10 | goal_task:T07；goal_task:T09 | 9 | 9 | 9 |
| geometry_wine_bottle_bowl_inner_floor | ground_wine_bottle_bowl_inner_floor | 否 | 236 | 10 | goal_task:T07；goal_task:T09 | 9 | 9 | 9 |
| geometry_wine_bottle_bowl_inner_floor | place_wine_bottle_bowl_drop_budget | 否 | 236 | 10 | goal_task:T07；goal_task:T09 | 9 | 9 | 9 |
| grasp_wine_bottle_topdown_close_guard | ground_wine_bottle_bowl_inner_floor | 否 | 236 | 10 | goal_task:T07；goal_task:T09 | 9 | 9 | 9 |
| grasp_wine_bottle_topdown_close_guard | place_wine_bottle_bowl_drop_budget | 否 | 236 | 10 | goal_task:T07；goal_task:T09 | 9 | 9 | 9 |
| ground_wine_bottle_bowl_inner_floor | place_wine_bottle_bowl_drop_budget | 否 | 236 | 10 | goal_task:T07；goal_task:T09 | 9 | 9 | 9 |
| bowl_plate_next_to_plate_hover_drop_budget | grasp_bowl_plate_hollow_rim_topdown | 否 | 183 | 10 | spatial_swap:T05；spatial_task:T02 | 40 | 40 | 16 |
| bowl_plate_hover_drop_budget | grasp_bowl_plate_hollow_rim_topdown | 否 | 178 | 5 | spatial_task:T01 | 15 | 15 | 8 |
| cream_cheese_bowl_hover_drop_budget | cream_cheese_bowl_support_geometry | 否 | 90 | 5 | goal_swap:T07 | 5 | 5 | 5 |
| cream_cheese_bowl_hover_drop_budget | cream_cheese_bowl_support_grounding | 否 | 90 | 5 | goal_swap:T07 | 5 | 5 | 5 |
| cream_cheese_bowl_hover_drop_budget | grasp_cream_cheese_bowl_flat_box_topdown_deep | 否 | 90 | 5 | goal_swap:T07 | 5 | 5 | 5 |
| cream_cheese_bowl_support_geometry | cream_cheese_bowl_support_grounding | 否 | 90 | 5 | goal_swap:T07 | 5 | 5 | 5 |
| cream_cheese_bowl_support_geometry | grasp_cream_cheese_bowl_flat_box_topdown_deep | 否 | 90 | 5 | goal_swap:T07 | 5 | 5 | 5 |
| cream_cheese_bowl_support_grounding | grasp_cream_cheese_bowl_flat_box_topdown_deep | 否 | 90 | 5 | goal_swap:T07 | 5 | 5 | 5 |
| geometry_cream_cheese_rack_top_region | grasp_cream_cheese_rack_flat_box_deep | 否 | 42 | 5 | goal_task:T08 | 5 | 5 | 5 |
| geometry_cream_cheese_rack_top_region | ground_cream_cheese_rack_top_region | 否 | 42 | 5 | goal_task:T08 | 5 | 5 | 5 |
| grasp_cream_cheese_rack_flat_box_deep | ground_cream_cheese_rack_top_region | 否 | 42 | 5 | goal_task:T08 | 5 | 5 | 5 |

## 每条 hint 的具体 task 数据

Task 按 suite+ID 计。同一个指令在不同 ID 下仍算两个 task，不等于两个不同语义；匹配跨度是适用范围，不是成功泛化的直接证据。每个 task 有 5 个 episode。仅省略 B/C4 均零匹配、零选择且无不可判定条件的 task；JSON 包含全部 60×18 格。

### bowl_plate_hover_drop_budget

职责：place；声明 profile：无命名 profile，直接提供参数。

声明的执行配置：`{"params.executor.place_lift_max_steps":70,"params.executor.place_lift_reached_m":0.014,"params.executor.place_lift_min_clearance_m":0.03,"params.executor.place_hover_clearance_m":0.055,"params.executor.place_hover_max_steps":90,"params.executor.place_hover_reached_m":0.014,"params.executor.place_drop_max_steps":120,"params.executor.place_drop_reached_m":0.018,"params.executor.place_release_z_max_m":0.1,"params.executor.place_open_dwell_steps":8}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_spatial_task/task01 | Pick the akita black bowl not between the plate and the ramekin and place it on the plate | 5/240 | 5/178 | 163 | 15 | 4/8 | 2/4 | 0/0 |
### bowl_plate_next_to_plate_hover_drop_budget

职责：place；声明 profile：无命名 profile，直接提供参数。

声明的执行配置：`{"params.executor.place_lift_max_steps":70,"params.executor.place_lift_reached_m":0.014,"params.executor.place_lift_min_clearance_m":0.03,"params.executor.place_hover_clearance_m":0.055,"params.executor.place_hover_max_steps":90,"params.executor.place_hover_reached_m":0.014,"params.executor.place_drop_max_steps":120,"params.executor.place_drop_reached_m":0.018,"params.executor.place_release_z_max_m":0.1,"params.executor.place_open_dwell_steps":8}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_spatial_swap/task05 | Pick the akita black bowl next to the plate and place it on the plate | 5/139 | 5/79 | 66 | 13 | 5/7 | 5/5 | 0/0 |
| libero_spatial_task/task02 | Pick the akita black bowl next to the plate and place it on the plate | 5/240 | 5/104 | 77 | 27 | 5/9 | 4/5 | 0/0 |
### cabinet_top_surface_geometry_explicit

职责：geometry；声明 profile：无命名 profile，直接提供参数。

声明的执行配置：`{"params.geometry_hints.placement_region.relation":"on","params.geometry_hints.placement_region.surface_name":"wooden_cabinet_1_cabinet_top","params.geometry_hints.placement_region.source_object":"wooden_cabinet_1_main","params.geometry_hints.placement_region.shape":"box","params.geometry_hints.placement_region.shrink_xy_m":0.012,"params.geometry_hints.placement_region.top_offset_m":0.012,"params.geometry_hints.placement_region.thickness_m":0.012,"params.geometry_hints.placement_region.place_z_offset_m":0.14}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 全部 60 个 task | 均未匹配/选用 | 0/0 | 0/0 | 0 | 0 | 0/0 | — | 0/0 |
### cream_cheese_bowl_hover_drop_budget

职责：place；声明 profile：cream_cheese_bowl_hover_drop_budget_v1。

声明的执行配置：`{"params.place_profile":"cream_cheese_bowl_hover_drop_budget_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_swap/task07 | Put the cream cheese on the bowl | 5/300 | 5/90 | 85 | 5 | 5/5 | 4/5 | 0/0 |
### cream_cheese_bowl_support_geometry

职责：geometry；声明 profile：cream_cheese_bowl_support_geometry_v1。

声明的执行配置：`{"params.geometry_profile":"cream_cheese_bowl_support_geometry_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_swap/task07 | Put the cream cheese on the bowl | 5/300 | 5/90 | 85 | 5 | 5/5 | 4/5 | 0/0 |
### cream_cheese_bowl_support_grounding

职责：grounding；声明 profile：cream_cheese_bowl_support_v1。

声明的执行配置：`{"params.grounding_profile":"cream_cheese_bowl_support_v1","params.grounding_hints.support_object.intent":"stack_support","params.grounding_hints.support_object.object_class":"bowl","params.grounding_hints.support_object.relation":true,"params.grounding_hints.support_object.predicates":[true]}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_swap/task07 | Put the cream cheese on the bowl | 5/300 | 5/90 | 85 | 5 | 5/5 | 4/5 | 0/0 |
### geometry_cream_cheese_rack_top_region

职责：geometry；声明 profile：wine_rack_top_region_surface_v1。

声明的执行配置：`{"params.geometry_profile":"wine_rack_top_region_surface_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task08 | Put the cream cheese on the rack | 5/300 | 5/42 | 37 | 5 | 5/5 | 5/5 | 0/0 |
### geometry_wine_bottle_bowl_inner_floor

职责：geometry；声明 profile：wine_bottle_bowl_inner_floor_v1。

声明的执行配置：`{"params.geometry_profile":"wine_bottle_bowl_inner_floor_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task07 | put the wine bottle in the bowl | 5/300 | 5/92 | 88 | 4 | 4/4 | 4/4 | 0/0 |
| libero_goal_task/task09 | put the wine bottle in the bowl | 5/300 | 5/144 | 139 | 5 | 5/5 | 3/5 | 0/0 |
### grasp_bowl_plate_hollow_rim_topdown

职责：grasp；声明 profile：hollow_bowl_rim_topdown。

声明的执行配置：`{"grasp_profile":"hollow_bowl_rim_topdown"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_swap/task04 | Put the bowl on the plate | 5/300 | 5/36 | 30 | 6 | 5/6 | 5/5 | 0/0 |
| libero_spatial_swap/task01 | Pick the akita black bowl between the plate and the ramekin and place it on the plate | 5/225 | 5/39 | 32 | 7 | 5/7 | 5/5 | 0/0 |
| libero_spatial_swap/task02 | Pick the akita black bowl from table center and place it on the plate | 5/240 | 5/33 | 27 | 6 | 5/6 | 5/5 | 0/0 |
| libero_spatial_swap/task03 | Pick the akita black bowl in the top layer of the wooden cabinet and place it on the plate | 5/240 | 5/248 | 188 | 60 | 5/8 | 0/5 | 0/0 |
| libero_spatial_swap/task04 | Pick the akita black bowl next to the cookies box and place it on the plate | 5/240 | 5/133 | 126 | 7 | 5/7 | 3/5 | 0/0 |
| libero_spatial_swap/task05 | Pick the akita black bowl next to the plate and place it on the plate | 5/139 | 5/79 | 66 | 13 | 5/7 | 5/5 | 0/0 |
| libero_spatial_swap/task06 | Pick the akita black bowl next to the ramekin and place it on the plate | 5/240 | 5/89 | 82 | 7 | 5/6 | 4/5 | 0/0 |
| libero_spatial_swap/task07 | Pick the akita black bowl on the cookies box and place it on the plate | 5/240 | 5/250 | 93 | 157 | 5/10 | 0/5 | 0/0 |
| libero_spatial_swap/task08 | Pick the akita black bowl on the ramekin and place it on the plate | 5/240 | 5/118 | 104 | 14 | 5/8 | 3/5 | 0/0 |
| libero_spatial_swap/task09 | Pick the akita black bowl on the stove and place it on the plate | 5/240 | 5/75 | 69 | 6 | 5/6 | 4/5 | 0/0 |
| libero_spatial_swap/task10 | Pick the akita black bowl on the wooden cabinet and place it on the plate | 5/240 | 5/78 | 73 | 5 | 5/5 | 4/5 | 0/0 |
| libero_spatial_task/task01 | Pick the akita black bowl not between the plate and the ramekin and place it on the plate | 5/240 | 5/178 | 163 | 15 | 4/8 | 2/4 | 0/0 |
| libero_spatial_task/task02 | Pick the akita black bowl next to the plate and place it on the plate | 5/240 | 5/104 | 77 | 27 | 5/9 | 4/5 | 0/0 |
| libero_spatial_task/task03 | Pick the akita black bowl on the top of the wooden cabinet and place it on the plate | 5/240 | 5/78 | 55 | 23 | 5/6 | 4/5 | 0/0 |
| libero_spatial_task/task04 | Pick the akita black bowl on the stove and place it on the plate | 5/119 | 5/73 | 66 | 7 | 5/7 | 4/5 | 0/0 |
| libero_spatial_task/task05 | Pick the akita black bowl next to the ramekin and place it on the plate | 5/162 | 5/185 | 172 | 13 | 4/7 | 2/4 | 0/0 |
| libero_spatial_task/task06 | Pick the akita black bowl next to the cookie box and place it on the plate | 5/103 | 5/81 | 63 | 18 | 5/6 | 4/5 | 0/0 |
| libero_spatial_task/task07 | Pick the akita black bowl on the top of the cabinet and place it on the plate | 5/240 | 5/41 | 35 | 6 | 5/6 | 5/5 | 0/0 |
| libero_spatial_task/task08 | Pick the akita black bowl on the cookie box and place it on the plate | 5/87 | 5/133 | 87 | 46 | 5/8 | 3/5 | 0/0 |
| libero_spatial_task/task09 | Pick the akita black bowl on the top of the cabinet and place it on the plate | 5/148 | 5/143 | 137 | 6 | 5/6 | 3/5 | 0/0 |
| libero_spatial_task/task10 | Pick the akita black bowl on the stove and place it on the plate | 5/127 | 5/71 | 62 | 9 | 5/6 | 4/5 | 0/0 |
### grasp_carton_upright_body_side

职责：grasp；声明 profile：carton_upright_body_side_v1。

声明的执行配置：`{"grasp_profile":"carton_upright_body_side_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_swap/task01 | Open the middle layer of the drawer | 0/0 | 0/0 | 0 | 0 | 0/0 | 0/0 | 300/300 |
| libero_object_swap/task07 | Pick the milk and place it in the basket | 5/280 | 5/32 | 27 | 5 | 5/5 | 5/5 | 0/0 |
| libero_object_swap/task08 | Pick the orange juice and place it in the basket | 5/280 | 5/37 | 32 | 5 | 5/5 | 5/5 | 0/0 |
| libero_object_task/task03 | Pick the orange juice and place it in the basket | 5/280 | 5/30 | 25 | 5 | 5/5 | 5/5 | 0/0 |
| libero_object_task/task06 | Pick the milk and place it in the basket | 5/280 | 5/32 | 27 | 5 | 5/5 | 5/5 | 0/0 |
### grasp_cream_cheese_bowl_flat_box_topdown_deep

职责：grasp；声明 profile：cream_cheese_flat_box_topdown_deep_v1。

声明的执行配置：`{"grasp_profile":"cream_cheese_flat_box_topdown_deep_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_swap/task07 | Put the cream cheese on the bowl | 5/300 | 5/90 | 85 | 5 | 5/5 | 4/5 | 0/0 |
### grasp_cream_cheese_rack_flat_box_deep

职责：grasp；声明 profile：cream_cheese_flat_box_topdown_deeper_v2。

声明的执行配置：`{"grasp_profile":"cream_cheese_flat_box_topdown_deeper_v2"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task08 | Put the cream cheese on the rack | 5/300 | 5/42 | 37 | 5 | 5/5 | 5/5 | 0/0 |
### grasp_object_basket_flat_box_topdown_deep

职责：grasp；声明 profile：cream_cheese_flat_box_topdown_deep_v1。

声明的执行配置：`{"grasp_profile":"cream_cheese_flat_box_topdown_deep_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_object_swap/task03 | Pick the butter and place it in the basket | 5/280 | 5/111 | 106 | 5 | 5/5 | 4/5 | 0/0 |
| libero_object_swap/task04 | Pick the chocolate pudding and place it in the basket | 5/280 | 5/161 | 155 | 6 | 5/6 | 3/5 | 0/0 |
| libero_object_swap/task05 | Pick the cream cheese and place it in the basket | 5/280 | 5/184 | 180 | 4 | 4/4 | 2/4 | 0/0 |
| libero_object_task/task01 | Pick the cream cheese and place it in the basket | 5/280 | 5/80 | 76 | 4 | 4/4 | 4/4 | 0/0 |
| libero_object_task/task07 | Pick the butter and place it in the basket | 5/280 | 5/235 | 229 | 6 | 5/6 | 1/5 | 0/0 |
| libero_object_task/task08 | Pick the chocolate pudding and place it in the basket | 5/280 | 5/29 | 24 | 5 | 5/5 | 5/5 | 0/0 |
### grasp_wine_bottle_plate_topdown_close_guard

职责：grasp；声明 profile：libero_topdown。

声明的执行配置：`{"grasp_profile":"libero_topdown","params.executor.grasp_close_max_above_m":0.18}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task04 | Put the wine bottle on the plate | 5/300 | 5/140 | 137 | 3 | 3/3 | 3/3 | 0/0 |
### grasp_wine_bottle_topdown_close_guard

职责：grasp；声明 profile：libero_topdown。

声明的执行配置：`{"grasp_profile":"libero_topdown","params.executor.grasp_close_max_above_m":0.18}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task07 | put the wine bottle in the bowl | 5/300 | 5/92 | 88 | 4 | 4/4 | 4/4 | 0/0 |
| libero_goal_task/task09 | put the wine bottle in the bowl | 5/300 | 5/144 | 139 | 5 | 5/5 | 3/5 | 0/0 |
### ground_cream_cheese_rack_top_region

职责：grounding；声明 profile：wine_rack_top_region_v1。

声明的执行配置：`{"params.grounding_profile":"wine_rack_top_region_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task08 | Put the cream cheese on the rack | 5/300 | 5/42 | 37 | 5 | 5/5 | 5/5 | 0/0 |
### ground_wine_bottle_bowl_inner_floor

职责：grounding；声明 profile：wine_bottle_bowl_inner_floor_v1。

声明的执行配置：`{"params.grounding_profile":"wine_bottle_bowl_inner_floor_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task07 | put the wine bottle in the bowl | 5/300 | 5/92 | 88 | 4 | 4/4 | 4/4 | 0/0 |
| libero_goal_task/task09 | put the wine bottle in the bowl | 5/300 | 5/144 | 139 | 5 | 5/5 | 3/5 | 0/0 |
### place_wine_bottle_bowl_drop_budget

职责：place；声明 profile：wine_bottle_bowl_drop_budget_v1。

声明的执行配置：`{"params.place_profile":"wine_bottle_bowl_drop_budget_v1"}`。

| Task | 任务指令 | B 匹配 ep/query | C4 匹配 ep/query | C4 无 trigger 匹配 | C4 决策选择 | C4 恢复 ep/入口 | 恢复 ep 最终成功 | B/C4 不可判定 query |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| libero_goal_task/task07 | put the wine bottle in the bowl | 5/300 | 5/92 | 88 | 4 | 4/4 | 4/4 | 0/0 |
| libero_goal_task/task09 | put the wine bottle in the bowl | 5/300 | 5/144 | 139 | 5 | 5/5 | 3/5 | 0/0 |

## 全 36 条 skill 一张表

全部在 C4 原始轨迹上统计。Trigger 的“选择”是 winner；hint 的“选择”是合并配置。恢复入口数是 mode=recovery，与过去只统计 hook 决策的表不同。

| 完整 skill ID | 类型 | 条件匹配 task 数 | 被选用 task 数 | 被选用 query | 实际恢复入口数 | 实际恢复 task 数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| black_bowl_cabinet_top_to_plate_wrong_object_handoff | Trigger | 5 | 2 | 6 | 6 | 2 |
| black_bowl_next_to_plate_wrong_object_handoff | Trigger | 2 | 1 | 16 | 4 | 1 |
| black_bowl_not_between_wrong_object_handoff | Trigger | 1 | 1 | 3 | 3 | 1 |
| black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | Trigger | 3 | 1 | 5 | 5 | 1 |
| bowl_cabinet_target_holding_handoff | Trigger | 0 | 0 | 0 | 0 | 0 |
| bowl_cookie_box_wrong_bowl_handoff | Trigger | 2 | 0 | 0 | 0 | 0 |
| bowl_plate_pick_lost_or_wrong_intent | Trigger | 21 | 21 | 428 | 127 | 21 |
| cream_cheese_bowl_wrong_object_intent | Trigger | 1 | 1 | 5 | 5 | 1 |
| cream_cheese_rack_wrong_object_handoff | Trigger | 1 | 1 | 5 | 5 | 1 |
| object_basket_bbq_orange_precontact_wrong_intent | Trigger | 4 | 4 | 20 | 20 | 4 |
| object_basket_cream_cheese_precontact_wrong_intent | Trigger | 2 | 1 | 4 | 4 | 1 |
| object_basket_cream_tomato_q5_wrong_intent_window | Trigger | 4 | 2 | 9 | 9 | 2 |
| object_basket_persistent_wrong_intent_group_a | Trigger | 10 | 9 | 47 | 47 | 9 |
| object_basket_salad_dressing_precontact_wrong_intent | Trigger | 2 | 2 | 10 | 10 | 2 |
| object_basket_tomato_persistent_wrong_intent | Trigger | 2 | 1 | 5 | 5 | 1 |
| plate_stove_open_wrong_intent_pregrasp_handoff | Trigger | 2 | 1 | 19 | 7 | 1 |
| wine_bottle_bowl_wrong_object_handoff | Trigger | 2 | 2 | 9 | 9 | 2 |
| wine_bottle_plate_wrong_object_handoff | Trigger | 1 | 1 | 3 | 3 | 1 |
| bowl_plate_hover_drop_budget | Hint | 1 | 1 | 15 | 8 | 1 |
| bowl_plate_next_to_plate_hover_drop_budget | Hint | 2 | 2 | 40 | 16 | 2 |
| cabinet_top_surface_geometry_explicit | Hint | 0 | 0 | 0 | 0 | 0 |
| cream_cheese_bowl_hover_drop_budget | Hint | 1 | 1 | 5 | 5 | 1 |
| cream_cheese_bowl_support_geometry | Hint | 1 | 1 | 5 | 5 | 1 |
| cream_cheese_bowl_support_grounding | Hint | 1 | 1 | 5 | 5 | 1 |
| geometry_cream_cheese_rack_top_region | Hint | 1 | 1 | 5 | 5 | 1 |
| geometry_wine_bottle_bowl_inner_floor | Hint | 2 | 2 | 9 | 9 | 2 |
| grasp_bowl_plate_hollow_rim_topdown | Hint | 21 | 21 | 458 | 145 | 21 |
| grasp_carton_upright_body_side | Hint | 4 | 4 | 20 | 20 | 4 |
| grasp_cream_cheese_bowl_flat_box_topdown_deep | Hint | 1 | 1 | 5 | 5 | 1 |
| grasp_cream_cheese_rack_flat_box_deep | Hint | 1 | 1 | 5 | 5 | 1 |
| grasp_object_basket_flat_box_topdown_deep | Hint | 6 | 6 | 30 | 30 | 6 |
| grasp_wine_bottle_plate_topdown_close_guard | Hint | 1 | 1 | 3 | 3 | 1 |
| grasp_wine_bottle_topdown_close_guard | Hint | 2 | 2 | 9 | 9 | 2 |
| ground_cream_cheese_rack_top_region | Hint | 1 | 1 | 5 | 5 | 1 |
| ground_wine_bottle_bowl_inner_floor | Hint | 2 | 2 | 9 | 9 | 2 |
| place_wine_bottle_bowl_drop_budget | Hint | 2 | 2 | 9 | 9 | 2 |

## 验证与可复现边界

冻结运行代码 commit：`7128c1ea6280c227e48561e621fe9da8604c5a6d`；matcher SHA256：`faaf1c8251484f5d8bfc7ebc1231b072b235e35adbf89940a2cfde02bb023a2c`。

在 C4 的 594 个 hook 决策检查点上，旁路匹配集合与原始 hint_sources 集合不一致 0 次。谓词执行错误 0 类。

恢复入口、字段保留不等于每个 profile 的物理阶段真的执行完；本次没有对 recovery_trace 内每种动作阶段做逐条归因，因此不能报告单 hint 成功率。Episode 最终成功也不能归因于某一条 hint。

完整结构化数据：libero_pro_c4_hint_shadow_results.json；逐检查点匹配、trigger 集合、选择集合、字段保留/覆盖数据：libero_pro_c4_hint_shadow_full.json.gz。
