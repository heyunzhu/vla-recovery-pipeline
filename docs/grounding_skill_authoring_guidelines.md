# Grounding Skill Authoring Guidelines

更新日期：2026-09-12

本文给后续 Codex / agent 编写 `grounding` recovery hint 使用。核心要求是：

> 用 BDDL、场景与实际编译规则检查目标绑定，修正已观察到的错绑或可证实的映射缺失，再检查配套 geometry。

BDDL 与 scene/编译代码之间
缺少必要映射也属于证据；无需等 rollout 到 place 才能提出 grounding 假设。

`grounding` skill 不负责触发 recovery。它只在 recovery 已经发生后，影响 planner 如何理解
“把目标放到哪里”。

## 1. 当前运行位置

`grounding` skill 必须写在 active skill pack 下面：

```text
skill_packs/<pack>/skills/pair/recovery_hint/grounding/
```

是否 online 只看该 pack 的 `skills/_index.yaml`。已入库 Markdown 应只引用
`params.grounding_profile`；profile 参数在 `skill_packs/<pack>/profiles/grounding.yaml`，
benchmark-specific 翻译逻辑在 `skill_packs/<pack>/code/grounding_profiles.py`。runtime 会先把
profile 展开成 `params.grounding_hints`，再由 goal compiler 消费。

主流程里只应保留通用 planner primitive，例如 `table_region_surface`、
`container_region_surface`、`preferred_support_surface`、`preferred_container_surface` 和
`movable_support_surface`。类似 LIBERO-90 的 caddy compartment、plate-side、top drawer 等
命名规则属于 pack-local adapter，不应再散落回主流程。

## 1.1 Profile / Adapter 契约

新增 benchmark-specific grounding 能力时，优先改 active skill pack，而不是改
`real_cutamp_adapter.py`：

```text
skill_packs/<pack>/profiles/grounding.yaml
skill_packs/<pack>/code/grounding_profiles.py
skill_packs/<pack>/capabilities.yaml
```

pack-local adapter 必须暴露：

```python
ADAPTER_NAME = "..."
PROFILE_IDS = ("registered_grounding_profile_v1", ...)

def normalize_grounding_profile_params(profile: str, params: dict) -> dict:
    ...
```

adapter 的输出仍然是 `params.grounding_hints`，并且其中的 `placement_surface` /
`support_object` 要能被主引擎的通用 primitive 消费。当前通用 primitive 由
`experiments/robot/libero/tiptop_repro/engine_capabilities.py` 统一定义：

| planner primitive | 典型 intent |
| --- | --- |
| `table_region_surface` | `bddl_table_region` / `fixed_table_region` |
| `container_region_surface` | `container_compartment` / container inside region |
| `preferred_support_surface` | `top_support` / `shelf_support` |
| `preferred_container_surface` | `drawer_container` |
| `movable_support_surface` | `stack_support` |

如果新 benchmark 只是有新的命名规则、region 选择规则或 alias，写 pack adapter 映射到这些
primitive。只有当这些 primitive 表达不了任务语义时，才在 `findings.md` 中提出新增共享
primitive；不要在 task-specific skill 中直接加主引擎分支。

## 2. 职责边界

`grounding` skill 负责：

- 选择 `placement_surface`；
- 选择 `support_object`；
- 保留 BDDL 中已经给出的虚拟 region；
- 把已观察到的错误绑定重写回正确 region；
- 区分相似语言，例如 “right of caddy” 和 “right compartment of caddy”；
- 说明它依赖哪一个 geometry skill。

`grounding` skill 不负责：

- 判断什么时候进入 recovery；
- 选择 grasp candidates；
- 修改物体尺寸、碰撞体、region bounds；
- 释放前闭环 XY 对齐；
- 调整 release guard；
- 增加执行器动作；
- 绕过 collision / IK 约束；
- 硬编码 episode、seed 或执行时绝对坐标。

如果问题本质不是目标绑定，应转给对应类别：

| 问题 | 应写 |
| --- | --- |
| 触发太早/太晚/没触发 | `<pack>/skills/pair/repair/` |
| 抓取点、yaw、高度、close 深度不对 | `<pack>/skills/pair/recovery_hint/grasp/` |
| region / support surface 在 planner 中不存在或尺寸错误 | `<pack>/skills/pair/recovery_hint/geometry/` |
| holding 后释放前需要局部对齐或特殊下放 | `<pack>/skills/pair/recovery_hint/place/` |

## 3. 输入材料

编写 grounding 前必须检查：

| 材料 | 用途 |
| --- | --- |
| task language | 看任务的语义关系，是 `on`、`inside`，还是 left/right/front/back。 |
| BDDL goal atoms | 找官方目标 surface / region / support object。 |
| `bddl_goal_surfaces` | 判断是否已有虚拟 region，例如 `*_plate_right_region`。 |
| `query_trace.jsonl` | 看 target、goal、surface 解析结果。 |
| `recovery_trace.jsonl` | 看 recovery 实际编译出的 goal surface。 |
| `.problem.json` / planner debug | 看 cuTAMP 收到的是哪个 surface 或 proxy。 |
| 失败视频或抽帧 | 确认不是抓取或执行器问题伪装成 grounding。 |
| 当前 online grounding / geometry skills | 避免写重复或冲突 skill。 |

禁止只凭任务描述猜目标。证据可以是“应绑定到 A，实际绑定到 B”，也可以是 BDDL 已指定 A，
但 scene/编译规则没有把 A 表达为可用的目标。列出具体字段和代码路径，通过 probe/replay 验证，
不能把尚未执行的推断写成已观察到的错绑。

## 4. 标准诊断流程

### 4.1 判断是否真是 grounding 问题

至少回答：

- 目标物体是否正确？
- 任务要求的目标区域是什么？
- BDDL 中是否有明确 goal surface / region？
- recovery 编译出的 surface 是不是这个 region？
- 如果不是，它被误绑定到了哪个实体？
- 如果 surface 正确但没有可行解，是不是 geometry / collision / place 问题？

常见 grounding 问题：

| 现象 | 典型原因 |
| --- | --- |
| 要放到 plate 右侧，却编译成放到 plate 上 | BDDL table-side region 没被保留。 |
| 要放到 caddy 右侧，却绑定到 caddy body | `desk_caddy_1_main` 抢走了虚拟 side region。 |
| 要放进 caddy front compartment，却只知道 caddy main | compartment region 没被作为目标语义传下去。 |
| 要放进 top drawer，却绑定到 cabinet main 或 cabinet top | drawer container 和 top support 混淆。 |
| 要 stack bowl，却报告第二个 bowl 不是 surface | movable support 没注册为 support object。 |

反过来，如果 planner 目标 surface 已经正确，但抓不住、撞环境、release guard 不开爪，
不要写 grounding skill。

### 4.2 找官方目标

优先从 BDDL 找目标，而不是从视频里估一个点。

要记录：

| 字段 | 例子 |
| --- | --- |
| target object | `white_bowl_1_main` |
| semantic relation | `on` / `inside` |
| BDDL goal surface | `kitchen_table_plate_right_region` |
| observed wrong surface | `plate_1_main` |
| desired planner surface | `kitchen_table_plate_right_region` 或对应 proxy |

如果 BDDL 只有相对描述，没有直接可用 region，才考虑 task-specific fixed region。fixed region
必须在文档里说明来源，并配套 geometry skill。

### 4.3 选择 grounding 形态

| 形态 | 什么时候用 | hint |
| --- | --- | --- |
| BDDL table region | BDDL 已有 `*_plate_left_region` / `*_desk_caddy_right_region` | `placement_surface.intent: bddl_table_region` |
| Fixed table region | 少数 task 的 BDDL region 固定且已知 | `placement_surface.intent: fixed_table_region` |
| Container compartment | 放进 caddy front/back/left/right compartment | `placement_surface.intent: container_compartment` |
| Top support | 放到 cabinet top / top side | `placement_surface.intent: top_support` |
| Shelf support | 放到 shelf top support | `placement_surface.intent: shelf_support` |
| Drawer container | 放进 top drawer | `placement_surface.intent: drawer_container` |
| Movable support | 放到另一个可移动物体上 | `support_object.intent: stack_support` |

选择后要检查当前 skill pack 的 grounding profile / adapter 是否能把它映射到主流程已支持的
planner primitive。不要发明未注册 intent，也不要为了一个 benchmark 把新 intent 直接写进主流程。
如果确实新增了 pack-local intent 名称，也必须在 `capabilities.yaml` 的
`grounding_hint_intents` 中注册，并由 adapter 归一化到上表中的通用 primitive。

### 4.4 检查是否需要 geometry

grounding 决定“指向哪里”，geometry 决定“planner 里这块地方长什么样”。

需要 geometry 的情况：

- region 不是 scene 中真实 object；
- BDDL surface 是虚拟 table region；
- container compartment 需要 inner floor proxy；
- drawer / shelf 需要内部或顶部支撑面 proxy；
- movable support 需要把可移动物体注册成 support surface。

如果只写 grounding、不写 geometry，常见结果是：matcher 命中了 skill，但 cuTAMP 仍然找不到
surface 或只能退回错误实体。

### 4.5 写 markdown skill

已入库的 grounding skill 应把具体参数放在当前 skill pack 的
`profiles/grounding.yaml`，Markdown 里只引用 `grounding_profile`。只有在新增 profile 的
草稿阶段，才允许临时内联 `grounding_hints`。

如果 profile 需要 benchmark-specific 的翻译逻辑，应在对应 skill pack 的
`code/grounding_profiles.py` 中把 profile 映射到已有 planner primitive，例如
`table_region_surface`、`container_region_surface`、`preferred_support_surface`、
`preferred_container_surface` 或 `movable_support_surface`。

不要把 `planner_primitive` 留空后指望主流程靠名称猜测。profile / adapter 应把“这是 table
region、container region、preferred support，还是 movable support”显式传给后端。

模板：

```yaml
---
id: <name>_grounding
name: <Human readable name>
kind: recovery_hint
track: pair
scope: grounding
priority: 48
when_to_apply: When an already-triggered recovery ...
when_not_to_apply: Do not use for ...
failure_signature:
  - The BDDL goal surface is ...
  - The semantic fallback can bind the goal to ...
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "<narrow regex>"
    - target_name_matches: "<target class>"
    - bddl_goal_surface_matches: "<region pattern>"
recovery_hints:
  params:
    grounding_profile: <registered_grounding_profile_v1>
evidence:
  tasks:
    - ...
  episodes:
    - ...
---

## Intent

This policy contributes only target grounding. It does not create planner
geometry, choose a grasp, or decide when recovery should start.
```

## 5. 常见写法

### 5.1 BDDL table-side region

适用于 “to the left/right of the plate/caddy” 这类任务。

关键点：

- `applies_to` 必须包含 BDDL goal surface；
- `region_name_from_bddl_goal: true`；
- `rewrite_misgrounded_goals` 只列已观察到的错误实体；
- 配套 geometry 使用 BDDL region bounds。

不要把 “right of caddy” 和 “right compartment of caddy” 混为一类。前者通常是 table
side region，后者可能是 container compartment。

### 5.2 Fixed task region

适用于 task35 / task38 这类已经确认 region name 的任务。

关键点：

- `region_name` 必须是明确 BDDL region；
- `applies_to` 要足够 task-specific；
- 正文写明为什么不能使用通用 plate-side / mug-side skill；
- 必须有同名或明确配套 geometry skill。

fixed region 是最后手段。能从 BDDL goal 动态读取时，优先动态读取。

### 5.3 Container compartment

适用于 caddy front/back/left/right compartment。

关键点：

- grounding 不要写死 `compartment: left` 或 `compartment: front`；
- 用 `region_name_matches` 覆盖四类 contain region；
- 具体 compartment 从 BDDL goal surface / region name 解析；
- geometry 负责 inner floor、entry candidate、collision proxy；
- place skill 负责释放前 XY footprint 对齐。

这个边界很重要：grounding 只保留 “目标是哪个格子”，不决定书怎样旋转、怎样下放。

### 5.4 Top / Drawer / Shelf

适用于 cabinet top、top drawer、shelf support。

关键点：

- `prefer` 写目标 surface；
- `avoid` 写容易误绑定的 drawer / door / handle / body；
- `fallback` 只能作为保守回退，不应优先使用；
- drawer container 和 cabinet top 是两类相反语义，一个是 `inside`，一个是 `on`。

### 5.5 Movable Support

适用于 bowl stack。

关键点：

- 使用 `support_object`，不是 `placement_surface`；
- `object_class` 必须写清楚；
- 只允许可移动 support 相关谓词，例如 `on`；
- 配套 geometry 要负责注册临时 support surface。

## 6. 验证流程

每个 grounding skill 至少走四步：

1. **静态 gate**
   检查 schema、intent、scope、anchor、配套 geometry、canary。

2. **matcher canary**
   用伪状态验证它命中该命中的任务，不抢不该抢的任务。

3. **trace scan**
   用历史 trace 扫描新 skill 是否改变已成功 episode 的绑定。

4. **小规模 online 验证**
   看 recovery trace 中的 `compiled_goal_surface`、planner problem 的 surface、最终视频位置。

如果修复后仍然是 0/64 或 place 不开爪，先确认 compiled goal surface 是否正确。surface
正确才进入 geometry / place / executor 诊断。

## 7. Evidence 写法

正文建议包含以下内容：

```markdown
## Grounding Diagnosis

- Task language: ...
- BDDL goal surface: ...
- Expected binding: ...
- Observed wrong binding: ...
- Evidence trace/problem: ...

## Boundary

- This skill only contributes grounding.
- Paired geometry skill: ...
- It does not change grasp / geometry / place / trigger.

## Validation

- Matcher canary: ...
- Trace scan: ...
- Online validation: ...
```

## 8. 反模式

不要这样写：

- 只靠 `task_language_matches`；
- 用 `target_name_matches: ".+"`；
- 把多个目标语义混进一个 skill，例如 caddy side 和 caddy compartment；
- 在 grounding 里写 `geometry_hints`；
- 在 grounding 里写 executor 参数；
- 为了绕过 planner 失败，把错误 surface 重写到一个看起来更容易规划的实体；
- 没看 BDDL goal surface，只凭视频猜 region；
- 让 task-specific skill 覆盖一批未验证任务。

grounding skill 的价值在于语义准确。它不需要聪明地补偿所有后续问题，只需要把目标传对。
