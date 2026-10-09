# LIBERO-Pro 持续 Skill 学习与退化 Benchmark 规范

日期：2026-10-06

状态：v0.1，后续评测工作的基准规范

## 1. 目标

本 benchmark 研究一个已部署的 agentic robotics 系统在持续积累外部 skill 时，能力如何获得、迁移、干扰、退化和恢复。

本文采用 *When Does Continual Learning Require Learning*（arXiv:2607.07847）的核心定义：持续学习不是只防止遗忘，而是在环境和任务持续变化时提高系统能力。论文的通用阶段协议被改写到本项目：模型权重保持固定，历史 skill pack 是阶段间携带的外部知识状态。

本 benchmark 的主问题是：

1. 学习一个新 LIBERO-Pro suite 后，旧 suite 的能力是否下降？
2. 已有 skill 是否帮助尚未学习的新 suite？
3. 新 skill 的收益是否超过它对旧任务造成的干扰？
4. 退化发生在 trigger、skill 仲裁、grasp、grounding、geometry、planning、execution 还是最终状态保持？
5. 删除无效或有害 skill、替换错误 skill，能否在获得新能力的同时保留旧能力？

这里测量的是 **system-level continual skill learning** 或 **external skill-memory degradation**。在主实验中 Pi0/VLA 权重固定，因此不得把结果表述成模型权重的 catastrophic forgetting。

## 2. 非目标

- 第一版不把 agentic-state 长链作为主轴。打开抽屉后再放物体等任务适合作为后续 long-horizon 扩展，但会混入状态记忆与长时序规划问题。
- 不用不同历史报告里的原始成功率直接拼学习曲线。历史运行的 seeds、runner、engine、语言配置和 recovery budget 不一致。
- 不修改或重新解释冻结 pack；所有兼容性修复发生在只读 replay 副本和 manifest 中。
- 不把“触发了 recovery”等同于 skill 成功。
- 不把未触发等同于 skill 失败；VLA 可能自行完成任务。

## 3. Benchmark 总体结构

Benchmark 分为一个主实验和两个解释性实验。

### 3.1 主实验：Cross-Suite Historical Replay

按真实学习顺序回放五个 skill 状态，并在每个状态上评测全部 suite panel。

```text
C0 goal_swap
  -> C1 spatial_task
  -> C2 goal_task
  -> C3 spatial_swap
  -> C4 object_task / object_swap
```

主实验回答跨 suite 的能力获取、forward transfer、backward transfer 和最终遗忘。

### 3.2 解释实验 A：Object Update Microscope

回放 object pack 内部的细粒度 Git checkpoint：

```text
24 -> 29 -> 30 -> 32 -> 31 -> 32 -> 36 skills
```

它用于解释一次 trigger 扩展、flat-box skill、新增错误 carton skill、撤回、替代学习和 rack 能力扩展分别造成什么变化。

### 3.3 解释实验 B：As-Run vs Clean Memory

比较保留历史污染的 as-run pack 与移除 13 条 quarantined 资产后的 clean derivative：

```text
goal-swap:   as-run 23 vs clean 10
spatial-task: as-run 29 vs clean 16
```

它测量错误或无效经验是否形成“catastrophic memorizing”：本应淘汰的 skill 是否继续抢占、干扰或增加上下文负担。

## 4. 冻结的历史 Checkpoint

### 4.1 主时间轴

| ID | 学习状态 | Pack | 索引资产数 | 性质 |
| --- | --- | --- | ---: | --- |
| C0 | goal-swap 后 | `libero_goal_task_from_goal_swap_v1_asrun_20260913_clean` | 10 | derived-clean，作为进入下一阶段的有效记忆 |
| C1 | spatial-task 后 | `libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914_clean` | 16 | derived-clean，新增 6 条 spatial-task 资产 |
| C2 | goal-task 后 | `libero_goal_task_from_goal_swap_spatial_mining_base_20260914` | 23 | frozen campaign pack |
| C3 | spatial-swap 后 | `libero_spatial_swap_from_goal_task_mining_base_20260916` | 24 | frozen campaign pack |
| C4 | object 两轴后 | `libero_object_task_from_spatial_swap_mining_base_20260918` | 36 | 当前终点 pack |

索引文件是资产数量的事实源。C3 到 C4 的历史说明曾写“25 条”，实际 C3 和 C4 初始索引均为 24 条；正式 replay manifest 必须记录这一更正。

C0/C1 的 `pack.yaml` 当前含有未加引号的冒号，PyYAML 无法直接解析。不得修改冻结目录；benchmark builder 应复制到临时 replay snapshot，仅规范化 manifest 字符串，并同时记录源文件 hash、规范化后 hash 与唯一改动。

### 4.2 Object 细粒度时间轴

| ID | Git commit | 索引资产数 | 更新事件 |
| --- | --- | ---: | --- |
| O0 | `13bf5b1` | 24 | 从 spatial-swap pack copy-forward |
| O1 | `5b93dcc` | 29 | 新增 5 条 object wrong-intent trigger |
| O2 | `e5503a5` | 30 | 新增 shared flat-box grasp hint |
| O3 | `3bfdf0b` | 32 | 新增 q5 trigger 与 tall-carton top-down hint |
| O4 | `fee3177` | 31 | 因 regression 撤回 tall-carton hint |
| O5 | `8e7b0bf` | 32 | 新增 upright-carton body-side profile |
| O6 | `3b6fb6a` | 36 | 新增 cream-cheese rack 能力链 |

`0c398d7` 只把两个候选放入 `drafts/`，未改变运行索引，不算独立学习状态。

## 5. 固定任务集合

### 5.1 Core-60 跨 Suite Panel

正式跨 suite 主面板包含以下六个 suite 的全部 10 个任务，共 60 个任务：

| Panel | Suite | 任务数 | 角色 |
| --- | --- | ---: | --- |
| P0 | `libero_goal_swap` | 10 | 最早学习域与长期 retention probe |
| P1 | `libero_spatial_task` | 10 | 第一轮跨域迁移 |
| P2 | `libero_goal_task` | 10 | goal 轴变化 |
| P3 | `libero_spatial_swap` | 10 | spatial 轴变化 |
| P4a | `libero_object_task` | 10 | object-task 域 |
| P4b | `libero_object_swap` | 10 | object-swap 域 |

P4a/P4b 在 stage-level 指标中可合并为 object stage，在诊断表中必须分别报告。

### 5.2 Shift-30 单轴泛化 Panel

保留 `pro_object_batch_20261004_task` 的 30 个任务作为受控变化面板：

- 10 个 goal 变体；
- 10 个 placement 变体；
- 10 个 geometry/yaw 变体。

该 panel 用来判断历史 pack 获得的是可迁移 skill，还是只记住源 suite 的表面分布。现有 1500-episode 结果属于开发和校准证据，不作为隐藏测试结果。

### 5.3 正式 Held-Out Panel

正式结论还需要一份未参与历史 skill 编写、阈值调整或当前 benchmark 分析的新 panel。构造规则：

1. 从与 Core-60 相同的源场景复制任务；
2. 每条任务只改变 goal、placement 或 geometry 中一个轴；
3. placement/geometry 改动后重新采样 init states；
4. 过滤 reset 后已经成功或无法加载的状态；
5. task、init 与 seed manifest 在正式评测前冻结；
6. hidden panel 不向 skill writer 暴露逐 episode trace。

若暂时没有正式 held-out panel，所有结果必须标记为 retrospective replay 或 pilot，不得称为最终泛化结论。

## 6. 统一回放协议

### 6.1 主协议：Skill-Only Replay

所有 checkpoint 使用统一的：

- Pi0/OpenPI checkpoint；
- 当前固定 runner commit；
- 当前固定 cuTAMP/cuRobo engine；
- benchmark BDDL、init 和 seed；
- 最大环境步数；
- `max_recovery_calls` 与 `max_recovery_steps`；
- 语言来源；
- 图像、动作和 verifier 配置。

唯一变化是 replay snapshot 中的 skill pack、profiles、pack-local adapters 和 capability registry。

历史 pack 全部以 `fail_only` 为主，因此主协议统一使用 mining 加载语义。不得把它们批量伪装成 `pair/online`，不得混用 `--enable_skills` 与 `--enable_mining_skills`，不得设置 `force_recovery_query`。

### 6.2 必需 Baseline

| Baseline | 含义 |
| --- | --- |
| VLA-only | 不加载 skill、不调用 recovery；判断任务原本是否可完成 |
| C0-C4 | 主历史轨迹 |
| Final pack C4 | 每个 panel 的统一终点参照 |
| As-run/Clean pair | 测 memory pruning 的净效果 |

可选 ablation：只加载当前 suite 新增的 skill，作为“无历史累积”对照。它不属于主轨迹，但可区分历史正迁移与历史干扰。

### 6.3 Episode 配对

不同 checkpoint 必须使用完全相同的：

- task；
- BDDL；
- init-state 下标；
- episode seed；
- policy seed；
- 最大步数与 recovery budget。

结果分析以配对 episode 为基本单位，不只比较两个独立成功率。

### 6.4 可选协议：Historical End-to-End Replay

可在少量代表 checkpoint 上使用当时的 runner/engine 重放，回答“当时整个部署系统表现如何”。该结果同时包含工程演进，必须与 skill-only replay 分表报告。

## 7. 结果矩阵与主指标

令 `R[i,j]` 为 checkpoint `Ci` 在 panel `Pj` 上的平均 task success。

### 7.1 能力获取

```text
Acquisition(j) = R[j,j] - R[j-1,j]
```

表示学习当前 suite 后立即获得了多少能力。

### 7.2 Backward Transfer

```text
BWT = mean_j<K (R[K,j] - R[j,j])
```

负值表示最终状态损害了过去 suite；正值表示后续学习反而改善旧能力。

### 7.3 Forward Transfer

```text
FWT(j) = R[j-1,j] - R[VLA-only,j]
```

表示在正式学习 suite `j` 之前，已有 skill 是否对它有帮助。

### 7.4 Peak-to-Current Forgetting

```text
Forgetting(i,j) = max_t<=i R[t,j] - R[i,j]
FinalForgetting(j) = max_i R[i,j] - R[K,j]
```

该指标能发现“先学会、后来退化”，而不是只看相邻阶段。

### 7.5 净收益

在配对 episode 上统计：

```text
NetGain(A -> B) = 新增成功 episode - 新增失败 episode
```

其中“新增失败”指旧 checkpoint 成功而新 checkpoint 失败。每次 skill 更新都必须报告净收益，不能只报告新增覆盖。

### 7.6 汇总规则

- 每个 suite 先按 task 求成功率，再对 task 做 macro average，避免容易任务支配结果。
- 同时报告 episode-level micro average，供计算总资源和总体成功数。
- 对 checkpoint 差值报告 paired bootstrap 95% 置信区间；bootstrap 以 task 为 cluster。
- 若区间跨过 0，不宣称显著提升或退化。

## 8. 机器人侧诊断指标

每个 `checkpoint × panel` 除最终成功率外，还必须输出以下分解。

### 8.1 Trigger 与仲裁

- 对 VLA-only 失败 episode 的触发召回率；
- 对 VLA-only 成功 episode 的误触率；
- 首次触发 query；
- 实际 winner skill；
- would-fire 但被更高 priority skill 覆盖的集合；
- checkpoint 间 winner replacement rate；
- 未触发但最终成功的 episode 数。

### 8.2 Recovery 条件成功率

```text
ConditionalRecoverySuccess
  = recovery 后任务成功 episode / 发生 recovery 的 episode
```

必须按 trigger skill、task、suite 分组。触发率与触发后成功率不得合成一个指标。

### 8.3 分层失败原因

至少区分：

1. trigger 未命中或过晚；
2. grounding/goal binding 错误；
3. geometry/profile 不适用；
4. grasp 候选不可行；
5. close/lift 后未持物；
6. motion planning 不可行；
7. trajectory execution/tracking 失败；
8. place/release 未进入目标区域；
9. recovery 成功后被后续 VLA 动作破坏；
10. verifier 或预算终止。

### 8.4 干扰

重点报告：

- VLA-only 成功、旧 checkpoint 成功、新 checkpoint 失败；
- 旧 checkpoint winner 成功，但新 skill 抢占后失败；
- 新 hint 被合并到旧 trigger 后导致失败；
- 新 profile 修改了共享物体族，但无关成员退化。

## 9. 运行分阶段与计算预算

### Phase 0：Snapshot Audit

对 C0-C4 和 O0-O6 生成只读 replay manifest：

- 源 commit/directory；
- parent checkpoint；
- pack/index/profile/adapter hashes；
- indexed skill IDs；
- 新增、删除、修改的资产；
- manifest 规范化记录；
- 当前 loader 与 schema 兼容性结果。

审计未通过的 snapshot 不得进入 GPU 正式运行。

### Phase 1：离线 Trace Replay

在历史 query traces 上扫描所有 checkpoint，比较 would-fire、winner、误触和 trigger 覆盖。该阶段用于发现高风险单元格，不能替代真实 rollout。

### Phase 2：Core-60 Pilot

建议配置：

```text
5 checkpoints × 60 tasks × 5 episodes = 1500 episodes
```

另跑一份配对的 VLA-only baseline。Pilot 用于生成初始矩阵和筛选需要扩大样本的单元格。

### Phase 3：Shift-30 与重点复测

在全部 checkpoint 上用较小 episode 数运行 Shift-30；对以下情况扩大到 30-50 episodes：

- 明显负 BWT；
- 明显正/负 FWT；
- as-run 与 clean 出现差异；
- winner skill 发生变化；
- task success 与 conditional recovery success 结论不一致；
- object O3/O4/O5 出现 regression、恢复或替代学习。

### Phase 4：Formal Held-Out Evaluation

冻结新 held-out manifest 后一次性运行，不再依据结果调 skill、阈值或任务。所有正式表格从该 manifest 产生。

## 10. 必需产物

每次 benchmark release 至少输出：

```text
benchmark/<version>/
  benchmark_manifest.json
  checkpoints.jsonl
  panels/
    core60.jsonl
    shift30.jsonl
    heldout.jsonl
  resolved_run_spec.json
  episode_pairs.jsonl
  matrices/
    task_success.csv
    trigger_recall.csv
    trigger_interference.csv
    conditional_recovery_success.csv
    forgetting.csv
  diagnostics/
    winner_transitions.jsonl
    failure_layers.jsonl
  report.md
```

`report.md` 必须包含：

1. checkpoint × suite 的完整 success matrix；
2. BWT、FWT、Final Forgetting；
3. trigger precision/recall 与 conditional recovery success；
4. 每次更新的新增成功、回退和 NetGain；
5. 至少一个正迁移和一个负迁移的 episode-level case study；
6. as-run/clean pruning 结果；
7. object 错误 skill 加入、撤回、替代的局部曲线；
8. 所有运行配置、commit 和资产 hash。

## 11. Benchmark 可以支持的结论

完成上述评测后，可以回答：

- skill 数量增加是否带来单调能力增长；
- 哪些 suite 之间存在正迁移或负迁移；
- 旧能力的峰值、退化点和最终遗忘量；
- 退化主要来自 trigger 仲裁还是 recovery 后端；
- shared profile 带来复用还是跨任务污染；
- 删除错误记忆是否优于无限累积；
- admission、global replay 和 canary 应覆盖哪些任务；
- 一个新 skill 的净收益是否为正。

不能仅凭本 benchmark 宣称：

- Pi0 权重发生 catastrophic forgetting；
- 某种结果可泛化到真实机器人；
- 在开发 panel 上表现最好就代表对未知任务最好；
- skill 触发次数越多，系统学习得越好。

## 12. 第一版冻结决策

v0.1 固定以下决策：

1. 主时间轴使用 C0-C4 的跨 suite clean/frozen lineage；
2. 主任务集合使用 Core-60；
3. Shift-30 是受控泛化 panel；
4. 正式论文结论必须另有 held-out panel；
5. 主协议是统一当前 runner/engine 的 skill-only replay；
6. VLA-only、as-run/clean 是必需对照；
7. object O0-O6 作为机制分析，不取代跨 suite 主矩阵；
8. agentic-state 长链推迟到后续版本；
9. 冻结 pack 不做原地修复，所有兼容性处理写入 replay manifest；
10. 最终成功、trigger 与 recovery 条件成功率必须分开报告。

后续若修改 checkpoint、panel、seed、budget、指标定义或加载语义，必须提升 benchmark 版本并保留旧 manifest，禁止覆盖已经发布的结果。

## 参考

- Anne Harrington et al. *When Does Continual Learning Require Learning*. arXiv:2607.07847, 2026.
- `docs/agentic_skill_recovery_pipeline.md`
- `docs/skill_pipeline_mining_loop.md`
- `docs/libero_pro_build_benchmark_2026-10-03.md`
- `docs/skill_pack_task_variant_methods.md`
- `docs/libero_pro_object_batch_20261004_eval.md`
- `docs/libero_object_axis_50seed_validation_2026-09-20.md`
