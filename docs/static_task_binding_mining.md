# 静态 Task-Binding Mining 流程

## 1. 目标

语言绑定是一个静态问题：

```text
task language + episode 初始 MuJoCo scene
    -> target / goal / relation / optional goal site
```

这些信息在 episode reset 后已经存在，不需要等待 VLA 失败，也不需要执行动作。因此，已经做过动态 mining 的任务不应为了语言绑定再完整运行 episode。

本流程把语言绑定从原有的动态 recovery mining 中分离出来：

```text
静态 task-binding lane                     动态 recovery lane
------------------------------------       ------------------------------
语言、对象、site、初始空间关系              抓取、碰撞、掉落、轨迹、执行失败
每个 Task reset 一次                       必须运行 episode
无 policy inference                        需要 policy/controller
离线生成 binding skills                    生成 trigger/repair skills
```

## 2. 总流程

```text
每个 Task reset + set_init_state(0) 一次
                    │
                    ▼
      读取初始 MuJoCo SceneState
                    │
                    ▼
  导出 compact task-binding context JSON
                    │
                    ▼
     按 fingerprint 缓存，后续直接复用
                    │
                    ▼
  [后续阶段] 批量交给大模型归纳 binding skill
                    │
                    ▼
  [后续阶段] 使用缓存 JSON 做离线 admission
                    │
                    ▼
  [后续阶段] 每类新 skill 只做少量在线 canary
```

当前代码已经实现“采集并缓存 context”、`task_binding` skill/profile schema、缓存 context
离线重放校验，以及 `language_mujoco` 运行时解析。暂不调用大模型，也不预置任何 mined
binding skill；实际 skill 仍由后续离线 mining 生成。

## 3. 数据边界

### 3.1 允许使用

- 任务语言；
- reset 后的 MuJoCo object/body/link/site/joint；
- 对象初始位姿；
- MuJoCo geom 的类型、尺寸和位姿；
- 从上述信息计算的几何代理；
- 当前 `language_mujoco` binder 的解析结果、候选和失败原因。

### 3.2 禁止使用

- BDDL `(:goal)`；
- BDDL `(:obj_of_interest)`；
- BDDL `(:regions)`；
- BDDL `(:init)` atoms；
- 从上述字段复制出来的 target、goal、region 或标准答案。

LIBERO 仍然可以使用 BDDL 文件创建模拟环境。这只是 simulator bootstrap；collector 不打开或解析其中的 goal/init/region。对于 `*_task` language 轴，若命令行明确或 `auto` 选择 BDDL `(:language)`，只允许读取语言句子，不能连带读取其他 section。

## 4. 当前采集器

入口：

```text
scripts/recovery/skill_pipeline/collect_task_binding_contexts.py
```

核心数据构造：

```text
experiments/robot/libero/skill_pipeline/task_binding_context.py
```

普通 LIBERO suite 示例：

```bash
python scripts/recovery/skill_pipeline/collect_task_binding_contexts.py \
  --task_suite_name libero_goal_task \
  --out_dir artifacts/task_binding/libero_goal_task
```

生成 benchmark 示例：

```bash
python scripts/recovery/skill_pipeline/collect_task_binding_contexts.py \
  --generated_benchmark_dir benchmarks/libero90_generated_v1_envfiltered_304 \
  --generated_split all \
  --out_dir artifacts/task_binding/generated_v1
```

调试时只采集少量任务：

```bash
python scripts/recovery/skill_pipeline/collect_task_binding_contexts.py \
  --task_suite_name libero_goal_task \
  --task_ids 1,2,3 \
  --out_dir artifacts/task_binding/debug
```

默认行为：

- 每个 Task 只使用 `init_state_index=0`；
- policy rollout steps 恒为 `0`；
- 已存在的 `contexts/<task>.json` 直接复用；
- `--refresh` 才重新 reset 和覆盖；
- 一个 Task 采集失败时保留其他成功结果，最终返回非零退出码；
- `--limit N` 只用于调试，不改变 Task 的排序。

## 5. 输出结构

```text
<out_dir>/
  contexts/
    task01.json
    task02.json
  index.jsonl
  summary.json
```

每个 context 的主要字段：

```json
{
  "schema_version": 1,
  "collector_version": "task_binding_context_v1",
  "task": {
    "source_suite": "libero_goal_task",
    "source_task_id_1based": 2
  },
  "language": "put the plate on the stove",
  "language_source": "bddl",
  "seed": 0,
  "init_state_index": 0,
  "input_contract": {
    "used": ["task_language", "initial_mujoco_scene"],
    "forbidden": [
      "bddl_goal",
      "bddl_obj_of_interest",
      "bddl_regions",
      "bddl_init_atoms"
    ],
    "policy_rollout_steps": 0
  },
  "scene": {
    "objects": [],
    "articulated_joints": [],
    "table_geometry": {}
  },
  "binding": {
    "target": "plate_1_main",
    "goal": null,
    "failure_reason": "language_goal_region_unsupported",
    "binding_evidence": {
      "goal_region_sites": ["flat_stove_1_cook_region"]
    }
  },
  "task_fingerprint": "...",
  "snapshot_fingerprint": "..."
}
```

为控制体积，collector 不保存 mesh vertices/faces、完整 contact table、相机图像、robot joint debug、policy output 或 recovery trace。

### 5.1 两种 fingerprint

`task_fingerprint` 包含规范化语言、object name/family/category/affordance、site 名称、geom name/shape/size、articulated joint 名称和 collector version。它不包含对象当前 pose，因此同一个 Task 换初始位置时通常不变。

`snapshot_fingerprint` 额外包含 object pose 和 joint value，用来区分具体初始快照。

已有 context 默认按文件存在直接缓存，不启动环境。fingerprint 用于后续离线去重、审计和重新 mining；当 MuJoCo model、语言或 collector 版本发生变化时，使用 `--refresh` 重新采集。

## 6. 后续大模型 Mining 的输入与输出

后续 miner 应一次读取多个 Task 的 context，而不是逐 Task 生成答案。输入至少包括 context JSON、当前 task-binding skill 库、binder 支持范围和 admission 规则。

模型的任务是聚类和归纳：

```text
多个 plate-on-stove failure
  + scene 中均存在 *_cook_region
  -> 一个 stove cook-region binding profile
```

而不是：

```text
task02 -> plate_1_main -> flat_stove_1_cook_region
```

未来 skill 应描述选择规则：

```yaml
scope: task_binding
applies_to:
  all:
    - task_language_matches: "plate.*stove|stove.*plate"
    - scene_site_matches: "*stove*_cook_region"
recovery_hints:
  params:
    task_binding_profile: stove_cook_region_v1
```

profile 再描述 target selector、goal selector、relation 和 site selector。具体 object instance、site 实例和坐标必须在 episode reset 后从当前 MuJoCo scene 动态解析。

当前可执行格式使用 Markdown skill 加独立 profile registry。skill pack 的
`skills/_index.yaml` 增加：

```yaml
task_binding_profile_registry: ../profiles/task_binding.yaml
task_binding:
  - task_binding/stove_cook_region.md

# mining draft 可先放这里；只有 --enable_mining_skills 会加载：
task_binding_fail_only: []
```

skill front matter 示例：

```yaml
---
id: stove_cook_region_binding
kind: task_binding
scope: task_binding
priority: 100
applies_to:
  all:
    - task_language_matches: "plate.*stove|stove.*plate"
    - scene_site_matches: ".*stove.*cook_region$"
task_binding_profile: stove_cook_region_v1
---
```

`profiles/task_binding.yaml` 示例：

```yaml
schema_version: 1
profiles:
  stove_cook_region_v1:
    target_selector:
      source: language
    goal_selector:
      source: scene
      category_matches: "^flat_stove$"
    relation: "on"
    goal_site_selector:
      name_matches: ".*_cook_region$"
      required: true
```

`source: language` 使用通用 binder 已解析出的语言实体和空间选择条件；`source: scene`
必须提供 category/name matcher。所有 selector 都要求在当前 reset 场景中唯一解析，零个或多个
候选都会显式失败。

## 7. 未来离线 Admission

生成 skill 后，先在缓存 context 上验证，不跑 episode：

1. language matcher 是否命中预期任务；
2. 是否错误命中无关任务；
3. target/goal selector 是否各自唯一；
4. 要求的 site/link/joint 是否真实存在；
5. 是否能生成受支持的 `goal_atoms`；
6. 多个 skill 是否产生冲突；
7. skill 是否包含 Task ID、seed、绝对 XYZ 或具体实例答案；
8. skill/profile 是否引用任何禁止的 BDDL goal 字段。

只有离线 admission 通过的新 skill family 才需要在线 canary。在线 canary 的目的只是确认真实 runtime plumbing，不重新做 mining。

当前离线重放入口：

```text
python scripts/recovery/skill_pipeline/validate_task_binding_skills.py \
  --skill-index <skill_pack>/skills/_index.yaml \
  --contexts <cached_context_dir> \
  --mining \
  --report <report.json>
```

校验器会报告每条 context 的 bound/unmatched/failed、skill 命中次数、选择出的 target/goal/
relation，以及冲突或非唯一选择。存在失败、冲突，或某个候选 skill 在语料中从未命中时，命令
返回失败。unmatched context 允许由通用 binder 继续处理，不会被视为 admission 失败。

运行时仅在 `--task_goal_source language_mujoco` 且启用对应 skill pack 时加载 binding skill。
唯一 skill 命中时优先于通用 binder；没有命中时回退通用 binder；多个 skill 产生不同绑定，
或 selector 不能唯一解析时直接失败并关闭该 episode 的 goal-dependent recovery，不回退猜测。

## 8. 一次 reset 的适用边界

一次 reset 足够发现稳定的场景拓扑：object family、fixture 类型、site/link/joint 名称、geom 类型/尺寸和可用的 region primitive。

空间选择词仍必须在运行时动态计算：

```text
next to / between / left / right / table center
```

mining skill 只能保存 selector，不得保存第一次 snapshot 中的具体实例编号。因此，一次 reset 不意味着把 `bowl_1` 固定到所有 episode；它只是帮助模型发现“应使用 next-to selector”。

若某类 skill 对初始状态变化特别敏感，可以在 admission 阶段额外采集少量 snapshot，但不需要运行完整 episode，也不改变默认的“一 Task 一次”采集策略。

## 9. 与现有 Mining 的关系

静态 lane 只负责语言句型、target/goal grounding、fixture site/region 选择和 task-binding profile。

原动态 lane 继续负责 trigger、grasp、collision、trajectory、object drop 和 controller/planner execution failure。

两条 lane 最终可以写入同一个 skill pack，但证据来源和 admission 规则不同，不能把静态 context 当成动作执行成功的证据。
