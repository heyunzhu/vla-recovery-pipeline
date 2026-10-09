# LIBERO-Pro C4 Skill 触发目录与泛化评估

## 1. 文档目的

本文档汇总 C4 frozen skill pack 中全部 18 个 trigger skill 的：

- 静态职责与 `applies_to` 条件；
- 动态 trigger 条件；
- Core-60 中的实际适用、触发、winner 与最终成功情况；
- 已被实验证明的泛化范围；
- 当前泛化风险及下一步应做的最小测试。

统计来自 C4 在 6 个 suite 上的 300 个 episode、8107 次 query。`适用`表示 `applies_to.passed=true`；`触发`表示 `would_fire=true`；`winner`表示该 query 实际选择了此 skill。一个 episode 可以多次触发，所以 query 数与 episode 数不可直接互换。

“winner 成功”使用 episode 最终 success，只表示相关性，不表示 recovery 对成功的严格因果贡献。

## 2. 泛化等级

| 等级 | 含义 |
| --- | --- |
| G0 | 没有有效性证据：未触发、未成为 winner，或触发后没有成功 |
| G1 | 仅在一个固定任务模板或单一 suite 中验证 |
| G2 | 已跨 task/swap 初始化变体，或跨多个 suite 验证，但对象与语言模板基本不变 |
| G3 | 已跨未见语言、对象、目标或组合进行系统验证 |

本轮最高只能评到 G2，因为尚未测试语义保持的语言改写、新对象类别、新目标容器和 held-out 组合。

## 3. 总览

| Skill | P | 适用 query / episode | 触发 query / episode | Winner episode | Winner 成功 | 等级 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | 72 | 588 / 25 | 7 / 7 | 6 | 6/6 | G1 |
| `black_bowl_next_to_plate_wrong_object_handoff` | 71 | 183 / 10 | 16 / 3 | 3 | 2/3 | G1 |
| `black_bowl_not_between_wrong_object_handoff` | 70 | 178 / 5 | 3 / 3 | 3 | 1/3 | G1 |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | 78 | 404 / 15 | 5 / 5 | 5 | 4/5 | G1 |
| `bowl_cabinet_target_holding_handoff` | 63 | 0 / 0 | 0 / 0 | 0 | — | G0 |
| `bowl_cookie_box_wrong_bowl_handoff` | 71 | 383 / 10 | 0 / 0 | 0 | — | G0 |
| `bowl_plate_pick_lost_or_wrong_intent` | 55 | 2265 / 105 | 428 / 92 | 92 | 63/92 | **G2** |
| `cream_cheese_bowl_wrong_object_intent` | 60 | 90 / 5 | 5 / 5 | 5 | 4/5 | G1 |
| `cream_cheese_rack_wrong_object_handoff` | 71 | 42 / 5 | 5 / 5 | 5 | 5/5 | G1 |
| `object_basket_bbq_orange_precontact_wrong_intent` | 78 | 153 / 20 | 20 / 20 | 20 | 20/20 | **G2** |
| `object_basket_cream_cheese_precontact_wrong_intent` | 77 | 264 / 10 | 4 / 4 | 4 | 2/4 | G1 |
| `object_basket_cream_tomato_q5_wrong_intent_window` | 79 | 332 / 20 | 9 / 9 | 9 | 9/9 | G1 |
| `object_basket_persistent_wrong_intent_group_a` | 76 | 844 / 50 | 47 / 45 | 45 | 38/45 | **G2** |
| `object_basket_salad_dressing_precontact_wrong_intent` | 76 | 131 / 10 | 10 / 10 | 10 | 9/10 | **G2** |
| `object_basket_tomato_persistent_wrong_intent` | 75 | 68 / 10 | 5 / 5 | 5 | 5/5 | G1 |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | 74 | 607 / 10 | 19 / 5 | 5 | **0/5** | G0 |
| `wine_bottle_bowl_wrong_object_handoff` | 72 | 236 / 10 | 9 / 9 | 9 | 7/9 | G1 |
| `wine_bottle_plate_wrong_object_handoff` | 71 | 140 / 5 | 3 / 3 | 3 | 3/3 | G1 |

## 4. Spatial / bowl family

### 4.1 `bowl_plate_pick_lost_or_wrong_intent`

- **职责**：通用 bowl→plate 恢复；在 VLA 仍空手、处于 open pick 状态并已靠近真实 target 时接管。
- **Applies-to**：语言包含 bowl 与 plate；target 为 bowl；BDDL goal surface 为 plate。
- **Trigger**：`handempty_or_unconfirmed`；aperture > 0.025；pick status 为 open；target 距 EE < 0.16m；预测 XY 距离 < 0.08m。
- **实际触发**：适用 2265 query / 105 episode；触发并成为 winner 428 query / 92 episode；最终成功 63/92。
- **覆盖范围**：goal-swap 5 episode、spatial-task 37、spatial-swap 50；对应成功为 5、25、33。
- **泛化判断：G2**。这是当前最接近 family-level skill 的 trigger，已有跨三个 suite 的证据。但它仍绑定 bowl/plate 名称，尚无 plate→tray 或 unseen bowl 的证明。
- **风险**：适用范围过宽，与多个专用 spatial skill 重叠；成功率约 68%，执行稳定性仍有限。

### 4.2 `black_bowl_not_between_wrong_object_handoff`

- **职责**：处理“不是位于 plate 与 ramekin 之间的 black bowl”这一特定关系描述。
- **Applies-to**：语言必须命中 `not between ... plate/ramekin`；target 为第二个 black bowl；goal 为 plate。
- **Trigger**：空手、gripper open、intent 不是 target、错误意图持续 ≥2、margin >0.03、target 距 EE <0.35m。
- **实际触发**：适用 178 query / 5 episode；触发并成为 winner 3 episode；最终成功 1/3。
- **泛化判断：G1**。只验证了单一关系模板，且实际成功较弱。
- **风险**：高度依赖自然语言中的 `not between` 表达；换成 “the other bowl” 或重排参照物顺序可能直接失配。

### 4.3 `black_bowl_next_to_plate_wrong_object_handoff`

- **职责**：处理 next-to-plate 关系下的错误 bowl intent。
- **Applies-to**：语言必须同时描述 black bowl、next to plate 和 place on plate；target/goal 分别为 bowl/plate。
- **Trigger**：空手、open、错误意图持续 ≥4、margin >0.03、intent XY <0.085m、target future XY >0.12m、target 距 EE <0.33m。
- **实际触发**：适用 183 query / 10 episode；在 3 episode 中触发，产生 16 次 rule 调用；最终成功 2/3。
- **泛化判断：G1**。仅有单一关系模板内证据。
- **风险**：多次恢复调用说明触发后执行并不稳定；数值窗口较多，容易在轻微几何偏移后形成 coverage hole。

### 4.4 `black_bowl_cabinet_top_to_plate_wrong_object_handoff`

- **职责**：从 cabinet top 取 black bowl 放到 plate；在持续接近错误 bowl 时接管。
- **Applies-to**：语言包含 black bowl、cabinet/top、plate；target 为 black bowl；goal 为 plate。
- **Trigger**：空手、open、错误 intent、nearest pickable 不是 target、target 静止、持续 ≥4、margin >0.1、intent XY <0.12m、target future XY >0.18m、target 距 EE >0.18m。
- **实际触发**：适用 588 query / 25 episode；触发 7 episode；6 episode 成为 winner且 6/6 成功。
- **泛化判断：G1**。模板内效果很好，但没有跨 goal 或新 furniture 验证。
- **风险**：与 wooden-cabinet early 版本职责高度重叠；一个 query 上曾同时完整触发。

### 4.5 `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff`

- **职责**：上一 skill 的 wooden-cabinet 专用早触发版本。
- **Applies-to**：显式要求语言出现 wooden cabinet。
- **Trigger**：与 cabinet skill 相同的错误 intent 结构，但将 margin 放宽到 0.08、intent XY 收紧到 0.06m、target future 阈值放宽到 0.1m、target 距离放宽到 >0.12m。
- **实际触发**：适用 404 query / 15 episode；winner 5 episode；最终成功 4/5。
- **泛化判断：G1**。它更像针对原 cabinet skill coverage hole 的 threshold patch，而不是独立抽象能力。
- **风险**：与 cabinet skill 有 78 次 query 同时适用；唯一一次 simultaneous `would_fire` 由本 skill 的 priority 78 胜出。

### 4.6 `bowl_cookie_box_wrong_bowl_handoff`

- **职责**：处理位于 cookie box 上的 bowl 被另一个 bowl 干扰的情况。
- **Applies-to**：语言要求 bowl on cookie(s) box 并放到 plate；target 为第一个 black bowl；goal 为 plate。
- **Trigger**：空手、open、错误 intent 持续 ≥4、margin >0.03、nearest pickable <0.25m、target 距 EE <0.35m。
- **实际触发**：适用 383 query / 10 episode，但从未满足完整 trigger，也从未成为 winner。
- **泛化判断：G0**。当前只有 applicability coverage，没有动态触发或有效性证据。
- **风险**：经常被通用 bowl skill 覆盖；可能是过时 skill、阈值过严，或者职责已被通用 skill subsume。

### 4.7 `bowl_cabinet_target_holding_handoff`

- **职责**：VLA 已抓住 bowl 后，接管 cabinet-top placement。
- **Applies-to**：bowl/cabinet 语言；排除 white bowl；goal surface 为 cabinet top。
- **Trigger**：target 距离与预测 XY 都 <0.19m，并且 holding 或 aperture <0.03。
- **实际触发**：在 C4 Core-60 中 0 applicable、0 trigger、0 winner。
- **泛化判断：G0**。本轮 benchmark 没有覆盖该职责，无法评估。
- **风险**：不是一定无效，也可能是当前 panel 缺少对应状态；需要专门的 holding-state probe 才能区分 dead skill 与 coverage gap。

## 5. Goal family

### 5.1 `cream_cheese_bowl_wrong_object_intent`

- **职责**：cream cheese→bowl 时，错误对象 intent 下接管。
- **Applies-to**：语言包含 cream cheese 与 bowl；target 为 cream cheese；goal surface 为 bowl。
- **Trigger**：空手、open、intent 不是 target、target 距 EE <0.37m、target future XY >0.18m、margin >0.1。
- **实际触发**：适用并触发 5 episode，均成为 winner；最终成功 4/5，全部位于 goal-swap。
- **泛化判断：G1**。只验证了固定 object-goal pairing。
- **风险**：语言和对象名绑定明显，无法说明对其他 flat-box→container 任务可迁移。

### 5.2 `cream_cheese_rack_wrong_object_handoff`

- **职责**：cream cheese→rack 的错误对象恢复。
- **Applies-to**：语言显式包含 cream cheese 与 rack；target 为 cream cheese；goal 为 rack/top region。
- **Trigger**：空手、open、错误 intent、nearest 不是 target、持续 ≥3、margin >0.03、nearest <0.28m、target <0.265m 且 target 静止。
- **实际触发**：适用、触发并成为 winner 5 episode；最终成功 5/5，全部位于 goal-task。
- **泛化判断：G1**。模板内证据强，但没有跨语言、对象或 rack 几何验证。

### 5.3 `plate_stove_open_wrong_intent_pregrasp_handoff`

- **职责**：plate→stove 时，在 open-hand wrong-intent 阶段提前接管。
- **Applies-to**：plate/stove 语言；target 为 plate；goal surface 为 stove/cook region。
- **Trigger**：空手、open、pick status open、错误 intent 持续 ≥4、nearest 不是 target、target 距离处于 0.12–0.22m、nearest <0.2m。
- **实际触发**：适用 607 query / 10 episode；在 5 episode 中触发 19 次；最终成功 **0/5**。
- **泛化判断：G0**。它证明了 detector 可以触发，但没有证明 recovery capability 有效。
- **风险**：重复触发而持续失败，应首先标记为 ineffective skill，不能用高 trigger recall 掩盖执行失败。

### 5.4 `wine_bottle_bowl_wrong_object_handoff`

- **职责**：wine bottle→bowl 的错误对象恢复。
- **Applies-to**：语言要求 wine bottle in bowl；target 为 wine bottle；goal 为 bowl。
- **Trigger**：空手、open、错误 intent、nearest 不是 target、持续 ≥4、margin >0.04、target 距 EE <0.25m。
- **实际触发**：适用 10 episode；9 episode 中成为 winner；最终成功 7/9。
- **泛化判断：G1**。单一 object-goal pairing 内表现较好。

### 5.5 `wine_bottle_plate_wrong_object_handoff`

- **职责**：wine bottle→plate 的错误对象恢复。
- **Applies-to**：语言要求 wine bottle on plate；target 为 wine bottle；goal 为 plate。
- **Trigger**：空手、open、错误 intent 持续 ≥4、margin >0.03、nearest <0.22m、intent XY <0.035m、target <0.25m。
- **实际触发**：适用 5 episode；3 episode 触发并成为 winner；最终成功 3/3。
- **泛化判断：G1**。样本少且仅一个固定模板。
- **风险**：与 wine-bottle→bowl 分成两个独立 trigger，表明能力仍按具体 goal 分片，尚未形成通用 bottle-placement skill。

## 6. Object→basket family

### 6.1 `object_basket_persistent_wrong_intent_group_a`

- **职责**：alphabet soup、butter、chocolate pudding、ketchup、milk 五类对象的持续错误 intent 恢复。
- **Applies-to**：精确列举五类 target；goal 必须为 basket。
- **Trigger**：空手、open、intent 不是 target、错误 intent 持续 ≥4、margin >0。
- **实际触发**：适用 844 query / 50 episode；45 episode 中触发，产生 47 次 rule 调用；最终成功 38/45。object-task 为 16/20，object-swap 为 22/25。
- **泛化判断：G2**。已跨 task/swap 初始化分布，并在五个对象间共享同一 trigger。
- **风险**：对象集合是硬编码枚举；尚不能证明对第六个未见对象具备 category-level 泛化。

### 6.2 `object_basket_bbq_orange_precontact_wrong_intent`

- **职责**：BBQ sauce 与 orange juice 的 precontact wrong-intent 恢复。
- **Applies-to**：精确列举两种对象；goal 为 basket。
- **Trigger**：空手、open、持续错误 intent ≥4、margin >0.03、intent XY <0.03m、target future >0.12m、nearest 距离 0.08–0.20m、pick status 为 non-target intent。
- **实际触发**：20 episode 全部成为 winner且 20/20 成功；object-task 与 object-swap 各 10/10。
- **泛化判断：G2**。当前跨初始化泛化最强，但仍是两种具名对象上的近分布证据。
- **风险**：大量连续阈值可能对位置与诊断噪声敏感。

### 6.3 `object_basket_salad_dressing_precontact_wrong_intent`

- **职责**：salad dressing 的 precontact wrong-intent 恢复。
- **Applies-to**：精确 salad dressing；goal 为 basket。
- **Trigger**：空手、open、持续 ≥4、intent XY <0.05m、target 距离 >0.18m、nearest 距离 0.10–0.16m、pick status open。
- **实际触发**：10 episode 全部成为 winner；object-task 5/5、object-swap 4/5，总计 9/10。
- **泛化判断：G2**。有 task/swap 证据，但没有跨对象共享。

### 6.4 `object_basket_cream_cheese_precontact_wrong_intent`

- **职责**：cream cheese basket-placement 的 precontact 窗口。
- **Applies-to**：精确 cream cheese→basket。
- **Trigger**：持续错误 intent ≥4、margin >0.03、intent XY <0.05m、target future >0.12m、nearest 距离 0.10–0.16m、non-target intent。
- **实际触发**：虽然在 task/swap 共 10 episode、264 query 中适用，但只在 object-swap 的 4 episode 成为 winner，最终成功 2/4。
- **泛化判断：G1**。适用范围跨两个变体，但有效触发只出现在 swap，且成功有限。
- **风险**：与 q5-window skill 大量重叠，功能被按距离/时间窗口切碎。

### 6.5 `object_basket_tomato_persistent_wrong_intent`

- **职责**：tomato sauce 的持续错误 intent 恢复。
- **Applies-to**：精确 tomato sauce→basket。
- **Trigger**：空手、open、持续 ≥4、margin >0、target future XY >0.12m。
- **实际触发**：适用 task/swap 共 10 episode；只在 object-swap 的 5 episode 成为 winner，最终成功 5/5。
- **泛化判断：G1**。尚未证明跨初始化方向稳定，因为 object-task 的 winner 被 q5-window skill 覆盖。

### 6.6 `object_basket_cream_tomato_q5_wrong_intent_window`

- **职责**：补充 cream cheese/tomato 在 persistence 不足时的 q5 早期窗口。
- **Applies-to**：cream cheese 或 tomato sauce→basket。
- **Trigger**：至少六步历史、空手、open、错误 intent 持续 ≥1、margin >0.1、intent XY <0.085m、target future >0.19m、nearest 距离 0.20–0.24m。
- **实际触发**：适用 332 query / 20 episode；只在 object-task 的 9 episode 成为 winner，最终成功 9/9。
- **泛化判断：G1**。模板内有效，但其职责本身就是针对既有 trigger coverage hole 的窄窗口 patch。
- **风险**：对 query history、距离区间和当前轨迹形态高度敏感，是最应接受边界扰动测试的 skill 之一。

## 7. 当前泛化结论

### 7.1 已经被支持的结论

1. 通用 `bowl_plate_pick_lost_or_wrong_intent` 能跨 goal-swap、spatial-task、spatial-swap 使用，具备一定 family-level transfer。
2. 三个 object trigger 已在 object-task/object-swap 两种初始化分布上保持效果：group-A、BBQ/orange、salad-dressing。
3. C4 的跨 family 门控较好：8107 次 query 中只有 1 次出现两个 skill 同时 `would_fire`。

### 7.2 尚不能声称的结论

当前没有证据证明 skill 能泛化到：

- 同义改写、语序变化和对象别名；
- 未见对象类别；
- 新 goal surface；
- 超出当前距离阈值区间的几何布局；
- 新 object × goal × relation 组合；
- 长期 agentic state 或多任务历史下的恢复。

因此，目前应表述为：**具有一定的近分布、跨初始化泛化，但开放式语义与组合泛化未知。**

## 8. 泛化风险信号

1. **模板绑定**：多数 `task_language_matches` 直接写死对象与 goal 名称。
2. **阈值 patch 化**：object family 通过 0.10–0.16m、0.20–0.24m、q5、persistence 1/4 等窗口切分职责。
3. **skill 碎片化**：同一 wrong-object recovery 被按 not-between、next-to、cabinet、wooden-cabinet 等模板拆开。
4. **职责闲置**：两个 trigger 在 Core-60 中从未成为 winner。
5. **触发与有效性脱节**：plate-stove 能稳定触发但最终 0/5。
6. **范围重叠**：1664/8107 query 同时有多个 applicable skill；当前虽然很少同时触发，但扰动后可能出现 collision 或 coverage hole。

## 9. 建议的泛化评测协议

对每个已有成功 episode，保存原始状态并构造四类成对 probe：

1. **语言不变性**：同义改写、主动/被动、关系词替换、对象别名；环境和 BDDL 不变。
2. **几何连续扰动**：目标与 distractor 平移 ±1/2/4/8cm，或旋转 ±10/20°；任务语义不变。
3. **对象/目标替换**：保持 affordance 与失败模式，替换为未列入 regex 的相似对象或 goal surface。
4. **组合留出**：学习时可见 object A→goal X 与 object B→goal Y，测试 A→Y 或 B→X。

每个 probe 同时报告：

- applicability recall；
- trigger recall；
- winner consistency；
- coverage-hole rate；
- simultaneous-trigger rate；
- `P(success | expected skill fired)`；
- 相对原 episode 的 paired success delta。

优先顺序建议为：

1. `object_basket_cream_tomato_q5_wrong_intent_window`：最典型的窄窗口 patch；
2. cabinet 与 wooden-cabinet 两个重叠 skill：检验 priority 边界稳定性；
3. `bowl_plate_pick_lost_or_wrong_intent`：检验最强 family-level skill 的跨 goal 泛化；
4. `object_basket_persistent_wrong_intent_group_a`：用一个 held-out object 判断它学到的是错误意图抽象还是对象枚举。

## 10. 数据位置

- 静态 skill 定义：C4 checkpoint 的 `skills/fail_only/trigger/`。
- C4 query 级统计：远端 run root 下 `skill_overlap_c4.json`。
- 本地统计副本：`tmp/inspire/skill_overlap_c4.json`。
- 触发归因程序：`tmp/inspire/analyze_skill_overlap.py`。
- 与遗忘/BWT 的联合分析见 `docs/results/libero_pro_core60_trigger_attribution_report.md`。

## 11. Task-level 实际触发表

这一表用于澄清 G1：G1 不是“只有自己的 task 才会通过 applicability”，而是“目前只有自己的固定语义模板提供了有效触发/成功证据”。`A-only` 表示通过 `applies_to` 但从未完整触发；`F/W/S` 分别是发生过 `would_fire`、成为 winner、winner 后成功的 episode 数。

| Skill | 实际触发任务（F/W/S episode） | 只适用但未触发的任务 |
| --- | --- | --- |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | spatial-task T3 1/0/0；T7 5/5/5；T9 1/1/1 | spatial-swap T3、T10 |
| `black_bowl_next_to_plate_wrong_object_handoff` | spatial-task T2 3/3/2 | spatial-swap T5 |
| `black_bowl_not_between_wrong_object_handoff` | spatial-task T1 3/3/1 | — |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | spatial-task T3 5/5/4 | spatial-swap T3、T10 |
| `bowl_cabinet_target_holding_handoff` | 无 | 无；当前 benchmark 未覆盖对应状态 |
| `bowl_cookie_box_wrong_bowl_handoff` | 无 | spatial-task T8；spatial-swap T7 |
| `bowl_plate_pick_lost_or_wrong_intent` | goal-swap T4；spatial-task T1–T10；spatial-swap T1–T10，共 92/92/63 | — |
| `cream_cheese_bowl_wrong_object_intent` | goal-swap T7 5/5/4 | — |
| `cream_cheese_rack_wrong_object_handoff` | goal-task T8 5/5/5 | — |
| `object_basket_bbq_orange_precontact_wrong_intent` | object-task T3/T10、object-swap T2/T8，各 5/5/5，总计 20/20/20 | — |
| `object_basket_cream_cheese_precontact_wrong_intent` | object-swap T5 4/4/2 | object-task T1 |
| `object_basket_cream_tomato_q5_wrong_intent_window` | object-task T1 4/4/4；T9 5/5/5 | object-swap T5、T10 |
| `object_basket_persistent_wrong_intent_group_a` | object-task T2/T6/T7/T8；object-swap T1/T3/T4/T6/T7，共 45/45/38 | object-task T5（alphabet soup） |
| `object_basket_salad_dressing_precontact_wrong_intent` | object-task T4 5/5/5；object-swap T9 5/5/4 | — |
| `object_basket_tomato_persistent_wrong_intent` | object-swap T10 5/5/5 | object-task T9 |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | goal-task T5 5/5/0 | goal-swap T3（push plate to front of stove） |
| `wine_bottle_bowl_wrong_object_handoff` | goal-task T7 4/4/4；T9 5/5/3 | — |
| `wine_bottle_plate_wrong_object_handoff` | goal-task T4 3/3/3 | — |

该表暴露出三种不同现象：

1. **真正的单模板 skill**：如 not-between、cream-cheese rack、wine-bottle plate，只在一个固定任务模板中适用并触发。
2. **跨 task/swap applicability，但没有进入 trigger 窗口**：如 next-to-plate、wooden-cabinet、cream-cheese、tomato。语义相同的 swap task 会通过 `applies_to`，但轨迹状态没有满足原有动态谓词。这是泛化风险线索，而不是单独成立的泛化失败证据：若 swap 轨迹根本没有出现同一种 failure state，不触发是正确行为；只有在相同错误行为已经出现、trigger 仍漏检时，才是 trigger recall 失败。
3. **Applicability 过宽**：plate-stove skill 会把 goal-swap 的 “push the plate to the front of the stove” 判为适用，但从不触发；generic bowl skill 则覆盖几乎所有 bowl→plate 任务。这需要用 minimal-pair false-positive 测试区分合理 family coverage 与错误职责扩张。

Priority 只在多个 skill 已经同时 `would_fire=true` 后参与仲裁。本轮 8107 次 query 只有 1 次发生这种情况：wooden-cabinet task 上 cabinet 与 wooden-cabinet-early 两个 skill 同时触发，priority 78 的 early skill 胜出。其余“适用但未触发”不是 priority 不够，而是至少一个动态 trigger predicate 为 false。
