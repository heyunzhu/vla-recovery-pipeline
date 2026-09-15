# Repair Skill Authoring Guidelines

更新日期：2026-09-12

本文给后续 Codex / agent 编写 `repair` skill 使用。它的核心要求是：

> 先定位问题，再验证 recovery 时机，最后才把判断写成 trigger。

skills-off baseline 中没有
recovery 是实验设置，不是“只缺触发”的证据；同时检查接管后的 grasp、绑定、几何与执行能力。
单次介入可以在有效 probe 之后追加所需 hint/profile，无需先提交仅能触发的版本。

`repair` skill 最重要的能力不是“拼出一组 YAML 谓词”，而是判断 VLA 在哪里开始偏离、
什么时候切入 recovery 才有意义，以及这个判断能否由 runner 在线诊断信号稳定表达。

## 1. 当前运行位置

`repair` skill 必须写在 active skill pack 下面：

```text
skill_packs/<pack>/skills/pair/repair/
```

是否 online 只看该 pack 的 `skills/_index.yaml`。目录里有 `.md` 文件但没有进 `online:`
列表时，它不会被 `--enable_skills` 加载。`fail_only` 草稿只在 mining validation 中通过
`--enable_mining_skills` 加载。

如果 repair 需要 recovery-entry 动作参数，应引用当前 pack 的 `profiles/repair.yaml`：

```yaml
recovery_hints:
  params:
    repair_profile: <registered_repair_profile>
```

runtime 会把 `repair_profile` 展开成受限 `params.executor`，再进入 capability audit。已入库
repair 不应直接内联 executor 参数。

## 2. Repair 的职责边界

`repair` 只决定：

> 当前 VLA rollout 是否应该离开 VLA，切到 recovery？

它不负责：

- 设计抓取点；
- 修改目标绑定；
- 添加或修正几何区域；
- 调整 place 释放前的对齐；
- 写 cuTAMP goal atom；
- 写单条 episode 的 query index、seed 或绝对坐标。

如果问题本质是抓取点、目标绑定、几何区域或释放前对齐，应拆到：

- `<pack>/skills/pair/recovery_hint/grasp/`
- `<pack>/skills/pair/recovery_hint/grounding/`
- `<pack>/skills/pair/recovery_hint/geometry/`
- `<pack>/skills/pair/recovery_hint/place/`

repair 可以引用少量已注册 `repair_profile`，例如刚进入 recovery 时先上抬、保持夹爪、
远离 blocker。profile 会在 runtime 中展开成 executor entry 参数。repair Markdown
不得直接内联 `params.executor`，也不能把这些 profile 变成完整抓取或放置策略。

## 3. 输入材料

编写 repair 前，agent 必须读取或检查：

| 材料 | 用途 |
| --- | --- |
| 当前失败 episode 的视频或抽帧 | 用视觉直觉定位问题第一次发生的位置。 |
| 同 task 多个失败 episode | 判断是否是共性失败，而不是单 seed 偶然。 |
| 同 task 成功 episode，若存在 | 对照成功和失败在哪里分叉。 |
| `query_trace.jsonl` | 查看每个 query 的 qstate、skill diagnostics、目标/夹爪/对象运动。 |
| `recovery_trace.jsonl` | 若已有 recovery，查看是否触发太晚或执行失败。 |
| `skill_match_diagnostics` | 解释现有 repair 为什么没触发、触发太晚或被别的 skill 抢占。 |
| 当前 pack 的 `skills/pair/repair/` 和 `_index.yaml` | 避免重复写 skill，检查 priority、online 状态和 overlap。 |
| `docs/repair_skill_static_test_standard.md` | 确认静态测试要求。 |
| `docs/diagnostic_signal_pipeline.md` | 当现有 qstate 不够时，按 draft / shadow 流程新增诊断信号。 |

禁止只看 JSON 就写 repair。视频或抽帧是第一证据，因为很多失败的本质只能从视觉中看出：
夹爪推歪目标、撞到环境、绕错侧、拿错对象、目标已经被破坏、或 place 阶段本来就不可救。

## 4. 标准编写流程

每个 repair 必须按下面顺序推进。

### 4.1 视觉定位

先看视频或抽帧，不急着写 trigger。

至少回答：

- 机器人具体做错了什么？
- 错误第一次出现在哪个阶段：approach、close、lift、transfer、place，还是 VLA 选择了错误目标？
- 错误发生前是否存在一个清楚的“还可以救”的时间窗口？
- 如果提前切入 recovery，是否有希望避免破坏环境？
- 同一 task 的多个失败是否呈现同一种分叉？
- 成功 episode 和失败 episode 最早在哪个 query 开始不同？

建议对同一 task 同时排布：

- 2-5 条失败视频；
- 若存在，1-2 条成功视频；
- 每条视频按 query 抽关键帧，至少覆盖 approach、close、lift、place 或结束帧。

视觉诊断输出应包含：

| 字段 | 含义 |
| --- | --- |
| `visual_failure_summary` | 用自然语言描述失败现象。 |
| `common_pattern` | 多个失败之间的共同点。 |
| `success_failure_split` | 成功和失败最早分叉的位置。 |
| `first_visible_error_query` | 第一次看出错误的 query。 |
| `last_safe_query` | 仍未破坏环境、适合接管的最后 query。 |
| `too_late_query` | 此后即使触发 recovery 也大概率无效。 |

### 4.2 判断是否真是 repair 问题

repair 只解决“何时切入”的问题。视觉定位后必须先分类：

| 现象 | 处理 |
| --- | --- |
| 早切入可以避免失败 | 继续写 repair。 |
| 抓取候选明显错误 | 写 grasp hint，不应只改 repair。 |
| 目标区域绑定错误 | 写 grounding hint，不应只改 repair。 |
| planner 几何表示错误 | 写 geometry hint，不应只改 repair。 |
| holding 后释放前需要额外对齐 | 写 place hint，不应只改 repair。 |
| 已测试的强制 query 都没有可行解 | 查对应 problem、粒子约束与运动规划，在本次介入内修所需能力；有限样本不能证明所有 query 都无解。 |

不要把所有失败都归为“触发太晚”。如果 recovery backend 本身无法完成任务，
repair trigger 写得再早也不会变好。

### 4.3 强制触发实验

在正式提交 trigger 前，使用固定 probe 取得真正进入待研究环节的证据，或复用本 run 配置对应
的有效 recovery 记录。probe 可失败，但不能把初始化报错当成已完成切入时机验证。

```powershell
python remote.py probe-recovery --seed 51 --query 10 --dry-run
python remote.py probe-recovery --seed 51 --query 10
```

上述 seed/query 是用法示例，按当前记录选取。工具继承 lane 的评测解释器，勿用 --planning
启动完整 Pi0 rollout。出错时先看 plan/preflight/eval.log，核对解释器再重试，不直接安装依赖。

推荐选点：

```text
last_safe_query - 1
last_safe_query
first_visible_error_query
too_late_query
```

如果 query 间隔较粗，可以用 3-5 个候选 query 覆盖错误发生前后。

实验要回答：

- 哪个 query 强制触发能成功？
- 哪个 query 触发已经太晚？
- recovery 失败时是没有可行解、执行失败，还是触发后目标状态已被破坏？
- 成功的强制触发是否依赖同一条 seed 的偶然位置？

强制 query 只用于诊断，不能写进最终 skill。最终 repair 必须用在线谓词近似这个触发窗口。

### 4.4 对照现有 repair

检查当前 online repair 在这些 query 上发生了什么：

- 有没有 repair would_fire？
- 如果没有，哪些 predicate failed？
- 如果有，为什么没有成为 winner？
- 如果 winner 已经触发，为什么仍失败：太晚、hint 不对、backend 无解、executor 中断？
- 新 repair 是否会抢占已有稳定 repair？

这一阶段必须使用 `skill_match_diagnostics`，不要只凭肉眼判断“没触发”。

### 4.5 把视觉直觉转成 runner 诊断信号

确认早切入有价值后，才开始找在线可计算信号。

例子：

| 视觉直觉 | 可能需要的诊断信号 |
| --- | --- |
| 夹爪正朝目标接近，但再晚会推歪目标 | `target_future_min_xy_distance_lt`、`nearest_pickable_is_target`、`target_ee_distance_lt` |
| 夹爪反复停在目标附近 | `ee_stalled`、`target_ee_distance_lt`、`holding_status_is` |
| VLA 正朝错误物体移动 | `intent_object_is_target`、`wrong_object_intent_persist_queries_gte`、`wrong_object_intent_margin_gt` |
| 错误物体已经被搬走，目标还没动 | `wrong_progress_target_static`、`wrong_progress_object_total_motion_gt`、`vla_wrong_object_progress_status_is` |
| 夹爪被打开抽屉卡住 | `vla_articulated_blocker_status_is` 加持续性状态 |

如果现有 qstate 没有足够信号，不允许硬凑 trigger。应在 `findings.md` 写：

```markdown
## Proposed runner diagnostics

- Need field: ...
- Visual reason: ...
- Online source: ...
- Expected true examples: ...
- Expected false examples: ...
```

新增 runner 诊断信号时，必须同时补：

1. qstate producer；
2. `query_trace.jsonl` 落盘字段；
3. `matcher.py` 谓词；
4. predicate registry 记录；
5. true / false / missing 单元测试；
6. 至少一组历史 trace replay。

### 4.6 写 repair trigger

trigger 的写法应该表达“在线诊断信号近似了理想触发窗口”，而不是表达一条经验猜测。

推荐结构：

```yaml
applies_to:
  all:
    - target_name_matches: "<target-regex>"
trigger:
  all:
    - holding_status_is: handempty_or_unconfirmed
    - ...
  any:
    - ...
```

写 trigger 时必须检查：

- `applies_to` 是否足够窄；
- trigger 是否有多源证据；
- 是否能在 `last_safe_query` 附近触发；
- 是否不会在成功 episode 中过早触发；
- 是否不会在已确认 holding 后再次触发 pick recovery；
- 是否与已有 repair priority 冲突。

### 4.7 验证与入库

正式进入 online 之前必须完成：

1. repair 静态测试；
2. 历史 trace replay；
3. priority / overlap scan；
4. 同 init validation；
5. 失败残例复查视频或抽帧。

如果 validation 失败，先回到视觉诊断和强制触发实验，不要反复微调 YAML 阈值。
通过数量按本 run 的 trials 与成功率阈值计算：15条/60%需要9成功。前5条全失败的早停规则
只用于拒绝，不把验收改成“3/5即可通过”。诊断 probe 不计分、不消耗 writes。

## 5. Trigger Family 模板

下面模板只给最低结构。具体阈值必须来自视频定位、强制触发实验和 trace replay。

### 5.1 Target Approach

适用：VLA 正在接近正确目标，但继续执行可能抓浅、抓坏或错过稳定入口。

```yaml
kind: repair
hook: after_pi0_query
backend: cutamp_recover
applies_to:
  all:
    - target_name_matches: "<target-regex>"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - target_ee_distance_lt: 0.11
  any:
    - nearest_pickable_is_target: true
    - intent_object_is_target: true
    - target_future_min_xy_distance_lt: 0.07
```

要求：

- 必须来自“早切入能救”的强制触发实验。
- 距离阈值越大，越需要 intent 或 future trajectory 证据。
- 如果目标会被接近动作推歪，触发窗口应在接触前，而不是 close 后。

### 5.2 Target Stall / Empty Grasp

适用：目标附近停住，或合爪后没有确认持有。

```yaml
applies_to:
  all:
    - target_name_matches: "<target-regex>"
trigger:
  all:
    - holding_status_is: handempty_or_unconfirmed
    - nearest_pickable_is_target: true
    - target_ee_distance_lt: 0.11
    - ee_stalled:
        window: 3
        max_disp_m: 0.015
```

要求：

- `ee_stalled` 必须搭配目标一致性证据。
- 如果用了 `aperture_lt`，必须解释为什么 close 后仍判断未持有。
- 要区分“目标附近停住”和“被非目标/环境挡住”。

### 5.3 Wrong Object Intent

适用：VLA 的轨迹稳定地朝非目标物体发展，但错误搬运尚未完成。

```yaml
applies_to:
  all:
    - target_name_matches: "<bounded-target-regex>"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - intent_object_is_target: false
    - wrong_object_intent_persist_queries_gte: 3
    - wrong_object_intent_margin_gt: 0.055
    - intent_min_xy_distance_lt: 0.075
    - nearest_pickable_is_target: false
    - nearest_pickable_distance_lt: 0.24
    - target_ee_distance_gt: 0.10
    - target_future_min_xy_distance_gt: 0.085
```

要求：

- 必须用多 query 持续性，不允许单帧判断。
- 不能把 gripper close 当成唯一证据。
- 必须用成功/失败对照视频验证没有把正常绕行误判为抓错。

### 5.4 Wrong Object Progress

适用：错误对象已经被明显搬动，目标对象仍基本静止。

```yaml
applies_to:
  all:
    - target_name_matches: "<target-regex-or-.+>"
  any:
    - goal_name_matches: "<goal-regex>"
    - bddl_goal_surface_matches: "<surface-glob>"
trigger:
  all:
    - wrong_progress_target_static: true
    - wrong_progress_object_total_motion_gt: 0.06
  any:
    - vla_wrong_object_progress_status_is: wrong_object_at_goal
    - vla_wrong_object_progress_status_is: wrong_object_transported
```

要求：

- 如果目标匹配很宽，goal / BDDL surface 锚点必须更强。
- 必须确认目标没有同步移动。
- 要用视频确认错误对象确实被搬运，而不是碰撞造成的环境扰动。

### 5.5 Articulated Blocker

适用：打开抽屉、门等 articulated object 阻挡正常 pick。

```yaml
applies_to:
  all:
    - target_name_matches: "<target-regex>"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - target_ee_distance_gt: 0.12
    - vla_articulated_blocker_status_is: blocked_open_drawer_before_pick
```

可选 entry hint：

```yaml
recovery_hints:
  params:
    repair_profile: entry_lift_escape_current_away_blocker_v1
```

要求：

- “抽屉默认打开”不是触发证据。
- blocker 状态必须来自动态诊断，例如持续卡住、EE 接近 blocker 且目标仍未接近。
- 如果触发后仍卡住，优先考虑 grasp 入口方向或 executor entry，而不是只改 trigger。

## 6. Evidence 写法

每个 repair 正文必须包含以下 evidence。

```markdown
## Visual Diagnosis

- Source videos / frames: ...
- Compared episodes: failure ep00/ep03, success ep01
- Common failure pattern: ...
- Success/failure split: ...
- last_safe_query: ...
- first_visible_error_query: ...
- too_late_query: ...

## Force Recovery Ablation

- qXX: success/failure, reason
- qYY: success/failure, reason
- Conclusion: earliest useful trigger window is ...

## Trigger Rationale

- Chosen family: ...
- Predicate mapping:
  - visual signal -> qstate predicate
- Existing repair diagnostics: ...
- Priority / overlap expectation: ...

## Anti-patterns

- Do not trigger when ...
- Do not use for ...
```

如果缺少视觉诊断或强制触发实验，repair 只能作为草稿，不能自动进入 online。

## 7. Applies-to 和 Priority

`applies_to` 必须先于 trigger 设计。先确定 skill 管哪类目标、哪类 goal、哪类 surface。

推荐：

```yaml
applies_to:
  all:
    - target_name_matches: "book|black_book"
    - bddl_goal_surface_matches: "*desk_caddy*_*_contain_region"
```

避免：

```yaml
applies_to:
  all:
    - task_language_matches: "put"
```

priority 表示同一 hook 下谁先触发。matcher 只返回第一个 winner。

正文必须说明：

- 它应该压过哪些 repair；
- 它不应该压过哪些 repair；
- 如果多个 repair 同时 would_fire，为什么当前 priority 合理。

## 8. 常见错误

| 错误 | 为什么危险 |
| --- | --- |
| 不看视频，只看 trace 写 trigger | 容易把不同失败混成同一种谓词模式。 |
| 没做强制触发实验 | 不知道 repair 时机是否真的能救。 |
| 用 query index 触发 | 只能用于诊断，不能上线。 |
| 用绝对 xyz | 初始化变化后失效。 |
| 只看 task language | 会跨物体、跨目标误触发。 |
| wrong-object 只看最近物体 | 容易把正常绕行或碰撞误判为抓错。 |
| close 后就认为抓错 | 夹爪开度不是可靠抓错证据。 |
| 缺诊断信号时硬凑 trigger | 会产生看似合理但不可验证的 skill。 |
| 新增 runner 字段不落盘 | 后续无法 replay 和审计。 |
| repair 里写 grasp / grounding / geometry / place | 职责混乱，后续维护困难。 |
| repair 里内联 `params.executor` | 低层动作参数会散落在 skill 中，应该改成注册过的 `repair_profile`。 |
| 高 priority 泛化 repair | 容易抢掉已有稳定 repair。 |

## 9. 最小交付物

Codex 写 repair 时至少交付：

1. `draft.md` 或正式 `<pack>/skills/pair/repair/*.md`。
2. `findings.md`，包含视觉诊断、多 episode 对照和是否需要新增 runner 诊断信号。
3. 强制 query recovery ablation 结果。
4. repair 静态 gate 结果。
5. 历史 trace replay / priority overlap 报告。
6. 同 init validation 结果。

如果没有第 3-6 项，repair 只能停在 `fail_only` 或人工审阅状态，不得自动进入 online。
