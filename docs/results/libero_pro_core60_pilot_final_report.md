# LIBERO-Pro Core-60 Continual Skill Replay：最终结果报告

## 1. 摘要

本报告汇总 `continual_skill_core60_pilot_20261006` 的完整结果。实验包含 6 个条件（VLA-only 与 C0-C4）、6 个 suite、每个 suite 10 个任务、每个任务 5 个配对 episode，共 36 个 job、1800 个有效 episode。

主要结论如下：

1. **没有检测到整体灾难性遗忘。** 四个旧阶段 panel 的总体 Backward Transfer（BWT）为 **0.0 个百分点**，task-cluster bootstrap 95% CI 为 **[-6.0, +7.5]**。
2. **能力获取高度不均匀。** goal-task 在 C2 获得 +26pp，object-task/object-swap 在 C4 分别获得 +80pp/+86pp；spatial-swap 在其名义学习阶段 C2→C3 仅增加 +2pp。
3. **Forward Transfer 是选择性的。** spatial-swap 在正式学习前已有 +50pp FWT，而 spatial-task、goal-task 与两个 object panel 的 FWT 分别为 0pp、+2pp、0pp、0pp。
4. **最终遗忘主要集中在 spatial-task。** 该 panel 从 C3 峰值 78% 降至 C4 的 70%，Final Forgetting 为 8pp，但 95% CI [0, 22] 仍包含 0。
5. **均值稳定掩盖了 episode 级 capability churn。** spatial-swap 的相邻 checkpoint 总成功率始终在 62%-66%，但每次更新都有 6-8 个旧成功丢失，同时被相近数量的新成功抵消。
6. **C4 object 学习形成了跨 task/swap 的 family-level 能力。** object-task 从 10% 升至 90%，object-swap 从 0% 升至 86%，分别净增 40 和 43 个配对成功，且没有旧成功丢失。

因此，这轮 clean/frozen skill replay **不支持“skill pack 普遍发生灾难性退化”这一强假设**；它支持更细的判断：模块化 skill memory 的总体 retention 很强，但存在局部遗忘、winner/coverage churn，以及不同 family 间显著不同的可迁移性。

## 2. 实验与统计口径

### 2.1 历史状态

| 条件 | 冻结时点 | Skill 数 |
| --- | --- | ---: |
| VLA-only | 不启用 skill recovery | 0 |
| C0 | goal-swap 学习后 | 10 |
| C1 | spatial-task 学习后 | 16 |
| C2 | goal-task 学习后 | 23 |
| C3 | spatial-swap 学习后 | 24 |
| C4 | object-task/object-swap 学习后 | 36 |

### 2.2 固定条件

- 相同 Pi0/OpenPI checkpoint；
- 相同当前 runner、BDDL、cuTAMP backend 与 recovery budget；
- 相同任务、episode seed 与 initial-state index；
- 每个 cell 为 10 tasks × 5 episodes；
- 两份缺失的 spatial-task init state 仅在 run-local overlay 中补充，并对所有条件复用；
- 先前两项失败 job 的 60 个半程 episode 已归档，不计入本报告。

因为每个 task 的 episode 数完全相同，suite 内 task-macro success 与 episode-micro success 数值相同。所有 checkpoint 差值均为配对差值；95% CI 使用 **20,000 次 task-cluster bootstrap**，以 task 为 cluster，固定随机种子 `20261007`。

### 2.3 指标定义

令 `R[i,j]` 为 checkpoint `Ci` 在 panel `j` 上的成功率。

- `Acquisition(j) = R[j,j] - R[j-1,j]`
- `FWT(j) = R[j-1,j] - R[VLA-only,j]`
- `BWT = mean_j<K(R[C4,j] - R[j,j])`
- `Final Forgetting(j) = max_i R[i,j] - R[C4,j]`
- `Net Gain(A→B) = 新增成功 episode - 新增失败 episode`

C4 同时学习 object-task 与 object-swap，因此 acquisition/FWT 对二者分别报告。BWT 只包含 C4 之前已经学过的 goal-swap、spatial-task、goal-task 和 spatial-swap。

## 3. 最终成功率矩阵

| 条件 | goal-swap | spatial-task | goal-task | spatial-swap | object-task | object-swap | 六 suite 平均 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| VLA-only | 6% | 56% | 12% | 12% | 10% | 0% | 16.0% |
| C0 | 24% | 56% | 16% | 62% | 10% | 0% | 28.0% |
| C1 | 20% | 74% | 14% | 64% | 10% | 0% | 30.3% |
| C2 | 26% | 76% | 40% | 62% | 10% | 0% | 36.0% |
| C3 | 26% | 78% | 36% | 64% | 10% | 0% | 35.7% |
| C4 | 24% | 70% | 42% | 66% | 90% | 86% | 63.0% |

从系统总体表现看，C4 相比 VLA-only 提高 47pp，相比 C0 提高 35pp。但这一总体增益主要由 C4 的 object family 贡献，不能解释为所有旧能力都同步改善。

## 4. 能力获取（Acquisition）

| Panel | 学习转移 | 学习前→学习后 | Δ | 95% CI | 新增成功 | 新增失败 | Net Gain |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| goal-swap | VLA→C0 | 6%→24% | +18pp | [0, 44] | 9 | 0 | +9 |
| spatial-task | C0→C1 | 56%→74% | +18pp | [-4, 42] | 14 | 5 | +9 |
| goal-task | C1→C2 | 14%→40% | **+26pp** | **[6, 50]** | 13 | 0 | +13 |
| spatial-swap | C2→C3 | 62%→64% | +2pp | [-10, 14] | 8 | 7 | +1 |
| object-task | C3→C4 | 10%→90% | **+80pp** | **[54, 100]** | 40 | 0 | +40 |
| object-swap | C3→C4 | 0%→86% | **+86pp** | **[72, 98]** | 43 | 0 | +43 |

只有 goal-task 与两个 object panel 的 95% CI 严格高于 0。spatial-task 虽有 +18pp 点估计，但新增 14 个成功的同时丢失 5 个旧成功，且收益集中于有限 task cluster，当前样本量下区间跨 0。spatial-swap 在 C3 的名义 acquisition 几乎为零，说明其主要能力在更早 checkpoint 已经形成。

若将 object-task/object-swap 先做 stage 内平均，五个学习阶段的平均 acquisition 为 29.4pp；该数值受 object 阶段巨大增益支配，应优先阅读逐 panel 结果。

## 5. Forward Transfer（FWT）

| 未来 Panel | 学习前 checkpoint | VLA→学习前 | FWT | 95% CI | 配对 Net Gain |
| --- | --- | ---: | ---: | ---: | ---: |
| spatial-task | C0 | 56%→56% | 0pp | [-12, 12] | 0 |
| goal-task | C1 | 12%→14% | +2pp | [0, 6] | +1 |
| spatial-swap | C2 | 12%→62% | **+50pp** | **[26, 72]** | +25 |
| object-task | C3 | 10%→10% | 0pp | [0, 0] | 0 |
| object-swap | C3 | 0%→0% | 0pp | [0, 0] | 0 |

主要发现：

- C0 在 spatial-task 上虽然触发并执行了大量 recovery，但其最终成功率与 VLA-only 完全相同；配对上新增 2 个成功、同时丢失 2 个基线成功。因此这里没有净 FWT。
- spatial-swap 的 +50pp 是唯一强且统计清晰的 FWT，说明 C0-C2 累积的 pick/place、空间 grounding 或 recovery executor 能迁移到尚未正式学习的 swap panel。
- object family 在 C4 之前完全没有 FWT：object-task 保持 10%，object-swap 保持 0%，且没有 recovery 触发。C4 的高 acquisition 因而是新覆盖的获得，而非此前能力的逐步积累。

若按五个学习阶段计算，并将两个 object panel 先取平均，stage-level FWT 为 13.0pp；它几乎全部由 spatial-swap 驱动。

## 6. Backward Transfer（BWT）

| 旧 Panel | 学会时状态→C4 | BWT component | 95% CI |
| --- | ---: | ---: | ---: |
| goal-swap | C0 24%→C4 24% | 0pp | [0, 0] |
| spatial-task | C1 74%→C4 70% | -4pp | [-18, 10] |
| goal-task | C2 40%→C4 42% | +2pp | [-14, 26] |
| spatial-swap | C3 64%→C4 66% | +2pp | [-6, 10] |
| **总体 BWT** | 四个旧 panel 平均 | **0.0pp** | **[-6.0, 7.5]** |

总体 BWT 为 0，且所有单项区间均跨过 0，因此本轮结果没有统计证据支持全局 catastrophic forgetting。最值得继续追踪的是 spatial-task 的 -4pp，而不是 goal-swap 或 goal-task。

## 7. Peak-to-Current Forgetting

| Panel | 历史峰值 | C4 | Final Forgetting | 95% CI |
| --- | ---: | ---: | ---: | ---: |
| goal-swap | 26%（C2/C3） | 24% | 2pp | [0, 12] |
| spatial-task | 78%（C3） | 70% | **8pp** | [0, 22] |
| goal-task | 42%（C4） | 42% | 0pp | [0, 14] |
| spatial-swap | 66%（C4） | 66% | 0pp | [0, 12] |
| object-task | 90%（C4） | 90% | 0pp | [0, 0] |
| object-swap | 86%（C4） | 86% | 0pp | [0, 0] |

六个 panel 的描述性平均 Final Forgetting 为 1.7pp；只在四个旧阶段 panel 上平均为 2.5pp。spatial-task 的 8pp 是唯一实质大小值得注意的峰值回落，但当前 CI 仍包含 0，不能宣称已确认退化。

## 8. 全部相邻 checkpoint 的配对净收益

表中 `+/-` 分别表示新增成功/新增失败；Net Gain 是二者之差。

| Panel | 转移 | 成功率变化 | + / - | Net Gain | Δ 的 95% CI |
| --- | --- | ---: | ---: | ---: | ---: |
| goal-swap | C0→C1 | 24%→20% | 1 / 3 | -2 | [-14, 4]pp |
| goal-swap | C1→C2 | 20%→26% | 3 / 0 | +3 | [0, 16]pp |
| goal-swap | C2→C3 | 26%→26% | 1 / 1 | 0 | [-6, 6]pp |
| goal-swap | C3→C4 | 26%→24% | 1 / 2 | -1 | [-12, 6]pp |
| spatial-task | C0→C1 | 56%→74% | 14 / 5 | +9 | [-4, 42]pp |
| spatial-task | C1→C2 | 74%→76% | 6 / 5 | +1 | [-6, 10]pp |
| spatial-task | C2→C3 | 76%→78% | 7 / 6 | +1 | [-10, 14]pp |
| spatial-task | C3→C4 | 78%→70% | 7 / 11 | **-4** | [-20, 6]pp |
| goal-task | C0→C1 | 16%→14% | 0 / 1 | -1 | [-6, 0]pp |
| goal-task | C1→C2 | 14%→40% | 13 / 0 | **+13** | **[6, 50]pp** |
| goal-task | C2→C3 | 40%→36% | 2 / 4 | -2 | [-12, 4]pp |
| goal-task | C3→C4 | 36%→42% | 9 / 6 | +3 | [-14, 30]pp |
| spatial-swap | C0→C1 | 62%→64% | 8 / 7 | +1 | [-16, 16]pp |
| spatial-swap | C1→C2 | 64%→62% | 7 / 8 | -1 | [-20, 18]pp |
| spatial-swap | C2→C3 | 62%→64% | 8 / 7 | +1 | [-10, 14]pp |
| spatial-swap | C3→C4 | 64%→66% | 7 / 6 | +1 | [-6, 10]pp |
| object-task | C0→C1 | 10%→10% | 0 / 0 | 0 | [0, 0]pp |
| object-task | C1→C2 | 10%→10% | 0 / 0 | 0 | [0, 0]pp |
| object-task | C2→C3 | 10%→10% | 0 / 0 | 0 | [0, 0]pp |
| object-task | C3→C4 | 10%→90% | 40 / 0 | **+40** | **[54, 100]pp** |
| object-swap | C0→C1 | 0%→0% | 0 / 0 | 0 | [0, 0]pp |
| object-swap | C1→C2 | 0%→0% | 0 / 0 | 0 | [0, 0]pp |
| object-swap | C2→C3 | 0%→0% | 0 / 0 | 0 | [0, 0]pp |
| object-swap | C3→C4 | 0%→86% | 43 / 0 | **+43** | **[72, 98]pp** |

该表揭示了成功率矩阵看不到的现象：spatial-swap 在各 checkpoint 的均值几乎不变，但每次有 13-15 个 episode 的成功身份发生替换。也就是说，系统总体能力稳定，不代表同一组实例上的能力稳定。

## 9. Recovery 覆盖与条件成功率

每个单元格写作 `触发 recovery 的 episode / recovery 后成功 / 条件成功率`。

| 条件 | goal-swap | spatial-task | goal-task | spatial-swap | object-task | object-swap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| C0 | 10/9/90.0% | 33/28/84.8% | 5/0/0% | 50/31/62.0% | 0/0/- | 0/0/- |
| C1 | 9/6/66.7% | 48/37/77.1% | 5/0/0% | 50/32/64.0% | 0/0/- | 0/0/- |
| C2 | 10/9/90.0% | 46/38/82.6% | 17/12/70.6% | 50/31/62.0% | 0/0/- | 0/0/- |
| C3 | 10/8/80.0% | 47/39/83.0% | 17/11/64.7% | 50/32/64.0% | 0/0/- | 0/0/- |
| C4 | 10/9/90.0% | 48/35/72.9% | 22/15/68.2% | 50/33/66.0% | 44/40/90.9% | 49/43/87.8% |

解释时需要注意：`recovery 后成功` 是执行路径分解，不是严格的因果 rescue 数。某些触发 recovery 的 episode 在 VLA-only 条件下也可能成功；严格因果收益应使用前述配对 baseline/checkpoint 差值。

该诊断仍显示两个清晰事实：

1. spatial-swap 在所有 pack 上都 100% 触发 recovery，最终成功取决于 recovery executor 的条件成功率；
2. object family 在 C0-C3 完全没有 recovery 覆盖，而 C4 同时获得高触发率和高条件成功率，说明 C4 不只是提高执行质量，而是增加了完整的 trigger/grounding/execution 能力链。

## 10. 结论

### 10.1 这轮结果支持什么

- 模块化、冻结的 clean skill pack 能够在扩展新能力的同时保持较强的旧能力稳定性；
- goal-task 与 object family 存在明确的阶段对齐 acquisition；
- C4 object 能力同时迁移到 task 与 swap，支持 family-level acquisition，而非只记住单个 suite；
- spatial-swap 表现出很强的提前迁移，说明某些 skill family 可以在正式学习前由先前经验组合得到；
- episode 级新增失败和 winner/coverage churn 是比 suite 平均值更敏感的退化信号。

### 10.2 这轮结果不支持什么

- 不支持“随着 skill 数从 10 增长到 36，旧能力普遍灾难性下降”；
- 不支持仅根据 recovery 触发或 recovery success 数直接宣称因果增益；
- 不足以证明不存在局部退化：spatial-task 的 8pp peak-to-current 回落和多个 panel 的 episode churn 仍需更细粒度分析。

### 10.3 对后续研究的含义

当前主实验更适合作为 **stability/acquisition 基线**，下一步应优先寻找自然发生的 interference，而不是人为要求主矩阵出现遗忘：

1. 运行 Object Update Microscope（O0-O6），定位错误 trigger、错误 carton hint、撤回和替代学习对应的新增失败；
2. 正式运行 as-run vs clean，对比被 quarantine 的历史 skill 是否导致 catastrophic memorizing；
3. 在 Shift-30/held-out family panel 上测 placement、geometry/yaw 与语言变化，区分 source-suite fitting 与 family generalization；
4. 对 spatial-task C3→C4 丢失的 11 个 episode 做 winner、trigger、grounding 和执行轨迹归因；
5. 增加 persistent agentic chain，测量 recovery 留下的环境状态是否沿 L1/L3/L5/L10 累积退化。

## 11. 可复现信息

- Remote run root：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006`
- 机器可读最终指标：`final_metrics.json`
- 有效 episode：1800
- Job：36/36 完成
- Bootstrap：20,000 次，task-cluster，seed `20261007`
- 生成时间：2026-10-07（Asia/Shanghai）
