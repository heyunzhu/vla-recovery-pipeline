# 任务目标解析 Skill：独立离线 Mining 设计

日期：2026-09-14

状态：设计提案，尚未实现。本文中的新目录、类型、字段和命令均为建议接口，不代表当前仓库已经支持。

## 1. 要完成的改变

建立一个独立于 recovery mining 的任务目标解析组件：从任务语言产生结构化语义目标，通过离线 mining 学习和维护解析 skill。

当前恢复链路可从 BDDL 获得正确目标。新组件将这部分目标来源替换为语言解析；BDDL 保留为离线监督和评测依据。

核心函数是：

```text
parse(language, frozen_parser_pack) -> TaskGoalSpec
```

输入不包含 scene、env、任务编号、文件名、对象实例列表或 BDDL goal。输出包含对象描述、限定关系、指代和最终目标关系，不包含场景中的具体对象 ID。

本项目沿用现有 grounding 的职责、profile、adapter 和 mining 流程。这里不新建一套 grounding，不同时挖 grasp、geometry、place、collision 或 repair，也不以 rollout 成功率评价解析 skill。

交付分成两个里程碑：

| 里程碑 | 交付 | 是否运行 episode |
| --- | --- | --- |
| M1：独立离线解析 | 数据集、解析协议、skill pack、mining 工具、静态评测报告 | 不运行，不启动环境或 cuTAMP |
| M2：接入现有恢复链路 | 将 TaskGoalSpec 适配到现有对象/surface 绑定和任务语义接口 | 接口检查可离线；真实 recovery 效果另行验证 |

M1 完成不等于整条 recovery 已经摆脱 BDDL 目标依赖。M2 是后续独立工程工作，不应混入解析 skill 的写入和效果统计。

## 2. 已核对的当前实现

以下内容根据当前本地代码核对；后续实施前应记录实际 commit 和工作树状态。

| 位置 | 当前行为 | 对设计的要求 |
| --- | --- | --- |
| `experiments/robot/libero/tiptop_repro/task_parser.py`：`parse_task` | 先做名称匹配；传入 env/BDDL 后，使用 BDDL target/goal 覆盖解析结果 | 新路径不能只替换语言匹配、继续保留目标覆盖 |
| 同文件：`ParsedTask` | `target_hint`、`goal_hint` 是具体名称，没有完整的对象选择条件类型 | 需要新的未绑定语义类型和最小接入适配 |
| `experiments/robot/libero/skill_pipeline/runner.py`：`_query_state` | 通过 `parse_task(..., env=env)` 获取目标，并计算 wrong-object 等特征 | 触发特征也必须使用语言产生的目标 |
| `experiments/robot/libero/tiptop_repro/cutamp_controller_v2.py`：`CuTAMPV2OraclePerceiver.perceive` | recovery 内再次调用 `parse_task(..., env=env)` | runner 改完后，controller 不能再次覆盖目标 |
| `experiments/robot/libero/tiptop_repro/task_semantics.py` | 已有 `TaskSemanticsResult`、规则和 LLM interpreter，接收已含目标提示的任务与 scene graph | 新组件在其上游；无需另造完整规划语义系统 |
| `experiments/robot/libero/tiptop_repro/real_cutamp_adapter.py`：`build_recovery_goal_candidates` | 从 `bddl_goal_atoms` 构造恢复目标候选 | language 模式需切断该目标来源 |
| `experiments/robot/libero/skill_pipeline/grounding_profiles.py` | 展开现有 grounding profile，由 adapter 归一化到 `grounding_hints` | 保留实现与 skill 资产 |
| `experiments/robot/libero/skill_pipeline/schema.py` | 当前 kind 只有 trigger、repair、diagnostics、recovery_hint | 新解析 skill 不能直接塞入旧 schema 或 recovery index |

现有 grounding 文档主要约束目标到 surface/region/support object 的绑定，不能据此声称它已经能求解所有 `next to`、`not between` 选择条件。接口缺项在 M2 中明确处理；不通过读取 BDDL 答案掩盖缺项。

参考：[grounding 编写指南](grounding_skill_authoring_guidelines.md)、[grounding 静态标准](grounding_skill_static_test_standard.md)、[现有 recovery mining 说明](skill_mining_actor_brief.md)。

## 3. 职责与信息边界

### 3.1 解析输出什么

以语言为例：

```text
Pick the akita black bowl next to the ramekin and place it on the plate
```

解析器应表达：

- 操作对象属于 akita black bowl 类别。
- 操作对象的选择条件是：位于 ramekin 旁边。
- `it` 指向前面选定的操作对象。
- 最终目标是把该对象放到 plate 上。

解析器不回答是哪一个 simulator body，不决定 plate 对应哪个 planner surface，不计算距离阈值、抓取点或放置坐标。

### 3.2 BDDL 可以在哪里使用

| 阶段 | 可以读取 | 不允许的做法 |
| --- | --- | --- |
| 开发集提取与标签审校 | 语言、完整 BDDL、objects、init、goal、regions | 把文件名当作文件内语言的替代品 |
| Mining agent 的错误分析 | 开发样本、标签、规则轨迹、开发回归结果 | 查看留出测试答案并据此改规则 |
| 在线解析函数 | 语言字符串、冻结的通用词表与解析 skill | 读取 env、BDDL、路径、task ID、实例列表 |
| 离线评测器 | 输入、预测、独立标签与 BDDL 参考 | 把参考答案传回解析函数 |
| 后续环境评分 | 官方成功条件 | 用评分目标纠正在线预测 |

允许用开发集 BDDL 教 agent 写通用规则，这是监督学习设定。禁止的是部署时取答案，以及把开发答案编成按句子、任务编号或固定对象 ID 检索的表。

从 BDDL 的 `(:language)` 提取用户指令是合法的数据读取；把 `(:goal)` 或 `obj_of_interest` 一起交给在线解析器则越过了边界。

## 4. 语料如何构建

### 4.1 原始数据

离线读取选定数据根目录下的任务文件，不启动 LIBERO，也不需要 GPU。首批使用已有 spatial 语言作为开发样例，之后按声明的研究范围扩展。

每条原始记录至少包括：

| 字段 | 用途 |
| --- | --- |
| `sample_id` | 数据管理标识，只存在于外层 runner，不作为解析输入 |
| `instruction` | 文件内的原始语言，或显式声明的真实 policy prompt |
| `instruction_source` | 语言来源，例如 `bddl_language` |
| `suite`、`source_path`、`source_sha256` | 溯源，不提供给在线解析器 |
| `raw_goal`、`raw_init`、`objects`、`regions` | 标签构建和一致性审校 |
| `duplicate_group`、`split` | 去重与划分 |
| `annotation_status`、`annotation_revision` | 标签质量和修改记录 |

优先复用现有 BDDL 提取工具。对于 `and`、`not`、量词或嵌套结构，必须确认提取器完整保留语义；现有只取 target/goal 的函数不能充当完整标签生成器。暂不支持的结构保留原文并标记，不能只取第一个 atom 当作完整目标。

### 4.2 去重与划分

按语言与任务语义分组，不能把同一任务不同 seed 当成新的语言样本。解析输入没有 seed，所以 seed1-50 并不形成 50 个独立的解析测试样本。

同一句话在不同 suite、task 或扰动单元中出现，默认放入同一个 duplicate group。单纯更换 BDDL 实例编号、文件名或任务目录，也不形成独立语义样本。

建议保留以下集合，不预先虚构当前数据能支持的样本量：

- `dev`：mining 可读取的输入与标签，包含固定回归子集。
- `test`：冻结前 mining 不读取的留出集合，按语义近重复组整体划分。
- `challenge`：独立组织的改写、介词替换、否定和修饰语作用域样本；区分已知句式改写与新组合。
- `quarantine`：标签冲突、语言无法表达 BDDL 目标、或暂不确定的样本。

所有集合在 mining 前生成 manifest，记录 hash、分组依据与数量。若十条 spatial 语言去重后样本太少，只能称为接口原型，不能声称已验证广泛语言泛化。

### 4.3 冲突分类

| 情况 | 处理 |
| --- | --- |
| 文件名与文件内语言不同 | 保留来源差异，以声明的输入语言为准，不自动判坏数据 |
| 相同语言，对应不同实例 ID，但抽象目标一致 | 正常现象；解析输出应一致，具体绑定由场景决定 |
| 语言说放到 plate，BDDL 最终目标却是不同关系，且无合理语义解释 | 标记 `language_goal_conflict`，进入 quarantine |
| BDDL 只给具体实例，无法据此验证语言修饰条件 | 标记部分监督；不伪造修饰条件标签 |
| 任务含当前不支持的多目标或否定结构 | 保留为 unsupported/challenge，不截断成简单任务 |

quarantine 数量和原因必须出现在报告中。不能根据候选表现好坏决定是否移除样本。

## 5. BDDL 监督怎样变成可靠标签

### 5.1 先明确 BDDL 不能直接提供什么

下面这个 BDDL goal：

```text
(On akita_black_bowl_2 plate_1)
```

可以监督最终关系和具体目标实例，但它不一定记录语言中的 `next to the ramekin`。只比较最终 goal，可能把遗漏整个对象限定短语的解析也判为正确。

所以需要两类分开的标签：

| 标签 | 内容 | 可检查的结论 |
| --- | --- | --- |
| `semantic_gold` | 从语言标注的类型化语义树，含修饰语与指代 | 语言是否被完整、正确地解释 |
| `bddl_reference` | 从 BDDL 提取的关系、对象类型和实例目标 | 与官方任务定义是否一致；实例绑定参考 |

`semantic_gold` 可以由独立的固定标注流程根据语言和 BDDL 辅助构建，经审校后冻结。它不是又一个在线模块，也不是重新 mining grounding。

对于能机械转换的简单目标可以自动建标签；关系作用域、否定和指代等不能可靠自动标注的部分，需审校或只报告部分标签指标。未经审校的生成标签称为 silver，不能和 gold 混报。

### 5.2 防止评测自证

- 标签构建器与待挖掘解析器使用不同工件；不能用当前候选预测直接当 gold。
- 修改候选不能顺手修改它刚刚没通过的标签。
- 标签确有错误时，提交独立的数据修订记录，重算所有被比较版本。
- `bddl_reference` 和 `semantic_gold` 不一致时进入审校，不自动让预测向某一方靠拢。
- 没有可靠完整语义标签的样本不计入 exact-match 分母，但必须报告数量和原因。
- BDDL 关系名称只做白名单语义归一化，例如大小写；不能把 `on` 和 `inside` 合并。

M1 的主要验收是语义解析，不包括实例绑定准确率。仅有语言和 BDDL、没有实际场景时，不声称验证了具体物体选择。

## 6. 输出协议：TaskGoalSpec

### 6.1 草案示例

下面是建议的 schema v1 示例，内部引用 `obj`、`ref`、`dst` 是语义变量，不是 simulator ID。

```yaml
schema_version: 1
status: parsed
entities:
  obj:
    category: akita_black_bowl
    selection: unique
    constraints:
      - relation: next_to
        reference: ref
        time_scope: instruction_start
  ref:
    category: ramekin
    selection: unique
    constraints: []
  dst:
    category: plate
    selection: unique
    constraints: []
action_intent: pick_and_place
target_ref: obj
final_goal:
  all:
    - predicate: on
      args: [obj, dst]
provenance:
  input_source: task_language
  skill_ids:
    - pick_place_pronoun_v1
    - noun_next_to_reference_v1
```

另外记录各字段对应的输入字符 span、pack hash、schema 版本和解析树，便于人工检查；这些记录不改变语义结果。

### 6.2 状态契约

| 状态 | 含义 | 后续处理 |
| --- | --- | --- |
| `parsed` | 产生唯一的完整语义结果，仍未绑定场景对象 | 可以交给现有链路的适配入口 |
| `ambiguous` | 语言存在多个不等价、无法消解的解析 | 返回候选与歧义位置，不武断选第一项 |
| `unsupported` | 缺少必要词汇、关系或句法规则 | 返回未支持片段，供离线 mining |
| `invalid` | 类型、引用、配置或 skill 执行错误 | 作为实现错误，不算普通语言失败 |

`selection: unique` 表达任务要求唯一选择，不代表当前场景真的只有一个候选。场景中存在多候选是下游绑定问题，不由纯语言解析器猜测。

### 6.3 语义细节

- 保留物体类别、颜色等可由语言支持的属性；不凭 BDDL 实例编号增加属性。
- `on the stove` 修饰源对象，与 `place it on the stove` 的最终关系分开表示。
- `not between A and B` 用显式 `not(between(...))` 表示，不能降格成 `next_to` 或丢掉否定。
- 源对象描述的空间限定默认针对 `instruction_start`；后续接入时保持已绑定目标身份。
- 代词必须有可解释的 antecedent；不能一律将 `it` 绑定到最近出现的名词。
- `open`、`closed`、`holding` 和放置关系保留差异，不能统统转成 place。
- 语言中的操作过程与最终条件分开存储，不能把 pick_and_place 的 pick 自动加成最终 holding。
- 不额外添加语言未要求的最终条件；例如 `handempty` 若是 executor 的执行约定，应在下游明确产生。
- 对目标中的合取保留所有项；若 v1 尚未实现某种逻辑，返回 unsupported。

## 7. 解析 Skill 的组织方式

### 7.1 使用独立 pack

建议目录如下，均待实现：

```text
task_parser_packs/
  libero_language_v1/
    pack.yaml
    skills/_index.yaml
    skills/actions/pick_place_pronoun.md
    skills/relations/noun_next_to_reference.md
    skills/relations/noun_on_support.md
    skills/relations/noun_not_between_references.md
    lexicon.yaml
```

不用当前 recovery pack 的 `skills/_index.yaml`，不为解析 skill 填写 `hook: after_pi0_query`、`backend: cutamp_recover` 或 recovery_hints。

建议将这种新工件称为 `task_parse_rule`，独立 schema 验证。可以复用已有 frontmatter 读取等中性工具，但不直接复用 recovery 的 kind、触发 winner 和准入语义。

### 7.2 优先使用声明式组合规则

由固定解释器提供 tokenizer、类型化捕获、引用检查、AST 构建与等价归一化；agent 主要挖规则和词汇映射，不在规则里写任意 Python。

规则例子如下，`pattern` 和 `emit` 是拟议 DSL，不是现有 matcher 的语法：

```yaml
id: noun_next_to_reference_v1
kind: task_parse_rule
stage: noun_phrase
input_type: text_span
output_type: EntitySelector
pattern:
  - capture: head
    parser: entity_head
  - literal: next to
  - capture: reference
    parser: noun_phrase
emit:
  constructor: with_relation
  entity: "$head"
  relation: next_to
  reference: "$reference"
  time_scope: instruction_start
```

这个规则只处理名词短语。更高层的 pick/place 规则先区分动作子句，再调用它，不让一条贪婪正则跨过 `and place` 吞掉目的地。

规则正文还需包含：适用范围、正反例、修复的问题、证据样本 ID、已知限制。样本 ID 只放在证据区，不进入匹配表达式。

### 7.3 匹配与冲突

- 只将完整覆盖必要语义片段的树作为完整解析；未消费的否定、介词或修饰语不能静默忽略。
- 支持多条生产规则组合，不照搬 repair 的“最高 priority winner”直接决定整句答案。
- 多个解析树归一化后等价，可以合并并保留所有来源。
- 多个解析树不等价，返回 ambiguous；不能通过提高 priority 隐藏已有正确解析。
- 解释器设置递归深度和候选树数量上限；达到上限返回可诊断状态，不静默丢弃语义分支。
- 词表可包含 `cream cheese`、`akita black bowl` 等通用类别表达；不能包含句子到具体对象编号的映射。
- 新增解释器构造器属于基础设施变化，必须单独记录，并重跑整个离线回归集。

## 8. 独立 Mining 流程

### 8.1 一轮如何执行

```text
冻结开发语料、标签、schema 和解释器版本
    -> 跑当前 parser pack 的完整 dev 评测
    -> 按失败类型聚类，选定一类问题
    -> 在临时 pack 中修改候选规则
    -> 跑最小正反例与类型检查
    -> 跑完整 dev + protected 回归
    -> admission 接受或拒绝
    -> 归档预测、差异、错误和 pack hash
```

错误类别至少区分：类别漏识别、源/目的地混淆、修饰语归属、关系混淆、否定遗漏、指代错绑、多目标丢失、歧义、规则冲突、实现错误和标签冲突。

Mining agent 先读失败样本和当前解析轨迹，再改对应层级；不能看到一个任务失败就新增整句专用规则。

### 8.2 实验节奏

这条 lane 不沿用 recovery 的 seed51-65、15 episodes、60% 成功率或 cuTAMP 超时设置。

- 小检查使用具有区分力的文本正反例，不要求执行 3-5 个 episode。
- 每版候选跑完整已冻结 dev 集，不能只检查修复的那几句话。
- 每版保存每个样本的 before/after AST 和错误变化，避免只看总分。
- 建议初始预算为每个失败簇最多 5 次有效候选；预算在 run 配置冻结，是新 lane 的约定，不套用旧 task 状态。
- 每轮无接受候选且预算耗尽时停止，保留最好版本和 unsupported 清单；不为了清零错误而放宽标签。
- 达到预先声明的开发覆盖目标，或完成预算后冻结版本，再进行留出评测。正式测试结果不能回流本轮 mining。

上述“开发覆盖目标”应在语料盘点后填写，不在尚不知道类别分布时任意指定一个 60% 门槛。

### 8.3 候选 Admission

| 门禁 | 接受条件 |
| --- | --- |
| Schema/type | 所有输出符合类型、引用和关系参数数量约定 |
| Input boundary | 在线规则只依赖语言和冻结的通用规则资源 |
| 完整性 | 没有静默遗失关键语义片段或未知关系 |
| 旧正确样本 | 所有 protected gold 样本仍得到语义等价的正确解析 |
| 新收益 | 至少修复一个真实开发错误；不得靠删除样本或改标签获益 |
| 错误变化 | 全 dev 正确数不降低；记录新增 confident error 与 ambiguity |
| 行为约束 | 不新增“错误但 parsed”的样本；从 unsupported 变成错误答案也应拒绝 |
| 冲突 | 不引入旧正确样本上的不等价竞争解析 |
| 可复现性 | 相同输入、schema 和 pack 重复运行得到一致结果 |

这里保护的是正确语义输出，不是旧规则必须继续成为 winner。新规则若改变内部推导路径，但结果等价，应允许接受。

拒绝结果必须写明样本 ID、旧/新输出和具体原因。仅重构等价规则不算一次语义收益，但可作为单独的维护变更验收。

## 9. 离线评测如何报告

### 9.1 主指标

| 指标 | 定义 |
| --- | --- |
| Semantic exact accuracy | 完整归一化 AST 与可靠 gold 等价的数量 / 有完整 gold 的样本数 |
| Parsed coverage | 返回 parsed 的数量 / 全部输入数，不等于正确率 |
| Accuracy among parsed | parsed 且正确 / parsed 且有 gold 的数量，明确分母 |
| Confident error | 返回 parsed 但语义错误的数量 |
| Unsupported / ambiguous / invalid | 各状态的数量与占比 |
| Field accuracy | 类别、源关系、目的关系、否定、指代等字段的正确率 |
| BDDL abstract consistency | 在可核对部分上，与 BDDL 的关系和对象类别约束一致的比例 |
| Regression count | 本轮破坏的旧正确语义解析数 |

内部变量重命名、白名单同义词和合法的合取项顺序变化可视为等价；不能通过归一化去掉对象限定、否定或目标项。

同一句输入出现多次时，同时报告去重语言分数与任务加权分数。跨 suite 同句重复不能伪装成大量独立泛化成功。

测试集、开发集、silver 标签和 quarantine 分开报告。M1 不报告 episode 成功率、抓取成功率或实例绑定准确率。

### 9.2 必需的区别性样例

| 样例对 | 必须发生的变化 |
| --- | --- |
| `bowl next to the cookie box` / `bowl on the cookie box` | 源对象限定关系改变 |
| `bowl on the stove ... on the plate` / `bowl on the plate ... on the stove` | 源关系与目的地不能混淆 |
| `between the plate and the ramekin` / `not between the plate and the ramekin` | 保留否定作用域 |
| `on top of the cabinet` / `in the top drawer of the cabinet` | 支撑关系与容纳关系、目标部件均不同 |
| `next to the plate` / `on the plate` 作为最终位置 | 最终目标关系不同，不能都输出 on |
| 只改冠词、大小写、标点的等价描述 | 在明确允许的归一化范围内，语义应一致 |
| 一个最终目标 / 两个最终目标 | 第二个目标不能丢失 |

对 BDDL 中的实例做 alpha-renaming，语言预测应不变；这个检查验证标签管道不会把实例编号反向注入解析器。场景位置交换属于后续 grounding 检查，不放入纯文本 lane。

## 10. 工具与工件布局建议

建议新增独立模块 `experiments/robot/libero/task_goal_parser/`，不要在现有 recovery matcher 中堆任务解析分支。

```text
experiments/robot/libero/task_goal_parser/
  schema.py             # TaskGoalSpec、ParseRule、类型验证
  parser.py             # 固定的组合解释器
  dataset.py            # 数据提取、去重、split 与标签状态
  evaluation.py         # 独立标签比较、AST 等价与分项指标
  admission.py          # 解析候选的离线门禁
  mining.py             # 状态、预算、候选接受与回滚
  tests/                # 类型、反例、冲突、泄漏边界测试

scripts/recovery/task_goal_parser/
  build_corpus.py
  evaluate.py
  run_admission.py
  run_mining.py

analysis_outputs/task_goal_parser/<run>/
  run_spec.json
  corpus_manifest.json
  pack_before_manifest.json
  candidates/<write_id>/
  predictions.jsonl
  errors.jsonl
  regression_diff.json
  admission.json
  summary.json
  report.md
```

脚本名称和路径只是实施建议，当前不能作为可运行命令使用。

run_spec 至少冻结：数据与标签 hash、split、schema/解释器版本、parser pack hash、候选预算、保护样本、停止条件。Mining agent 的模型版本、输入与输出也应归档，以便复现规则来源。

语料、私有测试标签、预测和规则工件分开存放；部署包只包含解释器需要的规则、词表与版本声明。仅靠字段命名约定不能防泄漏，评测 runner 应只把语言字符串传给解析 API。

## 11. 后续怎样接回现有 Grounding 与 Recovery

本节是 M2 的设计约束，不是要求 M1 新写一套 grounding。

### 11.1 接入关系

```text
任务语言
  -> 独立解析 skill pack
  -> TaskGoalSpec（未绑定的语义）
  -> 现有绑定入口的最小适配
  -> ParsedTask / TaskSemanticsResult（已绑定目标）
  -> 现有 repair、grounding、geometry、grasp、place
  -> cuTAMP recovery
```

具体对象识别和 surface/region 求解仍由当前链路承担。现有接口若不能承载 selector，就扩展传参和必要的关系求值入口；不把这项能力冒称已经存在，也不为兼容而让解析 skill 返回固定目标 ID。

若某个关系当前下游无法求解，记录 `binding_unsupported`，按既有 grounding 流程处理。这不回算成解析失败，也不触发本 lane 自动修改 grounding profile。

### 11.2 同一个目标贯穿恢复链路

- 语言模式使用与 VLA 相同的真实任务描述；不能让 VLA 读扰动语言、parser 读未扰动文件名。
- 在初始场景可用、策略动作开始前解析并完成适用的身份绑定。之后保留目标身份，更新姿态和执行进度。
- `_query_state` 的 wrong-object 特征、controller 的 task semantics 和 planner 的最终关系必须来自同一个目标上下文。
- controller 内重复 perceive 不得再次读取 BDDL 覆盖目标。
- 当前任务语义 interpreter 不能重新用原始字符串启发式推翻已经验证的解析；必要时通过已有 `TaskSemanticsResult` 接口接受语言产生的 atoms。
- 解析或绑定不确定时，不进入依赖确定目标的 recovery；保留 VLA 行为及原始任务预算，并记录原因。不得回退到 oracle goal。

### 11.3 兼容现有 BDDL 命名字段

现有 profile 和编译器使用 `bddl_goal_atoms`、`bddl_goal_surfaces` 等字段。建议内部增加中性的目标上下文：

```text
goal_source = language_skill | oracle_bddl
semantic_goal_atoms
semantic_goal_surfaces
task_goal_spec_hash
binding_provenance
```

在边界适配器中，必要时把语言推导并经现有 grounding 绑定的结果投影到旧字段，维持既有 profile 的读取接口。旧字段名字不代表数据必须来自 BDDL；日志必须同时明确真实 source。

这种兼容只允许传递语言推导的等价信息。若旧 profile 必须依赖当前任务 BDDL 专有的 region 名或目标答案，标记不兼容；不能从 BDDL 抄回这些信息来凑字段。

环境构建可以继续读取 BDDL。任务无关的场景几何也可以按原有设定保留，但目标专属 region、obj_of_interest、init atom 名中的隐含关系等需要来源审计，不能作为语言解析结果的替代答案。

### 11.4 切断隐藏目标回流的验收

接入测试至少覆盖：

1. language 模式中，目标解析/候选生成路径读取 BDDL goal 时测试直接失败。
2. 使用受控假输入更换隐藏的参考 goal，保持语言和场景输入不变，在线预测目标不变；不修改官方任务评分。
3. runner 和 controller 的目标来源、对象绑定、goal atoms 一致。
4. 既有 grounding/profile 获得语言导出的目标后，仍走原来的 planner primitive；没有暗中切换 profile。
5. 不兼容的 relation/region 明确报告；不静默回退到 parser 首个对象或 BDDL 目标。

以上可以先用静态 fixture 和 mock 做接口测试，真实闭环收益仍需在之后的正式评测中报告。

## 12. 实施顺序与完成标准

### 阶段 A：固定数据与语义协议

完成 corpus manifest、语言去重、冲突审校、schema v1、标签覆盖统计。先证明输入里有足够信息表达任务，不急于挖规则。

### 阶段 B：最小解析器

支持对象类别、pick/place 子句、on/inside 最终关系和代词引用；建立类型检查、完整消费检查、歧义输出及独立评测器。支持范围外显式拒绝。

### 阶段 C：离线 Mining

从空间限定关系开始挖规则；每版跑全 dev 和 protected gold。归档所有候选与拒绝原因。关系解释器不计算场景距离，不操作环境。

### 阶段 D：冻结与独立评测

冻结 parser pack、解释器、标签与测试 split，输出测试/挑战集报告。分开说明正确率、覆盖率、错误解析和不支持项。测试后产生新版本应使用新的评测协议，不反复沿用同一测试集作开发集。

### 阶段 E：接入现有系统

按第 11 节补最小接口与来源检查，沿用已有 grounding/recovery 资产。分别记录 oracle-goal 模式和 language-skill 模式；不直接覆盖已有实验记录。

M1 完成标准：

- 有可复现的语言语料与独立标签，清楚标注部分监督和冲突样本。
- 有只接收语言的确定性解析 API，以及可加载的独立 skill pack。
- 有完整开发回归、candidate admission、错误差异与冻结测试报告。
- 没有依赖 episode、cuTAMP 或 GPU 的验收步骤。
- 没有修改当前 recovery pack 或重新 mining grounding。
- 已知接口缺项、未支持语义和 M2 依赖均有明确清单。

M2 完成前，项目描述应写成“已实现可独立 mining 的离线任务语义解析器”；只有接入检查和闭环评测完成后，才能声称 recovery 的目标已由语言解析替代 BDDL 答案。
