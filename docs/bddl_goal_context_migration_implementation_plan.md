# 用 Language + MuJoCo 替换 BDDL 目标信息：最小实施方案

日期：2026-09-16

状态：实施方案，尚未修改代码。

目标分支：`feature/bddl-language-and-goal`

## 1. 核心思路

本次工作只做一件事：

> 保持 recovery 后半段完全不变，把原来由 BDDL 提供的 target、goal、goal atoms 和目标区域，改成由任务语言和 MuJoCo 场景提供。

当前链路：

```text
BDDL
  -> target / goal / goal_atoms / goal_surfaces / regions
  -> ParsedTask
  -> qstate / matcher / grounding / cuTAMP
```

改造后：

```text
language + MuJoCo scene
  -> target / goal / goal_atoms / goal_surfaces / regions
  -> ParsedTask
  -> qstate / matcher / grounding / cuTAMP
```

`ParsedTask` 之后的代码尽量不改。此次不新建复杂的目标系统，不重写 matcher、grounding、geometry 或 cuTAMP。

BDDL 仍可用于：

- LIBERO 环境加载；
- 初始状态构造；
- 官方成功判断；
- 旧模式对照。

但新模式的 recovery 不再读取 BDDL 的 `(:goal)`、`obj_of_interest`、`(:regions)` 和 `(:init)` 来决定目标。

## 2. 最终只保留两个模式

runner 增加一个参数：

```text
--task_goal_source bddl
--task_goal_source language_mujoco
```

含义：

- `bddl`：保持当前行为，用于复现旧结果；
- `language_mujoco`：使用语言确定任务语义，使用 MuJoCo 场景确定具体对象和几何。

默认值在迁移期间保持 `bddl`。新模式验证完成后，再决定是否调整默认值。

## 3. 第一步：提取统一的目标解析入口

当前 `task_parser.py::parse_task()` 先解析语言，随后通过 `load_bddl_hints()` 用 BDDL 覆盖 target 和 goal。

将这部分改成一个简单的来源开关：

```python
def parse_task(
    language,
    object_names,
    *,
    scene=None,
    env=None,
    task_goal_source="bddl",
):
    if task_goal_source == "bddl":
        hints = load_bddl_hints(object_names, env=env)
    elif task_goal_source == "language_mujoco":
        hints = resolve_language_mujoco_hints(language, scene)
    else:
        raise ValueError(task_goal_source)

    return build_parsed_task(language, hints)
```

两种来源返回相同形状的数据：

```python
{
    "target": "akita_black_bowl_2_main",
    "goal": "plate_1_main",
    "goal_atoms": [
        {"predicate": "on", "args": ["akita_black_bowl_2_main", "plate_1_main"]}
    ],
    "goal_surfaces": ["plate_1_main"],
    "regions": {},
    "source": "language_mujoco",
}
```

这样 runner、matcher 和 cuTAMP 仍然使用当前字段，不需要整体重构。

建议新增文件：

```text
experiments/robot/libero/tiptop_repro/language_mujoco_goals.py
```

其中只实现：

```python
resolve_language_mujoco_hints(language, scene) -> dict
```

## 4. 第二步：从语言得到任务语义

第一版只覆盖当前 LIBERO-Pro 中实际需要的句型，不做通用自然语言系统。

例如：

```text
Pick the akita black bowl next to the plate and place it on the plate
```

语言解析结果：

```python
{
    "target_type": "akita_black_bowl",
    "target_selector": {
        "relation": "next_to",
        "reference_type": "plate",
    },
    "goal_type": "plate",
    "goal_relation": "on",
}
```

第一版需要支持的内容：

- `pick X and place it on Y`；
- `put X in Y`；
- 对象类别，例如 bowl、plate、wine bottle、cream cheese；
- 目标关系 `on`、`inside`；
- 源对象限定 `next to`、`on`、`inside`、`between`、`not between`；
- `on top of the cabinet` 等已有任务需要的表达。

实现可以使用明确的规则和正则，不需要增加 parser skill mining 框架。

如果句型不支持，返回空结果并记录：

```text
language_goal_parse_failed
```

不得回退到 BDDL target。

## 5. 第三步：用 MuJoCo 场景绑定具体对象

语言只告诉系统“哪个类别、满足什么关系”，具体实例由 `read_scene()` 得到的 MuJoCo 场景决定。

例如场景里有：

```text
akita_black_bowl_1_main
akita_black_bowl_2_main
plate_1_main
```

语言说 `black bowl next to the plate`，则：

1. 找到所有 black bowl；
2. 找到 plate；
3. 根据 MuJoCo 中的 XY 位置计算每个 bowl 到 plate 的距离；
4. 选择符合 `next_to` 的 bowl；
5. 得到 `akita_black_bowl_2_main`。

关系由场景状态计算：

- `next_to(A, B)`：XY 距离；
- `on(A, B)`：XY 投影和 Z 高度；
- `inside(A, B)`：物体中心是否位于容器范围；
- `between(A, B, C)`：A 到 BC 线段的距离和投影位置；
- `not between`：上述条件的否定。

第一版不要求关系判断覆盖所有任务，只覆盖当前要评测的任务。

如果存在多个无法区分的候选，不随便选择，也不读取 BDDL；记录：

```text
language_goal_binding_ambiguous
```

对于带有 `next to`、`on`、`between` 等初始位置描述的任务，最好在 episode reset 后、Pi0 第一次动作前完成一次绑定，并在该 episode 内保留这个 target 名字。实现上只需要在 episode 状态里缓存 `ParsedTask`，不需要引入新的大型数据结构。

## 6. 第四步：生成和当前相同的 goal atoms

完成对象绑定后，直接生成当前 cuTAMP 已经支持的 atom 格式。

例一：

```text
place the bowl on the plate
```

生成：

```python
{"predicate": "on", "args": [bowl_name, plate_name]}
```

例二：

```text
put the wine bottle in the bowl
```

生成：

```python
{"predicate": "inside", "args": [wine_bottle_name, bowl_name]}
```

`goal_surfaces` 继续由 placement atom 的第二个参数产生。

`handempty()`、grounding 改写、surface 注册、fluent mapping 和 cuTAMP 求解继续沿用现有代码，不在本次修改。

由于返回格式和 BDDL hints 相同，`build_recovery_goal_candidates()` 可以继续工作。最多只需将候选名称中的 `bddl_required` 改成中性的 `required`；这不是首轮必须项。

## 7. 第五步：目标区域从语言和 MuJoCo 获得

目标是普通物体时，直接使用该物体的 MuJoCo 名称和几何。

目标是 cook region、rack top 或 cabinet top 时：

1. 语言确定目标类型，例如 stove、wine rack、cabinet top；
2. pack 中现有 grounding profile 确定要使用的 region/site 类型；
3. 从 MuJoCo scene object 或 site 读取位置和尺寸；
4. 按现有 geometry profile 的 margin、height 和 thickness 规则构造 surface。

例如：

```text
place the plate on the stove
```

可以继续由现有 profile 将粗目标：

```text
on(plate_1_main, flat_stove_1_main)
```

改写为：

```text
on(plate_1_main, flat_stove_1_cook_region)
```

然后从 MuJoCo site `flat_stove_1_cook_region` 读取几何。

新模式不得使用：

- BDDL goal surface 来选择 region；
- BDDL `(:regions)` 的 ranges；
- BDDL `(:init)` 来对齐 region。

若 MuJoCo 中没有需要的 site，则记录明确失败，不回退到 BDDL region。

## 8. 第六步：让 runner 和 controller 使用同一种来源

需要修改两个主要调用点：

1. `skill_pipeline/runner.py::_query_state()`；
2. `tiptop_repro/cutamp_controller_v2.py::perceive()`。

两处都必须传入相同的 `task_goal_source`。

最简单的做法是：

- episode reset 后调用一次 `parse_task()`；
- 保存得到的 `ParsedTask`；
- `_query_state()` 和 controller 都接收这个 `ParsedTask`；
- controller 不再自己执行 `parse_task(..., env=env)`。

示意：

```python
parsed_task = parse_task(
    task_description,
    initial_scene.objects.keys(),
    scene=initial_scene,
    env=env,
    task_goal_source=args.task_goal_source,
)

qstate = _query_state(env, obs, parsed_task)
controller.recover(env, obs, parsed_task)
```

这能避免 runner 使用语言目标，而 controller 又重新从 BDDL 读答案。

## 9. 第七步：保留字段形状，增加真实来源标记

为了减少改动，第一版可以继续保存现有字段：

```text
bddl_goal_atoms
bddl_goal_surfaces
bddl_regions
```

但必须同时增加：

```text
task_goal_source: bddl | language_mujoco
```

更稳妥的轻量改法是同时增加中性别名：

```text
goal_atoms
goal_surfaces
goal_regions
```

下游优先读取中性字段，没有时再读取旧字段。这样不用一次性修改所有旧 pack，也不会把 language 数据误说成来自 BDDL。

不需要在这一阶段删除所有旧字段；等新模式稳定后再清理。

## 10. 第八步：只做必要测试

本次不需要建立庞大的新评测框架，只需三类测试。

### 10.1 旧模式回归

`--task_goal_source bddl` 下验证：

- target 和 goal 不变；
- skill winner 不变；
- recovery goal atoms 不变；
- cuTAMP selected goal 不变。

### 10.2 新模式目标检查

选择当前重点任务，逐个检查：

- 语言解析出的类别和关系；
- MuJoCo 绑定出的 target/goal；
- 生成的 goal atoms；
- grounding 后的 surface。

### 10.3 防 BDDL 回退检查

在 `language_mujoco` 模式下：

- 改变或屏蔽 BDDL goal；
- 保持语言和 MuJoCo scene 不变；
- target、goal 和 goal atoms 应保持不变。

同时搜索运行日志，确认没有出现：

```text
target_source=bddl
goal_source=bddl
```

如果为兼容仍保留 `bddl_required` 候选名称，则必须通过 `task_goal_source` 确认实际数据来自 language；后续再改名。

## 11. 失败时的简单规则

新模式只需要遵守以下规则：

1. 语言解析失败：本次不启用依赖目标的 recovery。
2. MuJoCo 中找不到目标：本次不启用 recovery。
3. 多个候选无法区分：本次不启用 recovery。
4. 找不到目标 surface/site：记录失败，不读取 BDDL region。
5. 所有失败都允许原 Pi0 继续执行。

不需要设计复杂的多级错误系统，但日志必须说明失败发生在语言解析、对象绑定还是 surface 构造。

## 12. 推荐代码修改顺序

按以下顺序实施即可：

1. 同步当前 mining 分支，运行现有测试。
2. 新增 `--task_goal_source`，默认 `bddl`。
3. 新增 `resolve_language_mujoco_hints()`。
4. 修改 `parse_task()`，根据来源选择 BDDL 或 language + MuJoCo。
5. episode 开始时缓存一次 `ParsedTask`。
6. runner 和 controller 共用缓存的 `ParsedTask`。
7. 禁用新模式中的 BDDL region/init 回退。
8. 增加少量解析、绑定和防回退测试。
9. 使用固定 task/seed 对比两个模式的成功率。

整个改造的主要代码修改应集中在：

```text
experiments/robot/libero/tiptop_repro/task_parser.py
experiments/robot/libero/tiptop_repro/language_mujoco_goals.py
experiments/robot/libero/skill_pipeline/runner.py
experiments/robot/libero/tiptop_repro/cutamp_controller_v2.py
```

grounding/geometry adapter 只在发现仍读取 BDDL goal/region 时做小范围修改。

## 13. 完成标准

满足以下条件即可认为第一版完成：

1. `bddl` 模式仍能复现旧行为。
2. `language_mujoco` 模式不读取 BDDL goal、interest、regions 和 init。
3. runner 和 controller 使用同一个 `ParsedTask`。
4. target、goal 和 goal atoms 来自语言与 MuJoCo scene。
5. 现有 matcher、grounding 和 cuTAMP 主逻辑没有被重写。
6. 解析或绑定失败时不回退 BDDL。
7. 能在固定任务上完成两种模式的配对 rollout。

一句话总结：

> 新增一个 `language + MuJoCo -> BDDL hints 同形数据` 的替代函数，然后让整个 episode 共用它产生的 `ParsedTask`；除此之外，现有 recovery 流程尽量不动。
