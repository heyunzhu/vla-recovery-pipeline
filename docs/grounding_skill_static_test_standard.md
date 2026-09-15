# Grounding Skill Static Test Standard

更新日期：2026-09-09

本文定义 `grounding` recovery hint 的静态测试标准。它面向 harness / CI 使用，用来防止
Codex 在 mining loop 中写出目标绑定过宽、BDDL region 误用、和 geometry / place /
grasp 职责混在一起的 skill。

本文只约束 active skill pack 下的：

```text
skill_packs/<pack>/skills/pair/recovery_hint/grounding/*.md
```

`grounding` 不决定是否进入 recovery。它只在某个 repair / trigger 已经决定进入
recovery 后，回答 recovery 应该把任务语言中的目标区域、支撑物或容器绑定到哪个
planner 语义对象。

## 1. 核心契约

`grounding` skill 只回答一个问题：

> 当前 recovery 的目标语义应该绑定到哪个 surface / region / support object？

因此静态测试检查五层契约：

1. **Catalog 契约**：在线 grounding skill 必须显式出现在 active pack 的
   `skills/_index.yaml`。
2. **Schema 契约**：必须是 `kind: recovery_hint`、`scope: grounding`，不能声明
   `trigger`、`hook` 或 `backend`。
3. **语义锚点契约**：必须用 BDDL goal surface、goal name、region name 或目标类别
   锚定，不能只靠一句 task language。
4. **职责边界契约**：已入库 skill 优先只引用 `grounding_profile`；草稿期才允许临时输出
   `grounding_hints`，不能顺手修改 geometry、grasp 或 executor。
5. **配套契约**：如果 grounding 指向虚拟 region 或 movable support，必须有对应
   geometry skill 或代码路径能创建 planner surface；需要代码映射时必须走当前 skill pack
   的 grounding adapter。

## 2. 当前 Online Grounding Skills

`libero90_legacy` pack 当前有 9 个 online grounding skill：

| skill | 语义类型 | 作用 |
| --- | --- | --- |
| `plate_side_region_grounding.md` | BDDL table region | plate 左/右侧 region，避免误绑定成放到 plate 上。 |
| `desk_caddy_side_region_grounding.md` | BDDL table region | caddy 左/右侧 region，适用于 mug/cup 放在 caddy 旁边。 |
| `desk_caddy_compartment_grounding.md` | container compartment | book 放进 desk caddy 的 front/back/left/right compartment。 |
| `task35_mug_front_region_grounding.md` | fixed table region | task35 中 yellow-white mug 放到 white mug 前方。 |
| `task38_plate_right_region_grounding.md` | fixed table region | task38 中 white bowl 放到 plate 右侧。 |
| `cabinet_top_support_grounding.md` | top support | cabinet top support，避免绑定到 drawer / door / handle。 |
| `top_drawer_container_grounding.md` | drawer container | cabinet top drawer 内部容器。 |
| `shelf_support_grounding.md` | shelf support | two-layer shelf support surface。 |
| `bowl_stack_support_grounding.md` | movable support | bowl-on-bowl stack，把第二个 bowl 当 support object。 |

这些 skill 的共同点是：它们都只引用 `recovery_hints.params.grounding_profile`。具体
`grounding_hints` 参数放在 `profiles/grounding.yaml` 中，profile 到主流程 primitive 的映射
放在当前 skill pack 的 `code/grounding_profiles.py` 中。真正的 surface 尺寸、region bounds、
collision proxy、place yaw、drop budget 应由 geometry 或 place skill 处理。

## 3. Catalog 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | active pack `skills/_index.yaml` 中引用的 grounding skill 文件不存在。 |
| ERROR | active pack `skills/pair/recovery_hint/grounding/` 下存在未 online 且没有 `status: draft/retired/archived/experimental` 的 `.md` 文件。 |
| ERROR | online grounding skill 标记为 `status: draft/retired/archived/experimental`。 |
| ERROR | online grounding skill 的 `id` 与文件名语义冲突。 |
| WARN | 文件正文没有解释它和配套 geometry / place skill 的边界。 |

文件存在不等于 online 生效。静态 gate 必须把孤儿文件、退役文件和未登记文件显式列出，
否则 mining loop 容易把“仓库里有这份 skill”误解成“线上真的使用了这份 skill”。

## 4. Schema 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | `kind` 必须是 `recovery_hint`。 |
| ERROR | `scope` 必须是 `grounding`。 |
| ERROR | 不得声明 `trigger`、`hook`、`backend`。 |
| ERROR | 必须有 `recovery_hints.params.grounding_profile` 或 `recovery_hints.params.grounding_hints`。 |
| ERROR | 已入库 online skill 直接内联 `grounding_hints`，且没有明确处于 draft / profile-authoring 状态。 |
| ERROR | 使用 `grounding_profile` 时，profile 必须存在于当前 skill pack 的 `profiles/grounding.yaml` 且已在 capability registry 注册。 |
| ERROR | 需要 benchmark-specific 代码的 `grounding_profile` 必须由当前 skill pack 的 `code/grounding_profiles.py` 暴露并映射到通用 planner primitive。 |
| ERROR | 使用 `grounding_hints` 时，必须至少包含 `placement_surface` 或 `support_object` 之一。 |
| ERROR | 不得出现 `recovery_hints.grasp_profile`。 |
| ERROR | 不得出现 `geometry_hints`、`placement_region`、`executor`、`place_*`、`grasp_*` 等跨职责字段。 |
| WARN | `recovery_point` 不是 “After a repair/trigger skill has already decided to call recovery.” 或等价表述。 |
| WARN | `when_not_to_apply` 缺少明确反例。 |

`grounding` skill 不应该直接影响动作执行。它只是让后续 goal compilation 选对语义目标。

## 5. Hint Vocabulary / Primitive 检查

当前代码主要消费两类 grounding hint。

hint 可以使用 pack-local intent 名称，但必须通过 active pack 的
`code/grounding_profiles.py` 归一化到主引擎支持的 generic planner primitive。generic primitive
的单一来源是 `experiments/robot/libero/tiptop_repro/engine_capabilities.py`。

### 5.1 `placement_surface`

`placement_surface` 表示目标应该绑定到哪个放置 surface / region。

允许的 `intent`：

| intent | 用途 |
| --- | --- |
| `bddl_table_region` | 从 BDDL goal surface 保留 table 上的 left/right/front/back region。 |
| `fixed_table_region` | 固定 task 的虚拟 table region，例如 task35 / task38。 |
| `top_support` | cabinet top 这类顶部支撑面。 |
| `shelf_support` | shelf support surface。 |
| `drawer_container` | drawer 内部容器目标。 |
| `container_compartment` | desk caddy front/back/left/right compartment。 |

常用字段：

| 字段 | 要求 |
| --- | --- |
| `relation` | 应与语义一致，常见为 `on` 或 `inside`。 |
| `region_name` | 只用于 task 特化固定 region。 |
| `region_name_from_bddl_goal` | BDDL 已给出 goal region 时优先使用。 |
| `bddl_goal_surface_matches` | 动态 region 必须提供。 |
| `region_name_matches` | container compartment 必须提供。 |
| `container_name_matches` | container compartment 建议提供。 |
| `prefer` / `avoid` / `fallback` | top support / shelf / drawer 这类实体 surface 选择建议提供。 |
| `rewrite_misgrounded_goals` | 只用于已观察到的误绑定源，例如 `plate_1_main` 或 `desk_caddy_1_main`。 |

静态 gate 应检查：

| 级别 | 检查项 |
| --- | --- |
| ERROR | hint 既没有可识别 `intent`，也没有显式 `planner_primitive`。 |
| ERROR | `intent` 未在 active pack 的 `capabilities.yaml` 注册。 |
| ERROR | adapter 归一化后仍无法得到 `table_region_surface`、`container_region_surface`、`preferred_support_surface`、`preferred_container_surface` 或 `movable_support_surface`。 |
| ERROR | 新 profile 需要 benchmark-specific adapter，但 active pack 没有暴露 `grounding_profile_adapter`。 |
| WARN | 依赖 legacy fallback 名称猜测，而不是显式 planner primitive。 |

### 5.2 `support_object`

`support_object` 表示目标 surface 是一个可移动物体，而不是 planner 默认 surface。

允许的 `intent`：

| intent | 用途 |
| --- | --- |
| `stack_support` | bowl-on-bowl stack，把第二个 bowl 注册为支撑对象。 |

常用字段：

| 字段 | 要求 |
| --- | --- |
| `object_class` | 必须存在，例如 `bowl`。 |
| `relation` | 常见为 `on`。 |
| `predicates` | 建议列出相关谓词，例如 `on`。 |

新增 grounding primitive 不是普通 skill 写作事项。如果当前五类 generic primitive 表达不了任务，
agent 应输出 blocker / engineering action，并说明缺少哪一种通用语义，而不是直接修改
`real_cutamp_adapter.py` 的分支表。

## 6. Scope / Anchor 检查

`grounding` 的最大风险是匹配范围过宽，把相似语言绑定到错误目标。

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `applies_to`。 |
| ERROR | `applies_to` 只包含 `task_language_matches`。 |
| ERROR | `target_name_matches` 是 `.*`、`.+` 这类过宽表达。 |
| ERROR | left/right/front/back region 缺少 `bddl_goal_surface_matches` 或固定 `region_name`。 |
| ERROR | container compartment 缺少 container / goal 锚点。 |
| ERROR | top support / shelf / drawer 缺少 `prefer` / `avoid` 或等价 surface 选择约束。 |
| WARN | `task_language_matches` 同时覆盖 “right of caddy” 和 “right compartment of caddy”，但没有 BDDL surface 区分。 |
| WARN | skill 名称是 task 特化，但 `applies_to` 没有足够 task 特化锚点。 |

推荐锚点组合：

| 任务形态 | 最低锚点 |
| --- | --- |
| plate 左/右侧 | task language + target type + BDDL plate-side region。 |
| caddy 左/右侧 | task language + mug/cup target + caddy goal + BDDL caddy-side region。 |
| caddy compartment | task language + book target + caddy goal + `*_contain_region`。 |
| cabinet top | task language + top-support prefer/avoid。 |
| top drawer | task language + drawer level + cabinet avoid/fallback。 |
| bowl stack | task language + target bowl + goal bowl。 |

## 7. Grounding / Geometry Pairing 检查

如果 grounding 选择的是虚拟 region，planner 通常还需要 geometry skill 创建可优化的 surface。
静态 gate 应维护配对表：

| grounding skill | 需要配套 geometry |
| --- | --- |
| `plate_side_region_grounding` | `plate_side_region_geometry` |
| `desk_caddy_side_region_grounding` | `desk_caddy_side_region_geometry` |
| `desk_caddy_compartment_grounding` | `desk_caddy_compartment_geometry` |
| `task35_mug_front_region_grounding` | `task35_mug_front_region_geometry` |
| `task38_plate_right_region_grounding` | `task38_plate_right_region_geometry` |
| `top_drawer_container_grounding` | `top_drawer_inner_floor_geometry` |
| `shelf_support_grounding` | `shelf_region_inner_floor_geometry` |
| `bowl_stack_support_grounding` | `bowl_stack_support_geometry` |

| 级别 | 检查项 |
| --- | --- |
| ERROR | grounding 使用虚拟 region，但没有任何 online geometry skill 覆盖同一 intent / region。 |
| ERROR | grounding 的 relation 与 geometry 的 relation 冲突，例如 grounding 是 `inside`，geometry 编译成不相关的 table region。 |
| ERROR | grounding 指向 `container_compartment`，但 geometry 固定写死单一 compartment。 |
| WARN | grounding 和 geometry 使用不同的 region name 来源，一个来自 BDDL，一个来自硬编码。 |
| WARN | grounding 的 `rewrite_misgrounded_goals` 会把多个实体重写到同一 region，需要人工确认。 |

`cabinet_top_support_grounding` 当前主要靠真实或规则生成的 top support 名称，不一定需要单独
geometry skill。但如果以后 top surface 是虚拟 proxy，也必须进入配对表。

## 8. Canary 匹配检查

静态 gate 应维护一批小型 canary state，离线调用 matcher，检查每个典型任务的 grounding
winner 是否符合预期。

| canary | 预期 grounding |
| --- | --- |
| chocolate pudding left of plate，BDDL surface 为 `*_table_plate_left_region` | `plate_side_region_grounding` |
| red mug right of caddy，BDDL surface 为 `*_desk_caddy_right_region` | `desk_caddy_side_region_grounding` |
| book in right compartment of caddy，BDDL surface 为 `*_right_contain_region` | `desk_caddy_compartment_grounding` |
| white bowl right of plate，BDDL surface 为 `kitchen_table_plate_right_region` | `task38_plate_right_region_grounding` |
| yellow-white mug front of white mug，BDDL surface 为 `kitchen_table_porcelain_mug_front_region` | `task35_mug_front_region_grounding` |
| ketchup in top drawer of cabinet | `top_drawer_container_grounding` |
| bowl on top of cabinet | `cabinet_top_support_grounding` |
| book on top of shelf | `shelf_support_grounding` |
| stack bowl on bowl | `bowl_stack_support_grounding` |

| 级别 | 检查项 |
| --- | --- |
| ERROR | canary 没有命中任何 grounding skill。 |
| ERROR | canary 命中错误 grounding skill。 |
| ERROR | book-in-caddy canary 被 `desk_caddy_side_region_grounding` 抢走。 |
| ERROR | caddy-side mug canary 被 `desk_caddy_compartment_grounding` 抢走。 |
| WARN | 多个 grounding skill 同时命中，且 priority 关系没有在文档中说明。 |

## 9. Trace Scan 检查

静态 gate 不重跑仿真，但应能用历史 trace 扫描“如果 recovery 在这里发生，会合并哪些
grounding hint”。

最低报告：

| 字段 | 含义 |
| --- | --- |
| `task_id` / `episode_idx` / `query_idx` | 匹配位置。 |
| `task_description` | 原始任务语言。 |
| `target_name` / `goal_name` | recovery 解析出的目标和语义 goal。 |
| `bddl_goal_surfaces` | BDDL 给出的候选 surface / region。 |
| `matched_grounding_hints` | 所有匹配的 grounding skill。 |
| `winning_placement_surface` | 最终合并后的 placement surface hint。 |
| `winning_support_object` | 最终合并后的 support object hint。 |
| `compiled_goal_surface` | `real_cutamp_adapter` 最后使用的 surface / proxy。 |
| `paired_geometry_hints` | 同次 recovery 是否也命中配套 geometry。 |
| `success` | episode 最终是否成功。 |

这个报告用于回答三个问题：

1. 新 grounding 是否抢走历史上成功的绑定？
2. 是否出现 grounding 命中但 geometry 没命中的断链？
3. 是否仍有误绑定源没有被 `rewrite_misgrounded_goals` 覆盖？

## 10. Evidence 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `evidence.tasks`。 |
| ERROR | 没有写明 observed wrong binding，例如原本绑定到 `plate_1_main` / `desk_caddy_1_main` / `microwave_1_main`。 |
| ERROR | fixed task region 没有写明 region name 来自哪一个 BDDL goal。 |
| WARN | 没有列出失败 run / episode。 |
| WARN | 没有说明配套 geometry skill。 |
| WARN | 没有说明不适用场景。 |

## 11. 建议 Harness 产物

当前 `run_skill_admission.py` 对 grounding 已执行 schema、capability registry 和 offline trigger
scan；专门的 grounding 类型静态 gate 仍是待补工具。后续可以新增：

```bash
python scripts/recovery/skill_pipeline/check_grounding_skills.py
```

建议输出：

- `grounding_static_gate_result.json`
- `grounding_static_gate_report.md`
- `grounding_canary_matches.csv`
- `grounding_trace_scan.csv`

默认只有 ERROR 失败。WARN 写入报告，留给人工确认。
