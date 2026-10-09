# LIBERO-Pro Core-60：触发级归因与“为何未见明显遗忘”

## 1. 结论先行

本次 1800 个 episode 的 trace 归因不支持“新增 object skills 通过错误匹配或优先级竞争，覆盖了旧 spatial skills”这一解释。

最关键的证据是 C3→C4 的 `libero_spatial_task`：成功率从 78% 降至 70%，包含 11 个旧成功丢失和 7 个新增成功；但 11 个丢失样本全部仍由 C3 时相同的旧 skill 首先触发，没有 winner switch，也没有 trigger 消失。两侧首次触发的中位数都是 query 6。失败差异主要出现在触发后的规划、抓取确认和轨迹跟踪阶段。

所以目前最稳妥的判断是：

1. clean/frozen modular pack 的路由隔离有效，新增 family 很少污染旧 family；
2. 当前设置缺少会迫使旧知识被覆盖、压缩或淘汰的机制，因此天然不容易产生灾难性遗忘；
3. 已观察到的 episode churn 主要是“同一 winner、同一触发时刻附近、执行结果翻转”，其中混合了执行器/物理仿真的不稳定性，以及少量共享 profile 演化的影响；
4. 因而本轮结果应被定义为“低干扰的 clean modular retention control”，而不是对 skill-based continual learning 不会遗忘的一般性证明。

## 2. 触发级总表

下表中的“触发成功”表示该 episode 中出现 recovery rule 调用且最终任务成功，不表示该成功一定由 recovery 因果造成。`多次触发` 表示一个 episode 中记录了不止一次 rule 调用。

| 条件 / suite | 成功 | 触发 episode | 触发后成功 | 未触发成功 | 多次触发 | 首次触发 query 中位数 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C0 / goal-swap | 12/50 | 10 | 9/10 | 3/40 | 0 | 6 |
| C0 / spatial-task | 28/50 | 33 | 28/33 | 0/17 | 20 | 7 |
| C0 / goal-task | 8/50 | 5 | 0/5 | 8/45 | 5 | 5 |
| C0 / spatial-swap | 31/50 | 50 | 31/50 | 0/0 | 23 | 6 |
| C1 / goal-swap | 10/50 | 9 | 6/9 | 4/41 | 3 | 7 |
| C1 / spatial-task | 37/50 | 48 | 37/48 | 0/2 | 18 | 6 |
| C1 / goal-task | 7/50 | 5 | 0/5 | 7/45 | 5 | 6 |
| C1 / spatial-swap | 32/50 | 50 | 32/50 | 0/0 | 24 | 6 |
| C2 / goal-swap | 13/50 | 10 | 9/10 | 4/40 | 1 | 6 |
| C2 / spatial-task | 38/50 | 46 | 38/46 | 0/4 | 19 | 6 |
| C2 / goal-task | 20/50 | 17 | 12/17 | 8/33 | 5 | 6 |
| C2 / spatial-swap | 31/50 | 50 | 31/50 | 0/0 | 19 | 6 |
| C3 / goal-swap | 13/50 | 10 | 8/10 | 5/40 | 2 | 6.5 |
| C3 / spatial-task | 39/50 | 47 | 39/47 | 0/3 | 21 | 6 |
| C3 / goal-task | 18/50 | 17 | 11/17 | 7/33 | 6 | 6 |
| C3 / spatial-swap | 32/50 | 50 | 32/50 | 0/0 | 25 | 6 |
| C4 / goal-swap | 12/50 | 10 | 9/10 | 3/40 | 2 | 6 |
| C4 / spatial-task | 35/50 | 48 | 35/48 | 0/2 | 24 | 6 |
| C4 / goal-task | 21/50 | 22 | 15/22 | 6/28 | 7 | 6 |
| C4 / spatial-swap | 33/50 | 50 | 33/50 | 0/0 | 22 | 6 |
| C4 / object-task | 45/50 | 44 | 40/44 | 5/6 | 6 | 5 |
| C4 / object-swap | 43/50 | 49 | 43/49 | 0/1 | 5 | 6 |

两点值得注意：

- `spatial-swap` 在 C0 就已经做到 31/50，且 50/50 episode 都触发同一个 `bowl_plate_pick_lost_or_wrong_intent`。这解释了为什么其 FWT 很高、正式学习阶段 C2→C3 反而几乎没有净增长：早期 skill 已覆盖了这组 swap。
- `object-task/object-swap` 在 C3 完全没有 recovery 触发；C4 分别新增 44/49 个触发 episode，并带来 40/43 个新增成功且无旧成功丢失。这是新增 family 的真实 acquisition，而非基线偶然波动。

## 3. C3→C4 spatial-task 的 18 个翻转样本

| Task/Episode | 方向 | C3→C4 首个 winner | 首次 query | rule 调用次数 | C4 主要异常 |
| --- | --- | --- | ---: | ---: | --- |
| 1/0 | gain | 相同：not-between | 5→5 | 3→3 | 有失败事件，但后续恢复成功 |
| 1/3 | loss | 相同：not-between | 6→5 | 1→4 | lift 未确认、未抓稳、motion budget |
| 1/4 | loss | 相同：not-between | 4→4 | 3→4 | lift 未确认、未抓稳、motion budget |
| 2/1 | gain | 相同：next-to-plate | 7→6 | 4→3 | tracking/motion budget 后恢复 |
| 3/4 | loss | 相同：cabinet-top-early | 6→6 | 1→3 | tracking stalled、planning failed |
| 4/2 | loss | 相同：generic bowl-plate | 5→5 | 1→3 | motion budget / tracking budget |
| 5/3 | loss | 相同：generic bowl-plate | 8→9 | 1→4 | tracking stalled、lift 未确认 |
| 6/2 | loss | 相同：generic bowl-plate | 7→7 | 4→4 | tracking stalled、未抓稳 |
| 7/1 | gain | 相同：cabinet-top | 7→7 | 4→1 | C3 规划失败，C4 未复现 |
| 7/3 | gain | 相同：cabinet-top | 5→5 | 4→3 | C3 抓取接近失败，C4 未复现 |
| 8/0 | loss | 相同：generic bowl-plate | 6→7 | 1→2 | trace 中无明确严重错误，最终状态未达成 |
| 8/3 | loss | 相同：generic bowl-plate | 8→7 | 1→3 | 无可满足 particle / tracking stalled |
| 9/0 | gain | 相同：generic bowl-plate | 10→7 | 4→2 | C4 更早触发、重试更少 |
| 9/2 | loss | 相同：generic bowl-plate | 5→5 | 1→4 | tracking stalled、lift 未确认 |
| 9/3 | loss | 相同：generic bowl-plate | 8→7 | 4→1 | trajectory tracking budget |
| 9/4 | gain | C3 未触发→cabinet-top | 无→21 | 0→1 | 唯一由新增触发解释的 gain |
| 10/0 | gain | 相同：generic bowl-plate | 4→4 | 3→1 | C4 重试更少 |
| 10/1 | loss | 相同：generic bowl-plate | 4→4 | 1→2 | trajectory stalled / budget |

这里最重要的不是某个错误字符串的绝对次数，而是结构：**11 个 loss 全部是 same-winner；6/7 个 gain 也是 same-winner。** 这是双向执行 churn，而非 object family 抢占 spatial family。

## 4. 全部相邻 checkpoint 的翻转类型

把 30 个“相邻 checkpoint × suite”比较中的所有成功状态翻转合并：

| 翻转类型 | Gain | Loss |
| --- | ---: | ---: |
| 新增 trigger | 151 | 2 |
| 相同 winner | 51 | 58 |
| 两边都未触发 | 8 | 8 |
| trigger 消失 | 0 | 5 |
| winner switch | 5 | 1 |

因此，所有 74 个 loss 中只有 **1 个**与 winner switch 同时发生；58 个发生在相同 winner 下。新增 skill 的主要作用是填补过去不触发的区域，而不是改写已有 winner。

## 5. 为什么这轮几乎没有遗忘

### 5.1 主要原因确实是 setting

当前系统不是把新知识持续写进同一组 VLA 权重，而是把 skill 作为外部模块追加到 pack。新增 skill 不会直接覆盖旧 skill 的表示。只要旧文件还在、路由条件仍匹配，旧能力天然容易保留。

与此同时，本轮使用的是 clean/frozen checkpoints。早期遗留的错误 skill 已被清理或隔离，这会把“历史学习过程中的脏状态、错误规则累积和修修补补”从评测对象中移除。它回答的是“整理后的模块化记忆能否保留”，不是“在线学习全过程是否自然退化”。

### 5.2 强 `applies_to` 门控把 family 隔离开了

实际 C4 spatial trace 中，新增 object skills 会进入候选诊断，但因语言、target 或 goal 不匹配而在 `applies_to` 阶段被拒绝；旧 spatial skill 仍然胜出。全局统计中只有 1 个 loss 伴随 winner switch，与这个观察一致。

### 5.3 没有容量压力，也没有淘汰机制

skill 数从 10 增至 36，但没有固定 memory budget、top-k 保留、context token 上限、压缩或替换约束。只加不删时，系统更接近增长型规则库，而不是受限容量的 continual learner。很多论文中的遗忘来自共享参数更新或有限资源竞争，这两种压力在这里都很弱。

### 5.4 当前回放不是完整历史系统回放

所有 checkpoint 都运行在同一个当前 runner、BDDL、cuTAMP backend 和 recovery budget 上。这控制了基础设施变量，适合比较 skill pack；但它也会用现代执行器“托住”旧 pack，无法暴露历史时点中 engine 与 skill 共同演化造成的退化。

### 5.5 episode 独立重置，缺少长期 agentic state 漂移

每个 episode 都从固定 initial state 和 seed 重新开始，pack 之间没有长期记忆、错误摘要、任务历史或自我修改状态持续累积。因而不会出现长链任务中“旧状态污染下一任务”的级联退化。

### 5.6 小样本与双向 churn 会遮蔽净变化

每个 cell 只有 10 tasks × 5 episodes。`spatial-task` C3→C4 有 18/50 的结果翻转，但净值只有 -4；`spatial-swap` 每次也有 13–15 个双向翻转，总成功率却长期停在 62%–66%。只看 aggregate success 会把这种不稳定性误读成稳定保持。

## 6. C3 与 C4 的共同组件审计

C3 与 C4 checkpoint 有 38 个同路径文件，其中 30 个字节级完全一致，18 个是 C4 新增文件，8 个共同文件发生变化。旧 spatial trigger 文档（包括 `black_bowl_not_between_wrong_object_handoff` 和 `bowl_plate_pick_lost_or_wrong_intent`）在 C3/C4 间 hash 相同；变化集中在 pack index、capabilities 以及共享 geometry/grasp/repair profiles。

这意味着：

- 可以排除“旧 trigger 本身被改坏”作为 C3→C4 spatial loss 的主要解释；
- 但不能完全排除共享执行 profile 的演化影响。例如 C4 新增了 orientation reset、contact allowance 和新的 grasp/geometry 支持；虽然主要服务 object family，共享代码路径仍可能改变执行行为；
- 要把“共享组件干扰”和“执行随机性”分开，需要做一个严格消融：以 C3 为底，只追加 C4 object triggers/index，不替换任何共同 profile；再与完整 C4 对照。

## 7. 下一轮应如何测

建议把现有 full matrix 保留为 control，并追加三组最有信息量的实验：

1. **C4 append-only 消融**：C3 公共文件完全冻结，只追加 object skills；与完整 C4 在相同 18 个 churn episode 上重复 10–20 次。它直接检验 shared-profile interference。
2. **paired repeated replay**：优先重复 spatial-task C3/C4 的 18 个翻转 episode。若同一 checkpoint 自身也高频翻转，则当前 -8pp 主要是执行方差；若 C4 稳定更差，才有局部 backward interference 的证据。
3. **as-run / capacity-stress 轨道**：加入未经 clean 的历史 pack，并设置真实部署会遇到的 memory/context/top-k 预算。只有在这种设置下，才能检验错误 skill 累积、路由拥挤和记忆淘汰造成的自然退化。

若研究问题是“持续学习中的 skill 能力为什么退化”，下一轮的主要观测量不应只含 success/BWT，还应同时报告：trigger coverage、first-trigger latency、winner retention、wrong-winner rate、recovery retry count、planning/grasp/execution failure stage，以及 same-checkpoint repeat variance。

## 8. 数据位置与口径

- 完整触发归因 JSON：远端 run root 下 `trigger_attribution.json`；本地分析副本为 `tmp/inspire/trigger_attribution.json`。
- 分析程序：`tmp/inspire/analyze_trigger_attribution.py`。
- 错误计数是 trace event 次数，一个 episode 可贡献多次同类错误；不能直接当作失败 episode 数。
- rule 的 `success=true` 只表示该次规则 grounding 成功，不等于最终任务成功；本报告的“触发后成功”使用 `episode.json` 的最终 success。
