# Place Skill Authoring Guidelines

更新日期：2026-09-12

本文给后续 Codex / agent 编写 `place` recovery hint 使用。核心要求是：

> 依据执行事件或明确的 executor/几何不匹配提出 place 修复，并在能到达相应阶段的小验证中检验。

允许先从代码和几何提出可检验
的 place 假设，但不能用它掩盖尚未解决的 pick/目标问题。可以在同一次介入内补齐上游后继续验证。

`place` skill 不负责触发 recovery，不负责选择 grasp，不负责决定目标 region，也不负责创建
planner geometry。它只在已经 holding 目标后，处理 transfer、hover、yaw、XY 对齐、drop 和
release 前的局部动作问题。

## 1. 当前运行位置

`place` skill 必须写在 active skill pack 下面：

```text
skill_packs/<pack>/skills/pair/recovery_hint/place/
```

是否 online 只看该 pack 的 `skills/_index.yaml`。已入库 Markdown 应优先只引用：

```yaml
recovery_hints:
  params:
    place_profile: <registered_place_profile>
```

profile 参数在 `skill_packs/<pack>/profiles/place.yaml` 中。正式链路是：
`place_profile` -> `hooks.hover/align/release` -> pack-local
`code/place_policies.py` -> 受限 `params.executor`。只有 profile-authoring 草稿阶段才允许
临时内联 executor 参数；正式入库时应把参数收进 `place_profile`，并在
`capabilities.yaml` 注册。

## 1.1 Place Policy Adapter 契约

新增 benchmark-specific place 行为选择时，优先改 active skill pack：

```text
skill_packs/<pack>/profiles/place.yaml
skill_packs/<pack>/code/place_policies.py
skill_packs/<pack>/capabilities.yaml
```

pack-local adapter 必须暴露：

```python
ADAPTER_NAME = "..."
PROFILE_IDS = ("registered_place_profile_v1", ...)

def resolve_hover_policy(profile: str, profile_data: dict, params: dict) -> dict:
    ...

def resolve_align_policy(profile: str, profile_data: dict, params: dict) -> dict:
    ...

def resolve_release_policy(profile: str, profile_data: dict, params: dict) -> dict:
    ...
```

函数名也可使用 `resolve_place_hover_policy`、`resolve_place_align_policy`、
`resolve_place_release_policy`。adapter 可以只实现其中一类 hook，但 `PROFILE_IDS` 必须覆盖
它负责的 profile。

当前 hook 只有三类：

| hook | 用途 | 已支持 mode |
| --- | --- | --- |
| `hover` | holding 后到 place 区域上方前的转移 / 抬高 | `held_transfer_keep_z` |
| `align` | hover / yaw 后，释放前的 held-object XY 对齐 | `held_object_xy_align` |
| `release` | final drop / open / retreat 阶段 | `closed_loop_drop` |

`mode: executor_options` 可用于只输出 executor 参数、不附加 mode 默认开关。未知 hook 名、
未知 hook key、未知 executor key 都会在 profile 展开时失败，不会静默失效。

如果一个任务需要“新动作”，先判断它能否表达成现有三类 hook 的参数组合。不能表达时，应在
`findings.md` 中提出共享 executor primitive，而不是在 task-specific skill 里直接改
`libero_tiptop_executor.py`。

## 2. 职责边界

`place` skill 负责：

- holding 后转移时保持安全高度；
- place hover 后的受限 yaw 配合，如果它已经由 geometry 暴露；
- release 前根据 live object footprint 做小范围 XY 对齐；
- final drop 期间做分段闭环对齐；
- 给 executor 设置有限预算和容差；
- 说明失败时是 abort 还是允许回到 VLA。

`place` skill 不负责：

- 判断什么时候进入 recovery；
- 判断 VLA 是否抓错对象；
- 选择抓取点或 grasp profile；
- 修正 BDDL / target / surface 绑定；
- 构造 virtual surface / region bounds；
- 修改 collision world；
- 放宽成功判定；
- 硬编码 episode、seed、query 或最终物体坐标。

如果问题本质不是 place，应转给对应类别：

| 问题 | 应写 |
| --- | --- |
| 触发太早/太晚/没触发 | `<pack>/skills/pair/repair/` |
| 抓取点、yaw、高度、close 深度不对 | `<pack>/skills/pair/recovery_hint/grasp/` |
| 目标 surface / region 绑定错 | `<pack>/skills/pair/recovery_hint/grounding/` |
| region / support surface 在 planner 中不存在或尺寸错误 | `<pack>/skills/pair/recovery_hint/geometry/` |

## 3. 输入材料

编写 place 前必须检查：

| 材料 | 用途 |
| --- | --- |
| 失败视频或抽帧 | 确认失败发生在 transfer / hover / yaw / drop / release，而不是 pick。 |
| 成功和失败 episode 对照 | 看失败是否来自释放前局部动作。 |
| `recovery_trace.jsonl` | 看 place events、release guard、drop error、alignment event。 |
| `.problem.json` / planner debug | 确认 planner 有可行 place plan，目标 surface 正确。 |
| grounding / geometry skill 命中记录 | 确认目标语义和目标几何已经正确。 |
| live object geometry / footprint | 判断是否需要 footprint-based 对齐。 |
| 当前 online place skills | 避免重复写或扩大已有补丁。 |

上游尚未可靠时，不宣称 place 已验证，也不靠增加 place 预算解释优化无解。若有具体代码/几何
证据，可以拟写 place 候选并在同一次介入中修复上游；需要实际到达该阶段的 probe 才能评价效果。

## 4. 标准诊断流程

### 4.1 先确认 pick 已经成功

至少回答：

- close 后目标是否随夹爪上抬？
- holding latch 是否确认了目标？
- 失败前是否一直 holding 同一个目标？
- 如果目标没抓住或抓错了，应该先写 grasp / repair，不写 place。

### 4.2 确认目标和几何已经正确

至少回答：

- compiled goal surface 是不是预期目标？
- `surface_opening` 是否存在？
- place candidates 是否在正确 region 内？
- planner 是否已经产出可执行的 pick/place plan？
- 如果 surface 错，应写 grounding；如果 surface 不存在或 bounds 错，应写 geometry。

### 4.3 定位 place 阶段

把失败归到下面某个阶段：

| 阶段 | 现象 | 可能 place skill |
| --- | --- | --- |
| held transfer | 物体抓住后，转移到目标上方前逐渐下降并撞环境 | keep-z transfer |
| hover-yaw 后 | 姿态旋转后，held object footprint 偏离 opening | XY footprint align |
| final drop | 下放时 tracking drift，逐渐偏出 opening | closed-loop drop align |
| release check | 物体已经接近目标，但 release guard 拒绝开爪 | 检查 opening / footprint，不先放宽 guard |
| abort handoff | place 失败后交回 VLA 导致更差 | 对特定任务选择 abort 而不是 VLA handoff |

### 4.4 一次只修一个动作问题

| 要验证的变量 | 做法 |
| --- | --- |
| transfer 高度 | 只打开 keep-z，不改 drop / release。 |
| XY 对齐 | 只打开 held-object align，不改 grounding / geometry。 |
| drop drift | 只增加分段下放和每段对齐。 |
| release tolerance | 只在有 footprint 证据时小幅设置，不能靠放宽容差过关。 |
| 执行预算 | 只在已有动作方向正确但没执行完时增加。 |

不要一次同时改 grasp、region bounds、collision、alignment、release guard。

## 5. 常见写法

### 5.1 Held-transfer Keep-z

适用于已经抓住物体后，移动到 place 区域的途中因为下降而撞环境。

`profiles/place.yaml` 推荐字段：

```yaml
profiles:
  task38_held_transfer_keep_z_v1:
    hooks:
      hover:
        mode: held_transfer_keep_z
        held_transfer_z_margin_m: 0.020
        held_transfer_max_descent_m: 0.000
        held_transfer_max_steps: 45
        held_transfer_reached_m: 0.006
```

使用前必须证明：

- pick 已成功；
- 目标和 place region 正确；
- 碰撞发生在 transfer，而不是 final drop；
- 高度保持不会改变目标语义。

### 5.2 Held-object XY Footprint Align

适用于已经 hover 到目标 opening 上方，但 held object footprint 边界或中心仍有偏差。

`profiles/place.yaml` 推荐字段：

```yaml
profiles:
  caddy_book_compartment_align_budget_v1:
    hooks:
      align:
        mode: held_object_xy_align
        place_align_reached_m: 0.0015
        place_align_center_tolerance_m: 0.006
        place_footprint_release_tolerance_m: 0.001
        place_align_step_clip_m: 0.006
        place_align_max_iters: 8
        place_align_max_steps_per_iter: 12
      release:
        mode: closed_loop_drop
        place_drop_align_slices: 3
        place_drop_max_steps: 80
```

使用前必须证明：

- `surface_opening` 是正确 opening；
- live footprint 可读，或者 fallback 行为可接受；
- 物体不是 oversize；
- 修正量是小范围的 executor nudge；
- 不会把错误目标强行塞进错误区域。

### 5.3 新 Place 行为的判定

| 需求 | 应该怎么做 |
| --- | --- |
| 已有动作，只是参数不同 | 新增 `place_profile`，必要时由 `code/place_policies.py` 选择 hook。 |
| 需要根据 benchmark 名称/region 选择不同参数 | 写 pack-local `place_policies.py` adapter。 |
| 需要 executor 执行一种全新低层动作 | 提出共享 engine primitive，补 executor、capability、测试和文档。 |
| 只是目标点或 region 错 | 回到 grounding / geometry，不写 place。 |
| 只是抓取姿态导致放不进去 | 回到 grasp，不写 place。 |

## 6. 写 Markdown Skill

模板：

```yaml
---
id: place_<task_or_object>_<strategy>
name: <Human readable name>
kind: recovery_hint
track: pair
scope: place
priority: 48
when_to_apply: When recovery has already grasped ...
when_not_to_apply: Do not use for ...
failure_signature:
  - ...
recovery_point: After a repair/trigger skill has already decided to call recovery and after ...
applies_to:
  all:
    - task_language_matches: "<narrow regex>"
    - target_name_matches: "<target class>"
    - bddl_goal_surface_matches: "<region pattern>"
recovery_hints:
  params:
    place_profile: <registered_place_profile>
evidence:
  tasks:
    - ...
  episodes:
    - ...
---

## Intent

This policy contributes only executor-side place behavior. It does not change
triggering, grounding, geometry, or grasp sampling.
```

## 7. 验证流程

每个 place skill 至少走四步：

1. **静态 gate**
   检查 schema、scope、executor allowlist、数值范围、适用范围和 canary。

2. **trace scan**
   检查新 skill 是否只在 expected task family 命中，并记录 executor overrides。

3. **forced / small online validation**
   在已知 pick 可成功的 episode 上验证 place 行为，必要时强制 recovery 到同一阶段。

4. **视频核对**
   看物体是否在抓住后保持正确高度、是否在 release 前进入 opening、是否在 drop 中漂移。

验证时不只看最终 success，还要看：

- place skill 是否执行；
- 执行时是否 holding 正确目标；
- release guard reason 是否从错误状态变成 `ok`；
- 没成功的 episode 是否保留了足够的 place event 诊断。

## 8. Evidence 写法

正文建议包含以下内容：

```markdown
## Place Diagnosis

- Pick status: ...
- Grounding status: ...
- Geometry status: ...
- Failure stage: held transfer / hover-yaw / drop / release
- Observed event: ...
- Video / trace source: ...

## Executor Patch

- Executor keys: ...
- Place profile: ...
- Numerical budget: ...
- Safety bounds: ...
- Failure behavior: abort / return-to-VLA

## Boundary

- This skill only contributes executor-side place behavior.
- It does not change trigger / grounding / geometry / grasp.

## Validation

- Static gate: ...
- Trace scan: ...
- Online validation: ...
```

## 9. 反模式

不要这样写：

- 物体没抓住就写 place；
- 目标 surface 错了还用 XY align 补；
- region bounds 错了还用 place nudge 补；
- 用很大的 release tolerance 让 guard 开爪；
- 把 place skill 写成所有任务通用；
- 在 place skill 里写 `grounding_hints` 或 `geometry_hints`；
- 已入库 place skill 仍直接内联一大段 `params.executor`；
- 只看中心点，不看 held object footprint；
- place 失败后无条件交回 VLA；
- 一次同时改 transfer、drop、release guard 和 geometry。

place skill 的价值在于最后几厘米的稳健执行。它应该窄、小、可回放，并且不替其它层背锅。
