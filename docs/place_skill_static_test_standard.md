# Place Skill Static Test Standard

更新日期：2026-09-10

本文定义 `place` recovery hint 的静态测试标准。它面向 harness / CI 使用，用来防止
Codex 在 mining loop 中把 executor 当成万能补丁，写出作用范围过宽、释放条件过松、预算
无限增加，或混入 trigger / grounding / geometry / grasp 职责的 skill。

本文只约束 active skill pack 下的：

```text
skill_packs/<pack>/skills/pair/recovery_hint/place/*.md
```

`place` 不决定是否进入 recovery，也不决定目标语义、目标几何或抓取采样。它只在 recovery
已经抓住目标物体、正在执行 place 相关动作时，提供小范围 executor-side 局部修正。

## 1. 核心契约

`place` skill 只回答一个问题：

> 物体已经被正确抓住后，释放前的转移、对齐、下放动作是否需要一个受限的 executor 补丁？

因此静态测试检查五层契约：

1. **Catalog 契约**：在线 place skill 必须显式出现在 active pack 的 `skills/_index.yaml`。
2. **Schema 契约**：必须是 `kind: recovery_hint`、`scope: place`，不能声明
   `trigger`、`hook` 或 `backend`。
3. **职责边界契约**：已入库 skill 优先只引用 `place_profile`；profile 展开后只能输出
   `hooks.hover/align/release` 和受限 `executor` 参数，不得修改 grounding、geometry 或 grasp。
4. **数值契约**：对齐误差、步长、预算、release tolerance 必须处在安全范围。
5. **阶段契约**：必须说明它在 place 链路中的作用点，例如 held transfer、hover-yaw 后、
   final drop 前或 release check 前。
6. **Adapter 契约**：需要 benchmark-specific 逻辑时，必须由 active pack 的
   `code/place_policies.py` 选择 hook；新增 hook mode 或 executor key 不能静默通过。

## 2. 当前 Online Place Skills

`libero90_legacy` pack 当前有 2 个 online place skill：

| skill | 作用阶段 | 作用 |
| --- | --- | --- |
| `place_task38_held_transfer_keep_z.md` | pick 成功后，转移到 place hover 前 | task38 白碗被抓住后，XY 转移时保持高度，避免中途下降撞到微波炉或桌面几何。 |
| `place_caddy_held_object_xy_align.md` | caddy hover-yaw 后，drop / release 前 | book 放进 caddy 格子时，按 live footprint 对齐 safe opening，并在分段下放中重复修正。 |

这两份 skill 的共同点是：它们都不改变目标，也不改变抓取；它们只在 executor 已经持有目标后，
约束后续 place 动作。

## 3. Catalog 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | active pack `skills/_index.yaml` 中引用的 place skill 文件不存在。 |
| ERROR | active pack `skills/pair/recovery_hint/place/` 下存在未 online 且没有 `status: draft/retired/archived/experimental` 的 `.md` 文件。 |
| ERROR | online place skill 标记为 `status: draft/retired/archived/experimental`。 |
| ERROR | online place skill 的 `id` 与文件名语义冲突。 |
| WARN | 文件正文没有说明 place 阶段和不适用场景。 |

## 4. Schema 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | `kind` 必须是 `recovery_hint`。 |
| ERROR | `scope` 必须是 `place`。 |
| ERROR | 不得声明 `trigger`、`hook`、`backend`。 |
| ERROR | 已入库 online skill 必须有 `recovery_hints.params.place_profile`，且该 profile 存在于 active pack 的 `profiles/place.yaml`。 |
| ERROR | 已入库 online skill 直接内联 `recovery_hints.params.executor`，且没有明确处于 draft / profile-authoring 状态。 |
| ERROR | 不得出现 `recovery_hints.grasp_profile`。 |
| ERROR | 不得出现 `grounding_hints` 或 `geometry_hints`。 |
| ERROR | 不得出现 `placement_surface`、`placement_region`、`support_object`。 |
| WARN | `recovery_point` 没有说明 place 链路中的具体阶段。 |
| WARN | `when_not_to_apply` 缺少明确反例。 |

## 5. Executor Allowlist

place profile 先展开成 `hooks.hover/align/release`，再桥接到 place 相关 executor 参数。
hook 只能输出本节列出的参数；pack-local `code/place_policies.py` 可以决定某个 profile
启用哪几类 hook，但不能绕过 executor allowlist。

静态 gate 应同时检查 profile registry 和 adapter：

| 级别 | 检查项 |
| --- | --- |
| ERROR | `place_profile` 存在于 `profiles/place.yaml`，但 active pack 没有暴露需要的 `place_policy_adapter`。 |
| ERROR | adapter 没有非空 `PROFILE_IDS`。 |
| ERROR | `PROFILE_IDS` 不包含它负责的 profile。 |
| ERROR | adapter 没有任何 `resolve_hover_policy` / `resolve_align_policy` / `resolve_release_policy` 或等价 `resolve_place_*` 函数。 |
| ERROR | profile 或 adapter 输出了 `hover` / `align` / `release` 之外的 hook。 |
| ERROR | hook `mode` 不是 `held_transfer_keep_z`、`held_object_xy_align`、`closed_loop_drop` 或 `executor_options`，且没有被共享 executor primitive 明确支持。 |
| ERROR | hook 输出的 executor key 不在引擎支持列表或 active pack 的 `capabilities.yaml`。 |
| WARN | active pack 使用了引擎支持但未在 pack capability registry 注册的 executor key。 |

引擎支持列表来自
`experiments/robot/libero/tiptop_repro/engine_capabilities.py`；pack capability registry 是更窄的
运行许可。两边都通过，profile 才能认为会真实生效。

### 5.1 Held-transfer Keep-z

| key | 合理范围 | 含义 |
| --- | --- | --- |
| `held_transfer_keep_z` | bool | holding 后向 place 区域转移时保持保护高度。 |
| `held_transfer_z_margin_m` | 0.000 - 0.080 | 当前高度上的额外保护 margin。 |
| `held_transfer_max_descent_m` | 0.000 - 0.030 | XY 转移期间允许下降的最大量。 |
| `held_transfer_max_steps` | 0 - 120 | keep-z 转移预算。 |
| `held_transfer_reached_m` | 0.001 - 0.040 | 到达判定阈值。 |

### 5.2 Held-object XY Align

| key | 合理范围 | 含义 |
| --- | --- | --- |
| `place_held_object_xy_align` | bool | release 前启用 held object XY 对齐。 |
| `place_align_reached_m` | 0.001 - 0.040 | 单次 XY 对齐到达阈值。 |
| `place_align_center_tolerance_m` | 0.001 - 0.040 | footprint center 对齐容差。 |
| `place_footprint_release_tolerance_m` | 0.000 - 0.010 | footprint 边界允许越界容差。 |
| `place_align_step_clip_m` | 0.004 - 0.040 | 单步 XY 修正上限。 |
| `place_align_max_iters` | 0 - 8 | 对齐迭代次数。 |
| `place_align_max_steps_per_iter` | 1 - 30 | 每次对齐动作的最大 env steps。 |
| `place_align_retry_lift_m` | 0.000 - 0.040 | 对齐失败后可选上抬高度。 |
| `place_align_retry_lift_max_steps` | 0 - 30 | retry lift 预算。 |
| `place_drop_closed_loop_align` | bool | 下放时分段闭环对齐。 |
| `place_drop_align_slices` | 1 - 6 | 下放分段数。 |
| `place_drop_max_steps` | 1 - 120 | final drop 总预算。 |

### 5.3 Release / Retreat

| key | 合理范围 | 含义 |
| --- | --- | --- |
| `place_drop_reached_m` | 0.001 - 0.050 | final drop 到达阈值。 |
| `place_drop_align_xy_m` | 0.001 - 0.100 | drop 中触发 XY 再对齐的偏差阈值。 |
| `place_release_xy_m` | 0.001 - 0.080 | 普通 release 的 XY 容差。 |
| `place_release_xy_min_m` | 0.001 - 0.080 | opening release 的最小 XY 容差。 |
| `place_release_margin_m` | 0.000 - 0.050 | release opening 收缩 margin。 |
| `place_release_z_max_m` | 0.000 - 0.200 | release 允许的最大 z 偏差。 |
| `place_open_dwell_steps` | 0 - 30 | 开爪后停留步数。 |
| `place_retreat_m` | 0.000 - 0.120 | release 后竖直 retreat 距离。 |
| `place_retreat_max_steps` | 0 - 60 | release 后 retreat 预算。 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | executor key 不在 allowlist。 |
| ERROR | executor value 类型错误。 |
| ERROR | executor value 超出硬范围。 |
| ERROR | `place_footprint_release_tolerance_m` 大于 0.010。 |
| ERROR | `place_align_max_iters` 或 `place_drop_max_steps` 被设置成绕过失败的超大预算。 |
| WARN | bool 开关为 false，但仍保留相关数值参数。 |
| WARN | keep-z 和 footprint-align 混在同一个 skill 中，且没有同一任务证据。 |

## 6. Scope 检查

place skill 的适用范围必须很窄。

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `applies_to`。 |
| ERROR | `applies_to` 只包含 task language。 |
| ERROR | `target_name_matches` 是 `.*`、`.+` 这类过宽表达。 |
| ERROR | caddy footprint align 缺少 book target、caddy goal、BDDL contain region 锚点。 |
| ERROR | task-specific keep-z 缺少 task-specific target / language 锚点。 |
| WARN | place skill 会命中多个不相关 task family。 |

推荐锚点：

| place 类型 | 最低锚点 |
| --- | --- |
| task38 keep-z | task38 language + `white_bowl` target。 |
| caddy book XY align | caddy compartment language + book target + caddy goal + `*_contain_region`。 |

不要写 generic “所有 held transfer 都 keep z” 或 “所有 place 前都 XY align”。

## 7. 阶段和前置条件检查

place skill 必须说明它只在已经 holding 目标后生效。

| 级别 | 检查项 |
| --- | --- |
| ERROR | skill 试图修复 pick 前的问题。 |
| ERROR | skill 正文没有说明 pick 已经成功。 |
| ERROR | skill 没有说明作用点是 transfer / hover-yaw 后 / drop 前 / release 前。 |
| WARN | 没有说明如果 live object geometry 缺失时如何 fallback。 |
| WARN | 没有说明失败时是否应该 abort，还是交回 VLA。 |

caddy book 这类任务尤其要明确：如果 release geometry 不满足，不能轻易把仍然 holding 的书交回
VLA，否则 VLA 可能把已经接近完成的状态直接破坏。

## 8. Canary 匹配检查

静态 gate 应维护 canary state，离线调用 matcher，检查典型任务是否命中正确 place skill。

| canary | 预期 place |
| --- | --- |
| task38 white bowl right of plate | `place_task38_held_transfer_keep_z` |
| task74/75/76 book in caddy compartment | `place_caddy_held_object_xy_align` |
| mug/cup right of caddy side region | 不命中 book-caddy place skill |
| cream cheese in basket | 不命中 book-caddy place skill |
| ketchup in top drawer | 不命中 book-caddy place skill |
| bowl stack | 不命中任何 place skill |

| 级别 | 检查项 |
| --- | --- |
| ERROR | canary 没有命中该命中的 place skill。 |
| ERROR | unrelated canary 命中了 place skill。 |
| WARN | 多个 place skill 同时命中，且 priority 关系没有说明。 |

## 9. Trace Scan 检查

静态 gate 不重跑仿真，但应能用历史 trace 扫描 place 链路。

最低报告：

| 字段 | 含义 |
| --- | --- |
| `task_id` / `episode_idx` / `query_idx` | 匹配位置。 |
| `target_name` / `goal_name` | recovery 目标。 |
| `matched_place_hints` | 所有匹配的 place skill。 |
| `executor_overrides` | 最终合并后的 executor 参数。 |
| `holding_object` | place 生效时是否持有目标。 |
| `surface_resolved` / `surface_label` | executor 看到的 place surface。 |
| `surface_opening` | release opening。 |
| `held_object_footprint` | live footprint，若有。 |
| `place_held_object_xy_align` | 对齐事件和每次迭代误差。 |
| `place_drop` | 下放事件和是否到达。 |
| `place_release_check` | release guard 原因。 |
| `success` | episode 最终是否成功。 |

这个报告用于回答：

1. place skill 是否真的执行，而不是只匹配？
2. 执行时是否已经 holding 正确目标？
3. 对齐或 keep-z 后 release guard 是否改善？
4. 是否把失败交回 VLA 后造成二次破坏？

## 10. Evidence 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `evidence.tasks`。 |
| ERROR | 缺少 pick 已成功的证据。 |
| ERROR | 缺少 grounding / geometry 已正确的证据。 |
| ERROR | 缺少 place 阶段失败证据，例如 transfer collision、footprint outside、drop not reached 或 release guard。 |
| WARN | 没有列出失败 run / episode。 |
| WARN | 没有标注视频或抽帧路径。 |
| WARN | 没有写明参数来自哪次 A/B 或 forced recovery 对照。 |

## 11. 建议 Harness 产物

当前 `run_skill_admission.py` 对 place 已执行 schema、capability registry 和 offline trigger
scan；专门的 place 类型静态 gate 仍是待补工具。后续可以新增：

```bash
python scripts/recovery/skill_pipeline/check_place_skills.py
```

建议输出：

- `place_static_gate_result.json`
- `place_static_gate_report.md`
- `place_canary_matches.csv`
- `place_trace_scan.csv`

默认只有 ERROR 失败。WARN 写入报告，留给人工确认。
