# Repair Skill Static Test Standard

更新日期：2026-09-09

本文定义 `repair` skill 的静态测试标准。它面向 harness / CI 使用，用来防止
Codex 在 mining loop 中写出触发过宽、证据不足、依赖未登记诊断信号，或破坏既有
skill 优先级关系的 repair。

本文只约束 `kind: repair`。`grasp`、`grounding`、`geometry`、`place`
属于 `recovery_hint`，应由各自类别的标准约束。

## 1. 核心原则

`repair` 只回答一个问题：

> 当前 VLA rollout 是否已经进入可恢复失败模式，是否应该切到 recovery？

因此静态测试要检查三层契约：

1. **声明契约**：skill 文件能被 schema 解析，字段位置正确。
2. **谓词契约**：trigger 使用的谓词来自白名单，且组合成可靠证据。
3. **诊断生产契约**：谓词依赖的 qstate 字段由 runner / runtime 正确生产、记录，
   并能用历史 trace 离线回放。

只检查 YAML 格式是不够的。repair 的风险主要来自 runner 里临时添加的诊断字段：
字段缺失、语义漂移、没有落盘、或被新 skill 当成过强证据使用，都会让在线触发变得不可信。

## 2. 基础 Schema 检查

每个 active pack 下的 `skills/pair/repair/*.md` 和准备晋升的 `fail_only` repair 草稿必须通过以下检查。

| 级别 | 检查项 |
| --- | --- |
| ERROR | `kind` 必须是 `repair`。 |
| ERROR | online repair 必须位于 active pack 的 `skills/pair/repair/`，并由该 pack `skills/_index.yaml` 的 `online:` 显式列出。 |
| ERROR | `hook` 默认必须是 `after_pi0_query`。使用其他 hook 必须在正文说明原因。 |
| ERROR | `backend` 必须是已注册 backend。当前主线是 `cutamp_recover`。 |
| ERROR | 必须有非空 `applies_to` 和非空 `trigger`。 |
| ERROR | trigger 禁止硬编码 query index、seed、绝对 xyz、contacts 或单条 episode 特有坐标。 |
| WARN | `priority` 必须处在已知 repair 区间内，并说明为什么高于或低于相邻 repair。 |
| WARN | `evidence` 应列出来源 run / task / episode；没有验证证据的草稿不得进入 online。 |

## 3. Visual / Timing Evidence 检查

repair 的目标是找到正确切入时机。准备 ingest 或晋升 online 的 repair 必须提供视觉定位和
强制触发实验记录。

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `Visual Diagnosis` evidence 时，不允许自动晋升 online。 |
| ERROR | 缺少失败 episode 的视频或抽帧路径时，不允许自动晋升 online。 |
| ERROR | 未标注 `last_safe_query`、`first_visible_error_query`、`too_late_query` 中至少两项时，不允许自动晋升 online。 |
| ERROR | 缺少 `Force Recovery Ablation` 记录时，不允许自动晋升 online。 |
| WARN | 只看单条失败 episode、没有同 task 多失败对照。 |
| WARN | 有成功 episode 但没有做成功/失败分叉对照。 |
| WARN | 强制触发实验没有覆盖错误发生前后。 |

强制 query 只能用于诊断和 ablation，最终 trigger 不得包含 query index。

## 4. Predicate Registry 检查

每个 trigger / applies_to 谓词都必须在 predicate registry 中登记。registry 至少应包含：

| 字段 | 含义 |
| --- | --- |
| `name` | 谓词名，例如 `wrong_progress_target_static`。 |
| `scope` | `trigger` 或 `applies_to`。 |
| `state_fields` | 谓词依赖的 qstate 字段。 |
| `producer` | 字段由 runner / runtime 中哪段逻辑生产。 |
| `value_type` | bool / float / int / enum / regex / object。 |
| `missing_behavior` | 缺字段时如何处理。repair trigger 中一般必须是 false。 |
| `trace_fields` | query trace 中必须落盘的字段。 |
| `allowed_families` | 可用于哪些 repair family。 |
| `required_with` | 使用该谓词时必须搭配的其它谓词。 |
| `threshold_range` | 阈值合理范围。 |

静态测试要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | skill 引用的每个谓词必须在 registry 中存在。 |
| ERROR | registry 中声明的 `state_fields` 必须能在 runner/runtime 的 qstate 生产链路中找到。 |
| ERROR | 派生诊断字段必须落入 `query_trace.jsonl` 或可由 trace 确定性重算。 |
| ERROR | 新增谓词必须有 matcher 单元测试，覆盖 true / false / missing 三类状态。 |
| WARN | 阈值超出 registry 的 `threshold_range`。 |
| WARN | 同一个谓词的语义被多个 producer 重复生产。 |

当前 repair 中常见的派生诊断谓词包括：

- `holding_status_is`
- `nearest_pickable_is_target`
- `intent_object_is_target`
- `target_future_min_xy_distance_lt` / `target_future_min_xy_distance_gt`
- `wrong_object_intent_persist_queries_gte`
- `wrong_object_intent_margin_gt`
- `wrong_progress_target_static`
- `wrong_progress_object_total_motion_gt`
- `vla_wrong_object_progress_status_is`
- `vla_articulated_blocker_status_is`
- `ee_stalled`

这些谓词是 repair 能否可靠触发的关键，不得绕过 registry 直接在 skill 中使用。

## 5. Repair Family Contract

每个 repair 必须归入一个 trigger family。不同 family 有不同的最低证据要求。

### 5.1 Target Approach

用途：VLA 正在接近正确目标，但继续执行可能导致抓坏、抓浅或错过合适入口。

代表：`bowl_pick_preclose_near_target`、`book_pick_approach_recovery`、
`mug_pick_approach_or_stall_recovery`。

最低要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | `aperture_gt` 必须存在。 |
| ERROR | `holding_status_is: handempty_or_unconfirmed` 必须存在。 |
| ERROR | 必须有 `target_ee_distance_lt`。 |
| ERROR | 必须至少有一个目标一致性证据：`nearest_pickable_is_target: true`、`intent_object_is_target: true`、`target_future_min_xy_distance_lt`。 |
| ERROR | `applies_to` 必须绑定具体目标类型，不能只靠 task language。 |
| WARN | `target_ee_distance_lt` 过大时需要说明为什么不会过早触发。 |

反模式：

- 只因为目标距离小就触发。
- 没有 `holding_status`，导致已抓住物体后再次进入 pick recovery。

### 5.2 Target Stall / Empty Grasp

用途：夹爪已经到目标附近，但 EE 停滞、空抓、或合爪后没有确认持有。

代表：`bowl_pick_empty_close_stall`、`flat_box_pick_open_hand_stall_recovery`。

最低要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | 必须有目标邻近证据：`target_ee_distance_lt` 或等价注册谓词。 |
| ERROR | 必须有 `ee_stalled`，且 window 不小于 3。 |
| ERROR | 必须有 `holding_status_is: handempty_or_unconfirmed`。 |
| ERROR | 必须有目标一致性证据，避免把 wrong-object stall 当成目标 stall。 |
| WARN | `aperture_lt` 类空抓 repair 应说明 close 后为什么仍判断为未持有。 |

反模式：

- 只看 `ee_stalled`，不看目标是谁。
- close 后没有 holding 判定，就把所有停顿都当成空抓。

### 5.3 Wrong Object Intent

用途：VLA 尚未真正完成错误搬运，但其动作轨迹明显朝非目标物体发展。

代表：`vla_wrong_object_intent_conservative`、
`flat_box_wrong_object_intent_stall_recovery`。

最低要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | 必须有 `intent_object_is_target: false`。 |
| ERROR | 必须有持续性证据，例如 `wrong_object_intent_persist_queries_gte >= 3`。 |
| ERROR | 必须有 margin 证据，例如 `wrong_object_intent_margin_gt`。 |
| ERROR | 必须有目标未被接近或未被移动的证据，例如 `target_future_min_xy_distance_gt` 或 `wrong_progress_target_static`。 |
| ERROR | 必须有非目标邻近证据，例如 `nearest_pickable_is_target: false` 与 `nearest_pickable_distance_lt`。 |
| WARN | 目标匹配过宽时必须用历史 trace 扫描误触发。 |

反模式：

- 只看夹爪靠近非目标物体。
- 只看 gripper close。
- 只用一帧 intent 判断抓错对象。

### 5.4 Wrong Object Progress

用途：VLA 已经明显移动了错误对象，甚至把错误对象搬到 goal 附近。

代表：`vla_wrong_object_progress_recovery`。

最低要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | 必须有 `wrong_progress_target_static: true`。 |
| ERROR | 必须有错误对象运动量阈值，例如 `wrong_progress_object_total_motion_gt`。 |
| ERROR | 必须有 progress 状态枚举，例如 `vla_wrong_object_progress_status_is`。 |
| ERROR | 若 `applies_to` 使用 `target_name_matches: .+`，必须同时有 goal / BDDL surface 锚点。 |
| WARN | 该 family 通常优先级较高，必须做 priority overlap 扫描。 |

反模式：

- 只看某个非目标移动了一点。
- 没确认目标静止，就判断搬错东西。

### 5.5 Articulated Blocker

用途：机械臂或夹爪被打开抽屉、门等 articulated object 阻挡，VLA 无法进入正常 pick。

代表：`bowl_pick_blocked_by_open_drawer`。

最低要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | 必须使用已注册 blocker 状态，例如 `vla_articulated_blocker_status_is`。 |
| ERROR | 必须有持续性或状态机证据，不允许单帧碰撞/接近就触发。 |
| ERROR | 必须有 `holding_status_is: handempty_or_unconfirmed`。 |
| ERROR | 必须确认目标尚未进入正常 grasp 状态，例如 `target_ee_distance_gt` 或等价谓词。 |
| WARN | 若 repair 带 entry lift / retreat hint，必须检查 executor 是否消费这些参数。 |

反模式：

- 默认看到抽屉开着就触发。LIBERO 中一些柜子初始就是打开的。
- recovery 后又从同一侧抓取，继续撞到 blocker。

## 6. Applies-to 边界检查

`applies_to` 决定 skill 适用范围。静态测试要求：

| 级别 | 检查项 |
| --- | --- |
| ERROR | repair 不得只有 `task_language_matches`，必须至少绑定目标、goal、surface 或 BDDL surface 中的一类。 |
| ERROR | 目标类别 skill 必须有 `target_name_matches`。 |
| ERROR | 使用 `target_name_matches: .+` 的 repair 必须属于强诊断 family，例如 wrong-object progress，并额外绑定 goal / BDDL surface。 |
| WARN | `target_name_excludes` 过长时提示是否应该拆成更明确的目标类别。 |
| WARN | 同一个目标类别上多个 repair 覆盖重叠时，需要 priority overlap 报告。 |

## 7. Priority / Overlap 检查

当前 matcher 对 repair 是“最高 priority 第一个命中”。因此新 repair 可能抢占旧 repair。

静态测试必须对历史 trace 和合成 qstate 做 overlap scan：

| 级别 | 检查项 |
| --- | --- |
| ERROR | 新 repair 在非当前 task 的成功 episode 中成为实际 winner。 |
| ERROR | 新 repair 抢占更具体且已验证稳定的 repair。 |
| ERROR | 高 priority broad repair 没有强诊断证据。 |
| WARN | 新 repair 与已有 repair 在同一 task / query 上同时 would_fire，但同 init validation 没有回退时允许继续观察。 |
| INFO | 新 repair 在非当前 task would_fire 但被更高优先级 skill shadow；这不算 fatal。 |
| INFO | 记录每个 repair 的 would_fire 次数、实际 winner 次数、被谁抢占。 |

报告至少包含：

- `skill_id`
- `priority`
- `task_id`
- `episode_idx`
- `query_idx`
- `would_fire`
- `winner_skill_id`
- `shadowed_by`
- `new_trigger_on_success`

offline scan 的当前口径是单一全局 scan set，不再分“局部 scan”和“全局 scan”两层。scan set
由当前 task run、显式 `--scan-root` canary 和 rolling corpus 最近若干 run 合并而成。
报告按 `current_task_effectiveness` 与 `global_safety` 两块解释结果。

## 8. Repair Profile / Executor 边界

repair 可以引用已注册 `repair_profile`，用于安全进入 recovery，例如先上抬、
保持夹爪、避开当前 blocker。runtime 会把 `repair_profile` 展开成
`recovery_hints.params.executor`。repair skill 本身不应承担 grasp / grounding /
geometry / place 的职责，也不应直接内联 executor 参数。

| 级别 | 检查项 |
| --- | --- |
| ERROR | repair 中出现 `grasp_profile`、目标绑定、region geometry 或 place 对齐逻辑。此类内容应拆到 `recovery_hint`。 |
| ERROR | repair 中直接出现 `params.executor`。已入库 repair 必须改为 `params.repair_profile`。 |
| ERROR | `params.repair_profile` 必须存在于当前 skill pack 的 `profiles/repair.yaml`，并在 capability registry 的 `repair_profiles` 中注册。 |
| ERROR | repair profile 展开后的 executor key 必须在 executor config allowlist 中，并有测试证明会被消费。 |
| WARN | entry lift / retreat 的距离超出安全范围。 |
| WARN | repair 同时修改过多 executor 行为，建议拆分。 |

允许的 repair profile 例子：

- `entry_lift_open_hand_small_v1`
- `entry_lift_open_hand_mug_v1`
- `entry_lift_escape_current_away_blocker_v1`

## 9. Trace Replay 检查

所有准备进入 online 的 repair 必须在历史 trace 上离线回放 trigger。

最低报告：

| 字段 | 含义 |
| --- | --- |
| `positive_hits` | 目标失败 case 上触发次数。 |
| `success_hits` | 历史成功 case 上触发次数。 |
| `first_hit_query` | 每条 episode 首次触发 query。 |
| `hit_family` | trigger family。 |
| `matched_hints` | 触发 recovery 后会合并哪些 recovery_hint。 |
| `winner_skill_id` | 按当前 priority 实际会触发哪个 repair。 |
| `diagnostic_missing_fields` | 回放时缺失的 qstate 字段。 |

准入建议：

- 新 repair 在目标失败 case 上应能命中预期失败阶段。
- 当前 task 首次触发默认不得早于 `query_idx = 5`，除非有明确非 approach failure signal。
- 非当前 task 成功 episode 中，新 repair 不应成为实际 winner。
- 如果 trace 缺少该 repair 依赖的诊断字段，应先补 runner / trace，不应直接上线。

## 10. Gate 结果分级

静态测试输出应分为：

| 级别 | 处理方式 |
| --- | --- |
| ERROR | 不允许 ingest / 不允许进入 `online:`。 |
| WARN | 可以保留草稿，但需要人工确认；默认不得自动晋升。 |
| INFO | 只写入报告。 |

建议输出文件：

- `repair_static_gate_result.json`
- `repair_static_gate_report.md`
- `repair_overlap_report.csv`
- `predicate_producer_report.csv`

这四份产物应成为 mining loop 中 Codex 写完 repair 后的第一道门闩。
