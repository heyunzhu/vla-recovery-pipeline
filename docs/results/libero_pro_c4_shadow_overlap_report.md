# 实验 1：C4 Trigger 的无接管旁路触发统计

日期：2026-10-10。已完成；只分析既有日志，无新增 rollout，无修改 skill/profile。

## 结论

BASELINE 的共同动态触发有 89 条 query，C4 有 1 条。但它们全部来自同一对 cabinet 规则、同一个 task；按 episode 去重只有 4 与 1 个，不代表整个 pack 的竞争都很严重。两组都有 7 个 episode 出现多个 Trigger，说明同时触发统计会漏掉不同时间的共同覆盖。

BASELINE 最终成功的 48 个 episode 中，34 个也满足通用 bowl Trigger，值得检查接管必要性，但不能直接判为有害误触发。

## 数据与校验

- 各 300 episodes；六 suites、每 suite 10 tasks、每 task 5 episodes。从 jobs.tsv 精确选取 12 个完成 job，排除 resume 备份。两组 episode 键、seed 和任务描述逐一配对。
- Query 数均与 episode 元数据一致，ID 无重复；BASELINE 全部为 VLA 模式，未作 hook 决策。没有补跑实验。
- 从原实验冻结 runtime_repo 加载 matcher、schema 和历史重建逻辑，同一 C4 pack 的 18 条 Trigger 全部参加诊断。没有 dispatch/recover/env.step。
- BASELINE 按 query 顺序重建历史再判断；C4 比较使用原日志的全候选诊断，包括未成为 winner 的候选。
- 首次实际接管前（包括首次接管 query）5,733 条 query × 18 条规则 = 103,194 次 applies_to 检查及 103,194 次 would_fire 检查，均为 0 mismatch。接管后两类各 42,732 次检查，本次也均为 0 mismatch。
- 审计状态键全部存在，predicate error 为 0。target_name 为 null 的 query 两组各 300；goal_name 为 null 的 query 为 B 1,453、C4 1,467。
- 对 null/error 做三值逻辑审计：未知字段不直接当作 false，只有其他已知条件足够否定的候选才确定不触发。本次最终无法确定的候选为 0，所有 query 的候选触发状态均可判定。这里没有声称 null 字段的真实物体/goal 已被还原。

## 1. 总体统计

| 指标 | BASELINE 旁路 | C4 原诊断 |
| --- | ---: | ---: |
| Episode 数 | 300 | 300 |
| 原 rollout 最终成功数 | 48 | 189 |
| Query 数 | 15112 | 8107 |
| 至少一条 applies_to 的 query | 11859 | 4840 |
| 多条 applies_to 的 query | 3174 | 1664 |
| 至少一条 would_fire 的 query | 3321 | 594 |
| 多条同时 would_fire 的 query | 89 | 1 |
| 至少一条 would_fire 的 episode | 223 | 223 |
| 同 episode 出现多个 Trigger | 7 | 7 |
| 含同时触发的 episode | 4 | 1 |
| 仅先后触发、从未同时触发的 episode | 3 | 6 |

共同动态触发/query：B 89/15,112 = 0.589%；C4 1/8,107 = 0.012%。共同动态触发/episode：B 4/300 = 1.33%；C4 1/300 = 0.33%。89 条 query 是反复命中，不是 89 个独立案例。

前 11 次 query（0–10）的共同动态触发：B 5/3,293；C4 1/2,664。许多重叠来自较晚的持续失败状态。Query 数与 episode 长度不同，原始次数差不能直接当作因果效应。

### 决策和真实执行的口径修正

C4 hook_fired=true 共 594 次，但 mode=recovery 实际进入恢复只有 **269 次**，涉及 223 个 episode。恢复预算检查在候选选择之后；因此前面表中的 Trigger winner/hint 使用次数是 hook 决策与配置选择，不是物理恢复执行次数。本报告 would_fire 也不是执行次数。

## 2. 全部 18 条 Trigger

统计 would_fire，而非 winner，因此 C4 cabinet-top 有 7 次候选触发，此前 winner 表为 6 次。T 编号供后续 task/pair 表引用。

| 编号 | 完整 ID | B query | C4 query | B ep | C4 ep | B task数 | C4 task数 | B首次query中位数 | C4首次query中位数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 | black_bowl_cabinet_top_to_plate_wrong_object_handoff | 229 | 7 | 9 | 7 | 2 | 3 | 7 | 6 |
| T2 | black_bowl_next_to_plate_wrong_object_handoff | 38 | 16 | 4 | 3 | 1 | 1 | 10.5 | 6 |
| T3 | black_bowl_not_between_wrong_object_handoff | 109 | 3 | 4 | 3 | 1 | 1 | 5.5 | 5 |
| T4 | black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff | 118 | 5 | 5 | 5 | 1 | 1 | 6 | 6 |
| T5 | bowl_cabinet_target_holding_handoff | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| T6 | bowl_cookie_box_wrong_bowl_handoff | 0 | 0 | 0 | 0 | 0 | 0 | — | — |
| T7 | bowl_plate_pick_lost_or_wrong_intent | 789 | 428 | 85 | 92 | 19 | 21 | 6 | 6 |
| T8 | cream_cheese_bowl_wrong_object_intent | 90 | 5 | 5 | 5 | 1 | 1 | 8 | 8 |
| T9 | cream_cheese_rack_wrong_object_handoff | 41 | 5 | 5 | 5 | 1 | 1 | 7 | 7 |
| T10 | object_basket_bbq_orange_precontact_wrong_intent | 114 | 20 | 20 | 20 | 4 | 4 | 6 | 6 |
| T11 | object_basket_cream_cheese_precontact_wrong_intent | 8 | 4 | 5 | 4 | 1 | 1 | 6 | 6 |
| T12 | object_basket_cream_tomato_q5_wrong_intent_window | 14 | 9 | 11 | 9 | 3 | 2 | 5 | 5 |
| T13 | object_basket_persistent_wrong_intent_group_a | 1511 | 47 | 45 | 45 | 9 | 9 | 5 | 5 |
| T14 | object_basket_salad_dressing_precontact_wrong_intent | 72 | 10 | 10 | 10 | 2 | 2 | 7 | 8 |
| T15 | object_basket_tomato_persistent_wrong_intent | 208 | 5 | 5 | 5 | 1 | 1 | 5 | 5 |
| T16 | plate_stove_open_wrong_intent_pregrasp_handoff | 17 | 19 | 5 | 5 | 1 | 1 | 6 | 5 |
| T17 | wine_bottle_bowl_wrong_object_handoff | 50 | 9 | 10 | 9 | 2 | 2 | 7 | 7 |
| T18 | wine_bottle_plate_wrong_object_handoff | 2 | 3 | 2 | 3 | 1 | 1 | 7 | 6 |

首次触发先按每个命中 episode 取首次 query，再求中位数。两条件命中 episode 集合可能不同，中位数差不是接管时机的因果估计。完整 query 时刻与命中集保留在压缩审计产物，可重建每个 episode 的触发窗口。

## 3. Pair：同时和先后触发

共同 ep：双方都曾 would_fire。仅先后 ep：双方都出现，但整个 episode 从未同 query 共同触发。含同时触发的 ep 也可能另有先后触发，这里使用排他分类。

| Pair | B共同匹配query | C4共同匹配query | B同时query | C4同时query | B共同ep | C4共同ep | B仅先后ep | C4仅先后ep |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| T1 ↔ T4 | 720 | 404 | 89 | 1 | 4 | 1 | 0 | 0 |
| T1 ↔ T7 | 1108 | 588 | 0 | 0 | 0 | 1 | 0 | 1 |
| T2 ↔ T7 | 379 | 183 | 0 | 0 | 1 | 1 | 1 | 1 |
| T3 ↔ T7 | 240 | 178 | 0 | 0 | 1 | 3 | 1 | 3 |
| T4 ↔ T7 | 720 | 404 | 0 | 0 | 0 | 1 | 0 | 1 |
| T6 ↔ T7 | 327 | 383 | 0 | 0 | 0 | 0 | 0 | 0 |
| T11 ↔ T12 | 560 | 264 | 0 | 0 | 1 | 0 | 1 | 0 |
| T12 ↔ T15 | 560 | 68 | 0 | 0 | 0 | 0 | 0 | 0 |

全部 153 对均检查，上表仅省略共同匹配/共同触发均为零的 pair。Pair 次数不能相加作为独立 query/episode 数。

### 唯一同时竞争 pair

T1 cabinet-top ↔ T4 wooden-cabinet early，全部在 libero_spatial_task/task03。

| Episode | B首次early | B首次cabinet | B共同query数 | C4共同query数 |
| --- | ---: | ---: | ---: | ---: |
| ep01 | 6 | 25 | 23 | 0 |
| ep02 | 7 | 7 | 27 | 0 |
| ep03 | 7 | 7 | 23 | 1 |
| ep04 | 6 | 29 | 16 | 0 |

例如 ep01：early 从 query 6 满足，cabinet 到 query 25 才满足，之后持续共同满足。在线 early 接管可能减少进入较晚共同触发状态的机会；这是局部机制证据，不应把 88 次差值全部直接归因于一次接管。

### 先后触发案例

- B object-swap/task05/ep03：cream/tomato q5 在 query 5 满足，cream-cheese 专用规则在 query 7、8 满足。互斥距离门限仍可在不同时间覆盖同一 episode。
- C4 spatial-task/task01/ep00：not-between 在 query 5 满足，通用 bowl 在 query 6 满足。
- 先后命中不自动证明同一次失败重复处理：接管也可能制造新状态。需结合原状态/视频判断失败事件是否相同。

## 4. 成功 BASELINE 中的触发

成功 48 个 baseline 中，34/48（70.8%）满足 Trigger，全部为 T7 通用 bowl；失败 252 个 baseline 中有 189 个满足 Trigger。因此该 hook 不是只识别必然失败，它也覆盖 VLA 后来能自行成功的中间状态。

上述 34 个 episode 的 C4 配对结果为 25 个成功、9 个失败；这不能单独证明通用 Trigger 导致失败，其他介入、随机性及轨迹差异尚未排除。优先在这些状态上做仅通用 bowl 开/关或延迟接管对照。

成功 baseline 且会触发的 episode：

- libero_spatial_task/task04/ep00
- libero_spatial_task/task04/ep01
- libero_spatial_task/task04/ep02
- libero_spatial_task/task04/ep03
- libero_spatial_task/task04/ep04
- libero_spatial_task/task05/ep00
- libero_spatial_task/task05/ep02
- libero_spatial_task/task05/ep03
- libero_spatial_task/task06/ep00
- libero_spatial_task/task06/ep01
- libero_spatial_task/task06/ep02
- libero_spatial_task/task06/ep03
- libero_spatial_task/task06/ep04
- libero_spatial_task/task08/ep00
- libero_spatial_task/task08/ep01
- libero_spatial_task/task08/ep02
- libero_spatial_task/task08/ep03
- libero_spatial_task/task08/ep04
- libero_spatial_task/task09/ep00
- libero_spatial_task/task09/ep01
- libero_spatial_task/task09/ep02
- libero_spatial_task/task09/ep03
- libero_spatial_task/task09/ep04
- libero_spatial_task/task10/ep00
- libero_spatial_task/task10/ep01
- libero_spatial_task/task10/ep02
- libero_spatial_task/task10/ep03
- libero_spatial_task/task10/ep04
- libero_spatial_swap/task01/ep02
- libero_spatial_swap/task05/ep00
- libero_spatial_swap/task05/ep01
- libero_spatial_swap/task05/ep02
- libero_spatial_swap/task05/ep03
- libero_spatial_swap/task05/ep04

## 5. Task × Trigger

每 task 5 ep；T 编号见完整 ID 表。未列的行各项为零。这里的 ep 成功是原 rollout 最终结果，不是 skill 单独成功率。

| 条件 | Suite/task | Trigger | applies_to query | would_fire query | would_fire ep | 其中最终成功 | 首次query中位数 |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| C4 | goal_swap/task03 | T16 | 300 | 0 | 0 | 0 | — |
| C4 | goal_swap/task04 | T7 | 36 | 6 | 5 | 5 | 6 |
| C4 | goal_swap/task07 | T8 | 90 | 5 | 5 | 4 | 8 |
| C4 | goal_task/task04 | T18 | 140 | 3 | 3 | 3 | 6 |
| C4 | goal_task/task05 | T16 | 307 | 19 | 5 | 0 | 5 |
| C4 | goal_task/task07 | T17 | 92 | 4 | 4 | 4 | 7 |
| C4 | goal_task/task08 | T9 | 42 | 5 | 5 | 5 | 7 |
| C4 | goal_task/task09 | T17 | 144 | 5 | 5 | 3 | 6 |
| C4 | object_swap/task01 | T13 | 30 | 5 | 5 | 5 | 5 |
| C4 | object_swap/task02 | T10 | 47 | 5 | 5 | 5 | 8 |
| C4 | object_swap/task03 | T13 | 111 | 5 | 5 | 4 | 6 |
| C4 | object_swap/task04 | T13 | 161 | 6 | 5 | 3 | 5 |
| C4 | object_swap/task05 | T11 | 184 | 4 | 4 | 2 | 6 |
| C4 | object_swap/task05 | T12 | 184 | 0 | 0 | 0 | — |
| C4 | object_swap/task06 | T13 | 33 | 5 | 5 | 5 | 6 |
| C4 | object_swap/task07 | T13 | 32 | 5 | 5 | 5 | 5 |
| C4 | object_swap/task08 | T10 | 37 | 5 | 5 | 5 | 6 |
| C4 | object_swap/task09 | T14 | 93 | 5 | 5 | 4 | 8 |
| C4 | object_swap/task10 | T12 | 30 | 0 | 0 | 0 | — |
| C4 | object_swap/task10 | T15 | 30 | 5 | 5 | 5 | 5 |
| C4 | object_task/task01 | T11 | 80 | 0 | 0 | 0 | — |
| C4 | object_task/task01 | T12 | 80 | 4 | 4 | 4 | 5 |
| C4 | object_task/task02 | T13 | 32 | 5 | 5 | 5 | 5 |
| C4 | object_task/task03 | T10 | 30 | 5 | 5 | 5 | 5 |
| C4 | object_task/task04 | T14 | 38 | 5 | 5 | 5 | 6 |
| C4 | object_task/task05 | T13 | 149 | 0 | 0 | 0 | — |
| C4 | object_task/task06 | T13 | 32 | 5 | 5 | 5 | 5 |
| C4 | object_task/task07 | T13 | 235 | 6 | 5 | 1 | 5 |
| C4 | object_task/task08 | T13 | 29 | 5 | 5 | 5 | 5 |
| C4 | object_task/task09 | T12 | 38 | 5 | 5 | 5 | 5 |
| C4 | object_task/task09 | T15 | 38 | 0 | 0 | 0 | — |
| C4 | object_task/task10 | T10 | 39 | 5 | 5 | 5 | 6 |
| C4 | spatial_swap/task01 | T7 | 39 | 7 | 5 | 5 | 6 |
| C4 | spatial_swap/task02 | T7 | 33 | 6 | 5 | 5 | 5 |
| C4 | spatial_swap/task03 | T1 | 248 | 0 | 0 | 0 | — |
| C4 | spatial_swap/task03 | T4 | 248 | 0 | 0 | 0 | — |
| C4 | spatial_swap/task03 | T7 | 248 | 60 | 5 | 0 | 6 |
| C4 | spatial_swap/task04 | T7 | 133 | 7 | 5 | 3 | 7 |
| C4 | spatial_swap/task05 | T2 | 79 | 0 | 0 | 0 | — |
| C4 | spatial_swap/task05 | T7 | 79 | 13 | 5 | 5 | 8 |
| C4 | spatial_swap/task06 | T7 | 89 | 7 | 5 | 4 | 9 |
| C4 | spatial_swap/task07 | T6 | 250 | 0 | 0 | 0 | — |
| C4 | spatial_swap/task07 | T7 | 250 | 157 | 5 | 0 | 6 |
| C4 | spatial_swap/task08 | T7 | 118 | 14 | 5 | 3 | 5 |
| C4 | spatial_swap/task09 | T7 | 75 | 6 | 5 | 4 | 4 |
| C4 | spatial_swap/task10 | T1 | 78 | 0 | 0 | 0 | — |
| C4 | spatial_swap/task10 | T4 | 78 | 0 | 0 | 0 | — |
| C4 | spatial_swap/task10 | T7 | 78 | 5 | 5 | 4 | 6 |
| C4 | spatial_task/task01 | T3 | 178 | 3 | 3 | 1 | 5 |
| C4 | spatial_task/task01 | T7 | 178 | 12 | 4 | 2 | 6 |
| C4 | spatial_task/task02 | T2 | 104 | 16 | 3 | 2 | 6 |
| C4 | spatial_task/task02 | T7 | 104 | 11 | 3 | 3 | 7 |
| C4 | spatial_task/task03 | T1 | 78 | 1 | 1 | 1 | 6 |
| C4 | spatial_task/task03 | T4 | 78 | 5 | 5 | 4 | 6 |
| C4 | spatial_task/task03 | T7 | 78 | 18 | 1 | 0 | 7 |
| C4 | spatial_task/task04 | T7 | 73 | 7 | 5 | 4 | 5 |
| C4 | spatial_task/task05 | T7 | 185 | 13 | 4 | 2 | 11 |
| C4 | spatial_task/task06 | T7 | 81 | 18 | 5 | 4 | 7 |
| C4 | spatial_task/task07 | T1 | 41 | 5 | 5 | 5 | 5 |
| C4 | spatial_task/task07 | T7 | 41 | 1 | 1 | 1 | 8 |
| C4 | spatial_task/task08 | T6 | 133 | 0 | 0 | 0 | — |
| C4 | spatial_task/task08 | T7 | 133 | 46 | 5 | 3 | 7 |
| C4 | spatial_task/task09 | T1 | 143 | 1 | 1 | 1 | 21 |
| C4 | spatial_task/task09 | T7 | 143 | 5 | 4 | 2 | 7 |
| C4 | spatial_task/task10 | T7 | 71 | 9 | 5 | 4 | 4 |
| B | goal_swap/task03 | T16 | 300 | 0 | 0 | 0 | — |
| B | goal_swap/task04 | T7 | 300 | 38 | 4 | 0 | 6 |
| B | goal_swap/task07 | T8 | 300 | 90 | 5 | 0 | 8 |
| B | goal_task/task04 | T18 | 300 | 2 | 2 | 0 | 7 |
| B | goal_task/task05 | T16 | 300 | 17 | 5 | 0 | 6 |
| B | goal_task/task07 | T17 | 300 | 20 | 5 | 0 | 8 |
| B | goal_task/task08 | T9 | 300 | 41 | 5 | 0 | 7 |
| B | goal_task/task09 | T17 | 300 | 30 | 5 | 0 | 6 |
| B | object_swap/task01 | T13 | 280 | 151 | 5 | 0 | 5 |
| B | object_swap/task02 | T10 | 280 | 54 | 5 | 0 | 8 |
| B | object_swap/task03 | T13 | 280 | 221 | 5 | 0 | 5 |
| B | object_swap/task04 | T13 | 280 | 160 | 5 | 0 | 5 |
| B | object_swap/task05 | T11 | 280 | 8 | 5 | 0 | 6 |
| B | object_swap/task05 | T12 | 280 | 1 | 1 | 0 | 5 |
| B | object_swap/task06 | T13 | 280 | 135 | 5 | 0 | 5 |
| B | object_swap/task07 | T13 | 280 | 162 | 5 | 0 | 5 |
| B | object_swap/task08 | T10 | 280 | 16 | 5 | 0 | 6 |
| B | object_swap/task09 | T14 | 280 | 21 | 5 | 0 | 8 |
| B | object_swap/task10 | T12 | 280 | 0 | 0 | 0 | — |
| B | object_swap/task10 | T15 | 280 | 208 | 5 | 0 | 5 |
| B | object_task/task01 | T11 | 280 | 0 | 0 | 0 | — |
| B | object_task/task01 | T12 | 280 | 5 | 5 | 0 | 5 |
| B | object_task/task02 | T13 | 280 | 96 | 5 | 0 | 6 |
| B | object_task/task03 | T10 | 280 | 20 | 5 | 0 | 5 |
| B | object_task/task04 | T14 | 280 | 51 | 5 | 0 | 6 |
| B | object_task/task05 | T13 | 149 | 0 | 0 | 0 | — |
| B | object_task/task06 | T13 | 280 | 169 | 5 | 0 | 6 |
| B | object_task/task07 | T13 | 280 | 254 | 5 | 0 | 5 |
| B | object_task/task08 | T13 | 280 | 163 | 5 | 0 | 5 |
| B | object_task/task09 | T12 | 280 | 8 | 5 | 0 | 5 |
| B | object_task/task09 | T15 | 280 | 0 | 0 | 0 | — |
| B | object_task/task10 | T10 | 280 | 24 | 5 | 0 | 6 |
| B | spatial_swap/task01 | T7 | 225 | 14 | 5 | 1 | 6 |
| B | spatial_swap/task02 | T7 | 240 | 16 | 5 | 0 | 6 |
| B | spatial_swap/task03 | T1 | 240 | 0 | 0 | 0 | — |
| B | spatial_swap/task03 | T4 | 240 | 0 | 0 | 0 | — |
| B | spatial_swap/task03 | T7 | 240 | 23 | 5 | 0 | 6 |
| B | spatial_swap/task04 | T7 | 240 | 131 | 5 | 0 | 7 |
| B | spatial_swap/task05 | T2 | 139 | 0 | 0 | 0 | — |
| B | spatial_swap/task05 | T7 | 139 | 18 | 5 | 5 | 8 |
| B | spatial_swap/task06 | T7 | 240 | 75 | 5 | 0 | 9 |
| B | spatial_swap/task07 | T6 | 240 | 0 | 0 | 0 | — |
| B | spatial_swap/task07 | T7 | 240 | 134 | 5 | 0 | 7 |
| B | spatial_swap/task08 | T7 | 240 | 56 | 5 | 0 | 5 |
| B | spatial_swap/task09 | T7 | 240 | 43 | 5 | 0 | 4 |
| B | spatial_swap/task10 | T1 | 240 | 0 | 0 | 0 | — |
| B | spatial_swap/task10 | T4 | 240 | 0 | 0 | 0 | — |
| B | spatial_swap/task10 | T7 | 240 | 125 | 5 | 0 | 6 |
| B | spatial_task/task01 | T3 | 240 | 109 | 4 | 0 | 5.5 |
| B | spatial_task/task01 | T7 | 240 | 1 | 1 | 0 | 47 |
| B | spatial_task/task02 | T2 | 240 | 38 | 4 | 0 | 10.5 |
| B | spatial_task/task02 | T7 | 240 | 15 | 2 | 0 | 31.5 |
| B | spatial_task/task03 | T1 | 240 | 92 | 4 | 0 | 16 |
| B | spatial_task/task03 | T4 | 240 | 118 | 5 | 0 | 6 |
| B | spatial_task/task03 | T7 | 240 | 0 | 0 | 0 | — |
| B | spatial_task/task04 | T7 | 119 | 19 | 5 | 5 | 4 |
| B | spatial_task/task05 | T7 | 162 | 9 | 3 | 3 | 9 |
| B | spatial_task/task06 | T7 | 103 | 20 | 5 | 5 | 7 |
| B | spatial_task/task07 | T1 | 240 | 137 | 5 | 0 | 5 |
| B | spatial_task/task07 | T7 | 240 | 0 | 0 | 0 | — |
| B | spatial_task/task08 | T6 | 87 | 0 | 0 | 0 | — |
| B | spatial_task/task08 | T7 | 87 | 15 | 5 | 5 | 7 |
| B | spatial_task/task09 | T1 | 148 | 0 | 0 | 0 | — |
| B | spatial_task/task09 | T7 | 148 | 18 | 5 | 5 | 6 |
| B | spatial_task/task10 | T7 | 127 | 19 | 5 | 5 | 4 |

## 6. Task × Pair

| 条件 | Suite/task | Pair | 共同applies_to query | 同时would_fire query | 共同would_fire ep | 仅先后ep |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| C4 | object_swap/task05 | T11 ↔ T12 | 184 | 0 | 0 | 0 |
| C4 | object_swap/task10 | T12 ↔ T15 | 30 | 0 | 0 | 0 |
| C4 | object_task/task01 | T11 ↔ T12 | 80 | 0 | 0 | 0 |
| C4 | object_task/task09 | T12 ↔ T15 | 38 | 0 | 0 | 0 |
| C4 | spatial_swap/task03 | T1 ↔ T4 | 248 | 0 | 0 | 0 |
| C4 | spatial_swap/task03 | T1 ↔ T7 | 248 | 0 | 0 | 0 |
| C4 | spatial_swap/task03 | T4 ↔ T7 | 248 | 0 | 0 | 0 |
| C4 | spatial_swap/task05 | T2 ↔ T7 | 79 | 0 | 0 | 0 |
| C4 | spatial_swap/task07 | T6 ↔ T7 | 250 | 0 | 0 | 0 |
| C4 | spatial_swap/task10 | T1 ↔ T4 | 78 | 0 | 0 | 0 |
| C4 | spatial_swap/task10 | T1 ↔ T7 | 78 | 0 | 0 | 0 |
| C4 | spatial_swap/task10 | T4 ↔ T7 | 78 | 0 | 0 | 0 |
| C4 | spatial_task/task01 | T3 ↔ T7 | 178 | 0 | 3 | 3 |
| C4 | spatial_task/task02 | T2 ↔ T7 | 104 | 0 | 1 | 1 |
| C4 | spatial_task/task03 | T1 ↔ T4 | 78 | 1 | 1 | 0 |
| C4 | spatial_task/task03 | T1 ↔ T7 | 78 | 0 | 0 | 0 |
| C4 | spatial_task/task03 | T4 ↔ T7 | 78 | 0 | 1 | 1 |
| C4 | spatial_task/task07 | T1 ↔ T7 | 41 | 0 | 1 | 1 |
| C4 | spatial_task/task08 | T6 ↔ T7 | 133 | 0 | 0 | 0 |
| C4 | spatial_task/task09 | T1 ↔ T7 | 143 | 0 | 0 | 0 |
| B | object_swap/task05 | T11 ↔ T12 | 280 | 0 | 1 | 1 |
| B | object_swap/task10 | T12 ↔ T15 | 280 | 0 | 0 | 0 |
| B | object_task/task01 | T11 ↔ T12 | 280 | 0 | 0 | 0 |
| B | object_task/task09 | T12 ↔ T15 | 280 | 0 | 0 | 0 |
| B | spatial_swap/task03 | T1 ↔ T4 | 240 | 0 | 0 | 0 |
| B | spatial_swap/task03 | T1 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_swap/task03 | T4 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_swap/task05 | T2 ↔ T7 | 139 | 0 | 0 | 0 |
| B | spatial_swap/task07 | T6 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_swap/task10 | T1 ↔ T4 | 240 | 0 | 0 | 0 |
| B | spatial_swap/task10 | T1 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_swap/task10 | T4 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_task/task01 | T3 ↔ T7 | 240 | 0 | 1 | 1 |
| B | spatial_task/task02 | T2 ↔ T7 | 240 | 0 | 1 | 1 |
| B | spatial_task/task03 | T1 ↔ T4 | 240 | 89 | 4 | 0 |
| B | spatial_task/task03 | T1 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_task/task03 | T4 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_task/task07 | T1 ↔ T7 | 240 | 0 | 0 | 0 |
| B | spatial_task/task08 | T6 ↔ T7 | 87 | 0 | 0 | 0 |
| B | spatial_task/task09 | T1 ↔ T7 | 148 | 0 | 0 | 0 |

## 解释边界

- 结果支持 hook 改变后续触发机会这一局部解释，最明显的是 cabinet pair；不支持整个 pack 存在广泛严重竞争。
- 距离门限、对象白名单、时间窗口仍限制动态重叠；门限互斥不会因关闭接管而消失。
- 两组各 7 个多 skill episode，总量未下降，pair 构成却改变了。不能说 hook 对所有重叠都起到压制作用。
- 配对 seed/episode 顺序不是确定性轨迹证明；matcher 回放一致性也不是两组轨迹完全一致的证明。
- 未做 family 合并、执行消融或 held-out 泛化，不能直接宣称重复 skill 可删，也不能从旁路触发推断 rescue 效果。

## 产物与复现

- 汇总与 task/pair 数据：libero_pro_c4_shadow_overlap_results.json。
- 完整 600 ep 逐 query 的命中集、时间、失败谓词、观测 mode：libero_pro_c4_shadow_overlap_full.json.gz，解压为 JSON。原始传感状态 trace 仍在启智 run root。
- 统计入口：scripts/recovery/skill_pipeline/analyze_shadow_overlap_core60.py。
- 冻结 runtime HEAD：7128c1ea6280c227e48561e621fe9da8604c5a6d
- 冻结 matcher SHA256：faaf1c8251484f5d8bfc7ebc1231b072b235e35adbf89940a2cfde02bb023a2c
- Pack index SHA256：b9a56ea310dd5577ca7fd7a142fadb69344e7f26ab0c48654e5c3fb3adee8ccb
- 原 pack 全文件哈希沿用 run root/checkpoint_sha256.txt。结果 JSON 另记录分析脚本 SHA256。

本次通过已安装 Inspire 的 Jupyter transport 在同一 xinghanbo-eval 执行内存中的统计代码并下载结果，不向远端写脚本、不覆盖原日志，不运行 VLA/GPU 推理。

直接复现时，将统计脚本放到共享盘独立分析目录，调用原实验 Python。下面 /path/to 为需替换的路径，不是本次已执行路径：

```bash
/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/bin/python \
  /path/to/analyze_shadow_overlap_core60.py \
  --run-root /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006 \
  --json-output /path/to/new_shadow_overlap.json
```
