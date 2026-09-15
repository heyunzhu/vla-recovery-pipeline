# Geometry Skill Authoring Guidelines

更新日期：2026-09-12

本文给后续 Codex / agent 编写 `geometry` recovery hint 使用。核心要求是：

> 对照 BDDL、实际尺寸和 scene 构造代码，确认目标区域表示的缺失或错误，再建立可审计的 virtual surface / proxy。

可以在尚未进入 recovery 时
从 scene 与代码发现缺失的支撑面、开口或错误尺寸；随后以固定 probe 验证实际 planner 输入。
grounding 和 geometry 可以在同一 bundle 内配套修复，不必先花一轮验证错误绑定。

`geometry` skill 不负责触发 recovery，也不负责选择目标语义。它只影响 planner 怎样表示
已经确定的目标区域。

## 1. 当前运行位置

`geometry` skill 必须写在 active skill pack 下面：

```text
skill_packs/<pack>/skills/pair/recovery_hint/geometry/
```

是否 online 只看该 pack 的 `skills/_index.yaml`。已入库 Markdown 应只引用
`params.geometry_profile`；profile 参数在 `skill_packs/<pack>/profiles/geometry.yaml`，
benchmark-specific 测量/裁剪逻辑在 `skill_packs/<pack>/code/geometry_profiles.py`。runtime 会先把
profile 展开成 `params.geometry_hints` 和受限 executor metadata，再由 `tamp_scene.py`、
`real_cutamp_adapter.py` 和 executor 消费。

主流程里只应保留通用 primitive，例如 table rect、inner-floor proxy、movable support surface、
surface opening 序列化和 executor 对 opening 的通用消费。类似 LIBERO-90 desk-caddy site 表、
compartment 裁剪比例、plate/caddy side crop 等 benchmark-specific 手艺属于 pack-local adapter。

## 1.1 Profile / Adapter 契约

新增 benchmark-specific geometry 能力时，优先改 active skill pack，而不是改 `tamp_scene.py`
或 `real_cutamp_adapter.py`：

```text
skill_packs/<pack>/profiles/geometry.yaml
skill_packs/<pack>/code/geometry_profiles.py
skill_packs/<pack>/capabilities.yaml
```

pack-local adapter 必须暴露：

```python
ADAPTER_NAME = "..."
PROFILE_IDS = ("registered_geometry_profile_v1", ...)

def normalize_geometry_profile_params(profile: str, params: dict) -> dict:
    ...
```

adapter 的输出仍然是 `params.geometry_hints`。其中 `placement_region` /
`movable_support_surface` 要显式给出 `intent` 或 `planner_primitive`，并映射到主引擎支持的
通用 geometry primitive：

| planner primitive | 作用 |
| --- | --- |
| `fixed_table_rect` | 在 table / support plane 上创建矩形 region。 |
| `inner_floor` | 为 container / drawer / shelf / caddy compartment 创建内部地板 proxy。 |
| `movable_support_surface` | 临时把可移动物体注册为 support surface。 |

如果需要的只是新容器的测量、裁剪比例、site lookup、region fallback 或 collision metadata，
这些都属于 pack adapter。只有当要新增一种真正的几何构造方式，例如斜面、圆环、漏斗或复杂
非凸开口，才应作为共享 engine primitive 单独提出。

当前还支持一种轻量扩展：generic geometry descriptor。adapter 可以在 hint 中给
`surface_descriptor`，由主流程统一构造 `box`、`rotated_box`、`cylinder` 或 `sphere`。
descriptor shape 必须在 active pack 的 `capabilities.yaml` 中注册为
`geometry_descriptor_shapes`。

## 2. 坐标帧契约

当前 planner problem 使用 robot-base/planner frame。`tamp_scene._shift_geometry_to_robot_base`
会把 `geometry["geoms"]`、`geometry["sites"]`、`geometry["metadata"]["sites"]` 和
`geometry["metadata"]["containment_sites"]` 一起平移/旋转到 planner frame。geometry adapter
读取这些 site 或 bounds 时，必须假设它们已经和 movable/object pose 同帧。

virtual surface / inner-floor proxy 应在 metadata 中写明：

```yaml
inner_bounds_coordinate_frame: planner_frame
```

如果确实传入 world-frame opening，必须显式标注 `coordinate_frame: world`，让 executor 避免
二次 planner-to-world 转换。不要把 world 坐标悄悄塞进 planner-frame problem；这会让 cuTAMP
规划到一个偏移约 robot base offset 的“幻影位置”。

## 3. 职责边界

`geometry` skill 负责：

- 创建 BDDL table region 的薄矩形 support；
- 创建 container / drawer / shelf / caddy compartment 的 inner-floor proxy；
- 让 movable support object 临时注册为 planner surface；
- 设置 region bounds、margin、floor clearance、place candidate policy；
- 在必要且受限的情况下设置 collision exclusion；
- 在极少数需要几何姿态配合的任务中提供受限 executor yaw hint。

`geometry` skill 不负责：

- 判断什么时候进入 recovery；
- 决定 target / goal 应该绑定到哪个语义对象；
- 选择 grasp candidates；
- 判断 VLA 是否抓错物体；
- 释放前闭环 XY 对齐；
- 修改 holding latch 或 release guard 判定；
- 为了让规划通过而改写任务目标；
- 硬编码 episode、seed 或单次执行的最终物体坐标。

如果问题本质不是 planner geometry，应转给对应类别：

| 问题 | 应写 |
| --- | --- |
| 触发太早/太晚/没触发 | `<pack>/skills/pair/repair/` |
| 目标 surface / region 绑定错 | `<pack>/skills/pair/recovery_hint/grounding/` |
| 抓取点、yaw、高度、close 深度不对 | `<pack>/skills/pair/recovery_hint/grasp/` |
| holding 后释放前需要局部对齐或特殊下放 | `<pack>/skills/pair/recovery_hint/place/` |

## 4. 输入材料

编写 geometry 前必须检查：

| 材料 | 用途 |
| --- | --- |
| task language 和 BDDL goal atoms | 确认语义目标是什么。 |
| grounding 结果 | 确认目标已经绑定到正确 surface / region。 |
| `recovery_trace.jsonl` | 看 compiled goal surface、grounding、planner 失败原因。 |
| `.problem.json` | 看 planner 收到的 surfaces、place candidates、constraints。 |
| `cutamp_debug` / stderr | 看 0/64、collision、pos_err、unknown surface 等失败约束。 |
| MuJoCo / planner 几何可视化 | 看 region bounds、容器开口、目标物体尺寸是否合理。 |
| 失败视频或抽帧 | 核对物体是否卡在墙、桌面、容器唇、邻近物体。 |
| 当前 online grounding / geometry / place skills | 检查是否已有同类补丁，以及是否会冲突。 |

禁止只凭视频里“差一点”就写 geometry。geometry 必须能对应到 planner 世界里的 surface、
region bounds 或 collision 表示问题。

## 5. 标准诊断流程

### 5.1 先确认 grounding 已经正确

至少回答：

- recovery 的 target object 是否正确？
- semantic relation 是 `on` 还是 `inside`？
- BDDL goal surface / region 是什么？
- `real_cutamp_adapter.py` 编译出的 `compiled_goal_surface` 是不是预期 surface / proxy？
- 如果 surface 错了，先明确正确绑定，再按实际需要同时写 grounding 和 geometry；分别说明两者改变的字段。

### 5.2 判断 planner 缺的几何是什么

常见 geometry 问题：

| 现象 | 典型原因 |
| --- | --- |
| BDDL region 不是 scene object | 需要 BDDL table rect 或 fixed table rect。 |
| `inside(obj, container)` 不可执行 | 需要 inner-floor proxy，把 inside 编译成 on(proxy)。 |
| drawer / shelf region 不可放 | 需要内部地板 proxy。 |
| bowl stack 报 support 不是 surface | 需要 movable support surface。 |
| planner 有目标但 0/64 | 需要检查 bounds、z、collision、object footprint，而不是直接放宽 guard。 |
| 视频看起来撞容器边缘 | 需要核对 opening bounds、source collision、place candidate 和 release path。 |

### 5.3 把几何画出来

写 skill 前建议先生成可视化或表格：

- region / proxy 的 x/y/z bounds；
- source object 的 AABB / inner bounds；
- target object 的 footprint；
- place candidates；
- support z、planner support z、release z；
- surface / opening 的 coordinate frame；
- collision objects 和被 exclude 的对象；
- 当前抓取姿态下物体 footprint 是否能进入 opening。

尤其是 container / caddy / drawer / shelf，不要只看中心点。应同时看整体 footprint 是否进入
目标开口。

### 5.4 一次只验证一个变量

geometry 常和 grasp、grounding、place 互相耦合。定位时尽量一次只动一个变量：

| 变量 | 对照方式 |
| --- | --- |
| region bounds | 只替换 bounds，不改 grasp / release。 |
| support z | 只替换 support z 或 planner support z。 |
| collision | 只排除一个明确对象，保留其它碰撞。 |
| place candidates | 只改候选分布，不改目标 region。 |
| yaw / footprint | 只改 yaw policy 或交给 place skill 对齐。 |

如果多项一起改，即使成功也很难知道是哪一层起作用。

## 6. 常见写法

### 6.1 BDDL Table Rect

适用于 BDDL 已经定义了 table 上的 left/right/front/back region，但该 region 不是 scene object。

推荐字段：

```yaml
geometry_hints:
  placement_region:
    intent: bddl_table_rect
    relation: on
    support_surface: table
    region_name_from_bddl_goal: true
    bddl_goal_surface_matches:
      - "*_table_plate_left_region"
      - "*_table_plate_right_region"
    bounds_from_bddl_region: true
    align_bddl_regions_to_scene: true
    support_z_from: table
    thickness_m: 0.010
    min_span_m: 0.045
```

不要把 table-side region 改成 plate/caddy body。那是 grounding 错误，不是 geometry 修复。

### 6.2 Fixed Table Rect

适用于少数 task-specific region，已经从 BDDL 或反复验证中确认绝对 bounds。

推荐字段：

```yaml
geometry_hints:
  placement_region:
    intent: fixed_table_rect
    region_name: kitchen_table_plate_right_region
    support_surface: table
    bounds_m:
      x_min: 0.60
      x_max: 0.70
      y_min: 0.05
      y_max: 0.15
    support_z_from: table
    thickness_m: 0.010
    source_bddl_region: plate_right_region
```

fixed table rect 必须很窄地绑定 task，不要伪装成通用 region parser。

### 6.3 Inner-floor Proxy

适用于 `inside(obj, container)`，但当前 pipeline 没有可执行的 native place-in。

推荐字段：

```yaml
geometry_hints:
  placement_region:
    intent: container_inner_floor
    relation: inside
    container_name_matches:
      - "*basket*"
      - "*container*"
    proxy_suffix: inner_floor
    margin_m: 0.018
    floor_clearance_m: 0.006
    thickness_m: 0.010
    min_span_m: 0.045
```

它的含义是：语义仍然是 inside，但 planner 执行时把物体放到容器内部地板 proxy 上。

### 6.4 Compartment Inner-floor

适用于 desk caddy 这类有 front/back/left/right 格子的容器。

关键点：

- 不要在 skill 里写死 `compartment: left`；
- 从 BDDL region name 解析 compartment；
- 使用 `region_name_matches` 覆盖四个 compartment；
- 如果需要 high-drop，明确写 release mode 和 z/xy guard；
- 如果需要 yaw-after-hover，只能用受限 executor allowlist；
- book 的 grasp / footprint 由 grasp 和 place skill 分别负责。

`desk_caddy_compartment_geometry` 是当前最复杂的 geometry。新增类似 skill 时要优先参考它，
但不要把它扩成所有 container 的通用补丁。

### 6.5 Movable Support

适用于把可移动物体临时作为 support surface，例如 bowl stack。

推荐字段：

```yaml
geometry_hints:
  movable_support_surface:
    intent: stack_support
    object_class: bowl
    require_movable: true
    predicates:
      - on
```

不要用它处理普通 table / cabinet / shelf surface。

## 7. Collision Exclusion 原则

collision exclusion 是 geometry 中最容易写歪的部分。只有满足下面条件才考虑：

- planner 失败日志明确显示目标 source/container 或 support table 阻挡了进入目标区域；
- 被排除的对象就是目标区域的 source 或等价 support，不是无关障碍；
- 有对照 problem 证明不排除时卡在该碰撞；
- 正文写明为什么这个排除不改变任务语义。

不要为了让 0/64 变成可行解就大面积删障碍物。那会让 planner 通过，但视频里可能直接穿墙或
撞翻环境。

## 8. 写 Markdown Skill

已入库的 geometry skill 应把具体参数放在当前 skill pack 的
`profiles/geometry.yaml`，Markdown 里只引用 profile。只有在新增 profile 的
草稿阶段，才允许临时内联 `geometry_hints`。

如果 profile 需要 benchmark-specific 的翻译逻辑，不要继续往主流程里塞新的 intent 分支；
应在对应 skill pack 的 `code/geometry_profiles.py` 中把 profile 映射到已有 planner
primitive，例如 `fixed_table_rect`、`inner_floor` 或 `movable_support_surface`。如果使用
`surface_descriptor`，也要显式声明 shape、尺寸、坐标帧和来源，不要只传一个中心点。

模板：

```yaml
---
id: <name>_geometry
name: <Human readable name>
kind: recovery_hint
track: pair
scope: geometry
priority: 47
when_to_apply: When an already-triggered recovery ...
when_not_to_apply: Do not use for ...
failure_signature:
  - ...
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "<narrow regex>"
    - target_name_matches: "<target class>"
    - bddl_goal_surface_matches: "<region pattern>"
recovery_hints:
  params:
    geometry_profile: <registered_geometry_profile_v1>
evidence:
  tasks:
    - ...
  episodes:
    - ...
---

## Intent

This policy contributes only planner geometry. It does not bind the semantic
target, choose a grasp, or decide when recovery should start.
```

对应 `profiles/geometry.yaml` 才放数值和 primitive 参数：

```yaml
profiles:
  <registered_geometry_profile_v1>:
    params:
      geometry_hints:
        placement_region:
          intent: compartment_inner_floor
          region_name_from_bddl_goal: true
          thickness_m: 0.010
          min_span_m: 0.045
```

如果确实需要 executor 参数，也应优先放在 profile 里，并通过 allowlist；正文说明为什么它属于
geometry 的必要配套。
如果 executor 参数已经明显是在修 transfer / release / align，则应拆到 `place_profile`，不要
继续放在 geometry profile 中。

## 9. 验证流程

每个 geometry skill 至少走四步：

1. **静态 gate**
   检查 schema、intent、数值范围、region 来源、grounding 配套和 executor allowlist。

2. **matcher canary**
   检查它命中该命中的任务，不抢不该抢的任务。

3. **problem / trace scan**
   检查 `compiled_goal_surface`、created virtual surface、place candidates、surface opening、
   collision exclusions 是否符合预期。

4. **小规模 online 验证**
   看视频和 recovery trace，确认 planner target、surface opening 坐标帧、release opening、
   真实物体位置一致。

如果 online 失败，优先分辨：

- surface 错：回到 grounding；
- surface 对但 geometry 尺寸错：修改 geometry；
- geometry 对但释放前偏差大：转 place；
- pick 后物体姿态不对：转 grasp；
- 没触发或触发晚：转 repair。

## 10. Evidence 写法

正文建议包含以下内容：

```markdown
## Geometry Diagnosis

- Expected semantic surface: ...
- Compiled surface before this skill: ...
- Planner failure: unknown surface / 0-of-N / collision / pos_err / release guard
- Source geometry: ...
- Coordinate frame: planner_frame / world, and why it is safe
- Proposed virtual surface / proxy: ...
- Numerical parameters: ...

## Boundary

- Paired grounding skill: ...
- This skill only contributes geometry.
- It does not change trigger / grounding / grasp / place.

## Validation

- Static gate: ...
- Canary: ...
- Problem scan: ...
- Online validation: ...
```

## 11. 反模式

不要这样写：

- 在 geometry 里重写目标语义；
- 在 geometry 里写 `grasp_profile`；
- 没有 BDDL / problem 证据就写固定绝对 bounds；
- 大范围 exclude collision；
- 把 release guard 放宽当作 geometry 修复；
- 一个通用 container skill 覆盖 drawer、shelf、basket、caddy、microwave；
- 只看中心点，不看 held object footprint；
- 把 world-frame site / bounds 混进 planner-frame problem；
- 一次同时改 bounds、z、collision、yaw、place alignment。

geometry skill 的价值在于让 planner world 更接近任务需要的真实几何。它应该小、准、可解释。
