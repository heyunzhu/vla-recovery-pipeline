# BDDL 目标依赖、cuTAMP 输入链与语言目标迁移

日期：2026-09-14。

状态：代码核对与设计总结，尚未实施目标来源替换。本文不改变当前 pack、grounding 或正在运行的评测。

核对基准：本地 HEAD `1e3a31f83cd2b4f6586f1472f6f6f8bb1052713f`，以及当前工作树中的代码。本文描述的是静态调用关系和配置；某条可选路径是否在具体 episode 中执行，仍须查运行日志。主要 pack 为 `skill_packs/libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914`。

## 1. 问题与当前决定

当前 recovery 能从 BDDL 取得任务的正确对象和最终目标。这会帮助系统判断策略抓错了谁、选择哪条 skill，以及为 cuTAMP 构造恢复目标。因此，当前结果应当描述为带有 BDDL 目标信息的 recovery，不能据此宣称完整地从语言理解任务。

拟采用独立的语言目标解析组件，以离线 mining 学习解析 skill。在线输入只包含任务语言，输出结构化语义目标；BDDL 留在离线监督与官方评分侧。现有 grounding 的职责、profile 和几何构造方式尽量保留，通过最小兼容层接入预测目标。

三条决定：

1. 先做独立离线解析，再做 recovery 集成；不能把离线解析成功等同于端到端替换完成。
2. 保留可复现的 BDDL 模式，另设明确的语言模式。语言模式不得失败后偷偷回退到 BDDL 答案。
3. 先验证相同目标输入下 grounding 的行为等价，再验证语言预测误差对 episode 的影响。不要同时重写目标解析、grounding、geometry 和规划器。

解析器的详细方案见 [独立离线 mining 设计](task_goal_parser_skill_offline_mining_design.md)。本文补充当前依赖链与迁移边界。

## 2. BDDL 的不同内容不能混为一谈

| 内容 | 当前或合理用途 | 需要区分的风险 |
| --- | --- | --- |
| `(:language)` | 提供策略和 recovery 使用的任务指令 | 可以作为语言输入；不能用文件名替代扰动后的文件内语言 |
| `(:goal)` | 官方成功条件；当前还提供 recovery 目标 atoms 和目标对象 | 在线直接使用正确目标属于目标特权信息 |
| `obj_of_interest` | 当前在无法绑定 goal 时补充 target/goal | 也是任务相关提示，删掉 goal 读取后仍可能泄漏答案 |
| `(:regions)` | 描述区域名称、所属对象及范围；可选几何路径读取范围 | 指定哪个区域是正确目标，与读取一个已选表面的几何应分别审计 |
| `(:init)` | 环境初始化；可选路径用初始关系辅助区域坐标对齐 | 初始关系不能无条件当作 recovery 时刻的当前状态 |
| 文件路径、任务编号、文件名 | 环境加载、归档、样本标识 | 不能作为语言解析器检索正确实例或目标的输入 |

环境仍然需要任务定义来构造场景和判断成功。目标是隔离 agent 的决策输入，并非禁止模拟器和评测器读取 BDDL。

MuJoCo site 的位置和尺寸属于另一项场景信息依赖。去掉在线 BDDL goal 不等于实现纯视觉 grounding；保留模拟器几何时应如实声明。site 是否本身编码了任务特定的成功区域，也应另行审计，不能仅凭它来自 scene 就认定完全无特权。

## 3. 当前使用位置清单

本表仅列 agent 的语言输入、决策、恢复规划及离线回放中的依赖，不列环境构建、仿真任务生成和官方成功检查。规划器为决策构造表面几何的路径仍保留，因为这些数据会影响 recovery 动作。

以下路径均相对仓库根目录；函数名比行号更适合作为后续检索入口。

| 使用位置 | 怎样使用 | 对迁移的要求 |
| --- | --- | --- |
| `experiments/robot/libero/skill_pipeline/runner.py`：`bddl_language`、`apply_language_sources` | 提取 language，分别设置 policy 和 engine 的语言 | 保留指令读取；统一并记录双方实际语言 |
| `experiments/robot/libero/tiptop_repro/bddl_goals.py`：`load_bddl_hints` | 从显式文本、路径或 env 找到 BDDL，读取 language、goal、interest、init、regions | 语言模式不能借 env 再次读取答案 |
| 同文件：`resolve_bddl_target_and_goal` | 映射对象名，从 on/inside/holding 选 target/goal，失败时使用 interest | 必须一起替换 target、goal 和 interest 回退 |
| `tiptop_repro/task_parser.py`：`parse_task` | 先做语言/名称解析，随后用 BDDL 覆盖 target/goal，并存入 diagnostics | 仅换前半段 parser 不够；后半段会覆盖预测 |
| `skill_pipeline/runner.py`：`_query_state` | 用上述 target/goal 计算距离、holding、nearest-is-target、pick-target-status 等；导出 BDDL atoms/surfaces/regions | 触发特征也必须来自同一份预测目标 |
| `skill_pipeline/matcher.py`：`bddl_goal_surface_matches` | 直接匹配 qstate 中的 BDDL goal surfaces | 所有 trigger/recovery hint 的匹配输入都要纳入迁移 |
| `tiptop_repro/cutamp_controller_v2.py`：`CuTAMPV2OraclePerceiver.perceive` | recovery 内再次 `parse_task(..., env=env)` | runner 与 controller 必须共享目标来源，不能前者预测、后者取真值 |
| `tiptop_repro/task_semantics.py` 及其下游 | 接收已含 target/goal 的 parsed task 与场景语义 | 即便不直接搜索 BDDL 字符串，也可能继承上游真值 |
| `tiptop_repro/real_cutamp_adapter.py`：`build_recovery_goal_candidates` | 从 `bddl_goal_atoms` 直接生成 `bddl_required_*` 候选 | 语言模式必须由预测 final atoms 生成候选 |
| pack 的 `code/grounding_profiles.py` | 改写 placement surface；固定 region 缺失时可从 BDDL surfaces 选取 | 保留改写规则，替换动态目标来源；区分固定配置与回退 |
| pack 的 `code/geometry_profiles.py` | 固定 surface 缺失时也可从 BDDL atoms/surfaces 选名；按 scene site 构造表面 | 不因目标替换而误改位置、尺寸或坐标系 |
| `tiptop_repro/tamp_scene.py`、`real_cutamp_adapter.py` 的动态区域支持 | 可从 BDDL goal 选区域，从 regions 取范围，并用 init 辅助对齐 | 可选路径要显式禁用或提供独立、已声明的场景输入 |
| runner 的 query 日志、`skill_pipeline/bundles.py` | 保存 BDDL 派生字段，离线 bundle 可恢复这些匹配字段 | 旧离线扫描语料不是天然的 language-mode 语料 |

这里最容易漏掉的是间接依赖：即使某个 repair 只判断“抓错物体”，它判断所依据的 target 也可能已经被 BDDL 指定。移除 `bddl_goal_surface_matches` 并不能单独消除这类依赖。

## 4. 从 BDDL goal 到 cuTAMP 的完整变化

下面以一个示意放置目标说明。实例名用于展示现有表示，不代表语言解析器应输出这些名字。

### 4.1 读取与名字映射

BDDL 中的目标例如：

```lisp
(:goal (And (On akita_black_bowl_2 plate_1)))
```

`parse_bddl_task_goals` 提取 predicate/args；`resolve_bddl_target_and_goal` 再对场景对象名进行映射。映射会尝试原名、`_main` 后缀、唯一前缀匹配，柜顶还有 `_top_side` 的特殊映射。无法映射的 atom 参数可以保留原名，例如虚拟区域名。

示意结果：

```text
goal_atoms = [{predicate: on, args: [akita_black_bowl_2_main, plate_1_main]}]
target = akita_black_bowl_2_main
goal = plate_1_main
goal_surfaces = [plate_1_main]
```

这一步已经利用了正确实例身份，远多于从语言中提取“黑碗”和“盘子”两个类别。

### 4.2 覆盖 ParsedTask，并影响触发特征

`parse_task` 把 atoms/surfaces/init/regions 放入 `ParsedTask.diagnostics`，并在映射成功时覆盖 `target_hint`、`goal_hint`，记录 `target_source= bddl`、`goal_source= bddl`。

runner 以这份 target 计算目标到夹爪的距离、当前是否拿着目标、最近可抓物是否为目标等特征。匹配器还可直接读取 `bddl_goal_surfaces`。因此 BDDL 在进入规划器之前就能影响是否触发 recovery、哪条 skill 胜出。

### 4.3 构造恢复目标候选

`build_recovery_goal_candidates` 从 diagnostics 读取 BDDL placement atoms，仅将这里支持的 `on/inside` 分支加入 `bddl_placement`。随后调用 grounding 改写，检查物体存在、surface 已知或可虚拟化，并生成候选：

```text
candidate.name = bddl_required_...
candidate.atoms = [on(black_bowl, plate), handempty()]
candidate.surface_names = [plate]
```

`handempty()` 是 recovery 构造候选时添加的约束，不是上述 BDDL 原文自带的内容。

这不是对任意 BDDL 逻辑的无损编译。这里按放置 atom 构造候选；完整任务中的多目标、否定、关节状态等不能假定已全部传给 cuTAMP。系统还可以产生语义/LLM 和规则候选，候选会去重并逐个尝试。不能仅因存在 `bddl_required_*` 就断言它一定是实际选中的候选，应记录 selected goal。

### 4.4 Grounding 改写与几何实体构造

grounding 将粗目标绑定到合适的具体 surface。例如当前灶台 profile 将：

```text
on(plate_1_main, flat_stove_1_main)
                 ↓ grounding
on(plate_1_main, flat_stove_1_cook_region)
```

它修改的是目标参数。随后 geometry 将 cook region 变成有位置、尺寸、支撑高度的规划表面，加入 TAMPProblem 的 surfaces。二者是不同职责，详见第 5 节。

### 4.5 构造 TAMPProblem

`RealCuTAMPRecoveryPlanner.plan` 对每个候选调用 `build_tamp_problem`，传入：

```text
goal_atoms_override = candidate.atoms
required_final_atoms = candidate.atoms 的字典表示
surface_names = candidate.surface_names
init_atoms = 当前 graph.world_atoms 与 recovery.atoms 的合并
recovery_hints = 展开的 skill/profile 参数
```

注意这里的规划初始 atoms 来自当前场景图和 recovery 状态，不能因为参数叫 `init_atoms` 就认为它直接等于 BDDL `(:init)`。BDDL init 的区域对齐用途是另一条路径。

`build_tamp_problem` 同时组织 movables/surfaces/statics、虚拟表面、抓取和放置候选、机器人当前关节状态等。BDDL goal 本身没有给出完整运动轨迹，也没有解决碰撞和可达性。

### 4.6 映射成 cuTAMP 原生 fluents

`map_atoms_to_cutamp(required_final_atoms or goal_atoms)` 产生 `fluent_mapping['goal']`。例如：

```text
on(bowl, plate) → on(bowl, plate)
handempty()     → handempty()
inside(x, y)    → on(x, y)，标记 approximated
```

`inside` 的包含语义需要结合容器 surface/geometry 表示；单纯改名为 `on` 不保证真实包含。其它不支持的谓词可能仅保留在语义/几何层，或记录 ignored/skipped diagnostics。必须保存这些诊断，不能把“规划器可行”当成“完整官方 goal 已满足”。

### 4.7 后端绑定并交给求解器

`real_cutamp_backend.py` 读取 `problem.fluent_mapping['goal']['fluents']`，映射/清理对象名字，通过 `fluent.ground(*args)` 生成原生 fluent 实例，最后构造：

```text
TAMPEnvironment(
    movables=...,
    statics=...,
    type_to_objects={Movable: ..., Surface: ...},
    goal_state=frozenset(goal_state),
)
```

再由 `run_cutamp` 使用这个环境、规划配置和当前机器人状态等求解。未知 fluent 或绑定失败会留下 goal notes；同时请求 Holding 和 HandEmpty 时后端会丢弃 HandEmpty。这些也是原始目标到实际求解约束之间的变化。

可概括为：

```text
BDDL goal
  → atoms + 具体实例映射
  → ParsedTask + 触发特征
  → 恢复候选 atoms + handempty
  → grounding 改写 surface
  → TAMPProblem + surface 几何
  → 原生 fluent 映射（可能近似/跳过）
  → TAMPEnvironment.goal_state
  → cuTAMP 搜索与运动求解
```

## 5. Grounding 要保留什么，BDDL 在哪里介入

### 5.1 当前 pack 的正常路径

当前 `profiles/grounding.yaml` 的灶台和酒架 profile 都配置了固定 `region_name`。`code/grounding_profiles.py::_region_name` 先返回固定名字；只有固定名字缺失才搜索 BDDL surfaces。酒架 `_task_matches` 还存在读取 BDDL surfaces 的匹配逻辑。

`rewrite_placement_atom` 负责把粗物体目标改成 cook/top region。`is_known_or_virtual_surface` 声明这个名字是可接受的虚拟 surface。

配套 `profiles/geometry.yaml` 也有固定区域和 `source_site_name`。`code/geometry_profiles.py::resolve_surface_descriptor` 找到 scene object/site，读取位置与尺寸，加 margin 和高度规则，返回薄矩形描述；缺失 site 时存在使用物体位置和默认尺寸的回退。

因此，当前配置的主路径是“固定区域名 + scene site 几何”。不能说它必然从 BDDL ranges 计算表面。它仍可能因 skill 的 BDDL 匹配条件而依赖目标真值；固定区域名和 site 也属于需要声明的先验。

### 5.2 引擎支持的可选 BDDL 区域路径

`region_name_from_bddl_goal` 可以启用动态目标区域选择；`bounds_from_bddl_region` 可以从 `bddl_regions` 读取矩形 `ranges`。`tamp_scene.py::_bddl_table_rect_bounds` 在启用时还可调用 `_bddl_region_xy_offset`，用 BDDL 初始关系及当前物体位置估计 XY 偏移，以中位数对齐区域。

这属于真正的几何输入依赖，但是否执行由 profile 参数和 adapter 分支决定。目标来源迁移需要审计它，不能据“引擎里有代码”认定当前 pack 每次都走它。

### 5.3 迁移时的保留边界

保留已有目标到 surface 的改写、support object 规则、site 几何、margin、坐标系、碰撞表示和 grasp/place 参数。优先改变传入的语义目标与其 provenance。

现有 grounding 不应被假定已经具备任意对象选择能力。比如语言中的 `next to the ramekin`、`not between ...` 需要将语义 selector 绑定到场景实例；如果现有入口不能承载，就在最小接入层明确补充并单独验证，不能偷偷使用 BDDL 实例 ID 来“保持兼容”。

## 6. 计划怎样替换

以下类型、模式和日志字段是设计建议，不是已经实现的接口。

### 6.1 独立离线解析 mining

核心接口：`parse(language, frozen_parser_pack) -> TaskGoalSpec`。解析器看不到 env、BDDL goal、文件名、task ID 或场景实例列表。

例如语言“Pick the akita black bowl next to the ramekin and place it on the plate”应输出对象类别、`next_to(ramekin)` 选择条件、指代关系和最终 `on(selected_object, plate)`。不能直接输出 `akita_black_bowl_2_main` 或假装知道区域坐标。

BDDL 在开发侧提供最终目标监督，供 mining agent 分析错误；解析函数只接收语言。最终 goal 往往只有实例 ID，并不包含语言中完整的选择条件，因此不能只机械提取 goal 就声称获得了完整语义标签。需要审校语言、对象和初始关系；不一致、歧义或无法从语言恢复的样本要单列。

按语义模板/组合划分开发与留出集，并去重跨 suite 的相同语言。相同语言可能对应不同场景实例，语言解析应输出相同语义，由场景绑定解决实例差异。不能将每句话映射到其 BDDL 答案做查表，也不能把同一句话换 seed 当成新的解析泛化样本。

离线报告至少区分目标关系、对象描述、选择条件、指代、拒答/不支持和总体结构正确率。此阶段无需 episode 或 GPU。

### 6.2 最小兼容层与双模式

保留 `bddl_oracle` 模式作为历史对照，新增 `language_predicted` 模式。统一目标上下文至少包含语义目标、绑定实例、final atoms、goal surfaces、来源和失败状态。

runner、controller、task semantics、matcher 和 recovery candidate generator 必须消费同一目标上下文。不要仅在某一入口替换，然后允许下游 `parse_task(..., env=env)` 重读 BDDL。

旧 skill 可通过兼容层继续使用原来的字段形状。若短期保留 `bddl_goal_surface_matches` 名字作为历史别名，language 模式下值必须来自预测与绑定结果，并明确标记来源；长期迁移到中性字段。改名本身不消除泄漏，盲目全局替换则容易破坏旧 profile。

区域坐标不能由纯语言解析器凭空输出。几何描述由单独的场景接口提供，禁止通过正确 goal 挑选“答案区域”。现有 BDDL ranges 可选路径应在新模式显式阻断，或作为单独声明的几何 oracle 实验条件，不得静默混用。

解析/绑定失败时返回可诊断的失败状态，按预先定义的行为保留策略或停止该次 recovery；不使用真值纠正。LLM、规则候选和缓存同样不能成为隐藏回退来源。

## 7. 怎样避免弄坏现有 grounding

按以下顺序推进，出现偏差先定位层级，再决定是否修改该层。

| 阶段 | 检查内容 | 验收要求 |
| --- | --- | --- |
| 冻结旧行为 | 记录代码/pack hash、配置、场景快照、选中 skill 和目标链 | 旧模式仍可复现，不修改当前评测资产 |
| 相同语义输入的差分检查 | 在固定场景注入与旧模式等价的目标，走新兼容层 | target/goal、关键触发特征、winner、候选 atoms 与 surface 绑定一致 |
| 几何差分检查 | 比较虚拟表面 center、quat、half_extents、inner_bounds、support_z、frame、来源和碰撞属性 | 符号字段精确一致；浮点在预先声明容差内一致 |
| fluent 差分检查 | 比较 required atoms、近似诊断、最终 goal_state | 无额外丢失、错误绑定或候选顺序变化 |
| 信息隔离检查 | 固定语言和 scene 输入，仅替换/屏蔽 agent 可见 BDDL goal、interest、路径与任务 ID | language 模式预测和后续决策不应变化；环境评分器保持独立 |
| 缺失输入检查 | 缺失 selector 绑定、site 或目标对象，注入错误/低置信度解析 | 暴露失败与几何回退，无 BDDL 目标兜底 |
| 新模式离线扫描 | 使用预测模式重算 qstate 和匹配结果 | 显式 current/non-current roots，不能直接复用 oracle 字段的旧扫描结论 |
| 配对 rollout | 固定 pack 和其余参数，对比 oracle 与 language 模式 | 报告总体成功率及解析、绑定、触发、规划、执行各层失败 |

信息隔离检查应在固定快照/接口上做，不能改动 BDDL 导致环境也变了，再把动作变化误判为目标泄漏。

静态差分不能保证 rollout 完全相同；随机规划仍需固定 seeds 和配置。端到端验收应明确容许的成功率变化，不能只验证几个成功例子。`real_cutamp_grasp_dof=6` 等当前已确认参数保持一致，避免再次把配置变化当成语义模块效果。

## 8. 日志与研究结论的边界

建议每次保存：language、parser 版本与 skill hash、TaskGoalSpec、实例绑定及依据、目标来源、grounding 改写前后 atoms、表面几何来源、候选及 selected goal、fluent mapping/goal notes、实际 firing skill 与 query_idx、最终官方成功结果。

BDDL 参考答案放在评测侧独立记录，不放进 agent 可读取的 diagnostics。日志供后续 mining 回放时也要保持这种隔离。

需要分别报告：

- 现有 pack 在 BDDL 目标条件下的 recovery 效果。
- 冻结同一 pack，仅替换目标来源后的效果差异。
- 离线语言解析质量，以及场景绑定的正确率。
- 若以后重新 mining，明确那是新目标信息条件下的新 pack。

语言与 BDDL 目标不一致时，忠实解析语言也可能不满足官方 goal。应单独报告该类冲突，不能通过解析规则偷改指令来迎合标签。去掉 goal oracle 后仍保留的 scene state/site 等信息，也必须继续声明。

## 9. 本次范围与待定事项

本次仅归纳问题与迁移方案，不修改代码、pack、现有 grounding 或远端评测。

实施前仍需确定：语义 selector 的最小 schema；现有实例绑定入口的覆盖范围；scene site/region 信息的实验权限；语言失败时的 recovery 行为；留出划分；配对评测的验收阈值。

首个可独立交付物仍是离线语言解析器。接入阶段的原则是：目标来源替换要完整，grounding 行为变更要最小，无法等价的部分要显式记录并单独验证。
