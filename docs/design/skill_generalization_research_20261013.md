# 外部skill库重构与生产逻辑：第一轮调研

日期：2026-10-13。仅文献与本地代码/历史材料调查；未修改skill、引擎、门禁或冻结实验，未提交GPU实验。

## 1. 结论与前述方案的修正

研究“固定基础模型、外部可执行能力库不断扩展/重构”合理，机器人库学习已有直接先例。但本系统不等同于标准LLM在线function calling：Codex位于离线生产外环，在线主要由确定性matcher决定handoff，然后固定cuTAMP/执行器消费profiles与hints。文本语义检索不是当前在线瓶颈的既定事实。

此前“需要新增已有skill试跑、分诊、复用提示”的说法不准确：这些已经存在。actor prompt也已要求按物体类别复用能力，避免重复，输出代码而非仅描述，并保留success/failure证据。真正缺口更可能是多案例的库级重构、替代关系管理、跨物体/任务的独立验证；尚未实验证实这些就是性能瓶颈。

不要将“减少条目数”“扩宽regex”“抽象描述”当作泛化本身。需要分别考虑：调用判断的通用性、几何/抓取算法的可迁移性、goal编译支持范围、物理执行与回归安全。

## 2. 文献证据与迁移边界

| 工作 | 经核查的方法 | 可借鉴 | 不应直接推断 |
|---|---|---|---|
|ToolLibGen v1|问题专用函数→功能聚类→库设计/代码重构→reviewer调用solver验证原问题覆盖；seen与unseen分开|多案例蓝图、原功能到新实现的映射、功能保持回归|源题回归不等于未见物体或物理状态泛化；不能用功能名称相似证明可合并|
|ToolScope v2|语义候选→等价关系图→代表工具/签名描述整合→自动纠错→候选检索与rerank|相似/包含/互补能力关系的候选发现|主体结果是工具选择，不是机器人代码重构；原标签会映射到合并后标签，不能据此证明所有原执行行为保存。端到端只20query|
|ReGAL|对一批原程序提炼helper，同时重写调用方；执行对比原输出；失败反馈；编辑/剪枝codebank|共同helper+调用方同步重构；通过/失败案例同时驱动修订|假设有参考程序/输出；机器人非确定执行不能直接要求轨迹字节等价。压缩与泛化不是同一指标|
|LRLL|wake收集成功instruction/action/success-code及初始状态；sleep按忽略常量/变量的AST结构分组，抽象函数，再从初态回放|积累经验后批量抽象，与新失败即时修复分开；保留可回放初态与旧能力|其API/仿真与本系统不同；自生成success code依赖特权仿真状态，不能直接替代固定benchmark成功判据|
|Voyager|可执行代码skill、检索复用、执行错误/环境反馈、自验证|以实际成功程序而非只有失败摘要作为抽象来源|Minecraft高层动作与接触操控不同；存成功程序不自动解决库级合并和旧行为回归|
|Code as Policies|基于感知/控制API生成带逻辑和参数计算的机器人程序，支持层级函数生成|区分参数化算法与物体常量；明确可编程API边界|不是现成的持续库重构或保持性验证流程|

还发现ASPIRE（2026）的直接相关工作：固定模型之外持续修订robot control programs，细粒度执行trace驱动修复、skill库及搜索。已查官方摘要与仓库入口；其LIBERO-Pro fix-loop、zero-shot-transfer和库规模runbook值得第二轮深入。尚未逐文件核验实现或复现实验，不把其宣传成绩直接用作本项目预期。

来源（原始论文/作者项目页）：

- ToolLibGen：https://arxiv.org/html/2510.07768v1 （§2、§3.1、§3.3）
- ToolScope：https://arxiv.org/html/2510.20036v2 （§3.2、§4.2、Appendix M端到端20query）
- ReGAL：https://arxiv.org/html/2401.16467v2 （§3.1–3.3）
- LRLL：https://arxiv.org/html/2406.18746v2 （§III-A/B、§V）
- Voyager：https://voyager.minedojo.org/
- Code as Policies：https://code-as-policies.github.io/
- ASPIRE：https://arxiv.org/abs/2607.00272 、https://github.com/NVlabs/ASPIRE

## 3. 现有实现与生产流程

本地材料与代码互证：

- `scripts/recovery/skill_pipeline/run_codex_actor.py`：组装当前skill Markdown、index、capability registry、authoring指南及pair/fail_set证据。不是完全不读已有库，但没有在此入口看到功能依赖/多案例重构的专门结构化输入。该入口也不保证自动包含全部profile源码，需要区分具体daemon/actor调用路径。
- `scripts/recovery/skill_pipeline/prompts/actor.md`：已经要求分诊repair/grasp/grounding/geometry/place/diagnostics、查看约束结果、复用既有entrypoint、识别重复failure mode、生成pack-local可执行代码、检查注册与确定性。repair_profile只有YAML参数，不是任意动作程序。
- `docs/skill_pipeline_mining_loop.md` 与 `experiments/robot/libero/skill_pipeline/mine.py`：新task先带当前库验证，再决定是否写草稿。默认同init5集、60%与不低于baseline；实际run可配置15集或其他数目，不能说全部历史只验5集。
- `experiments/robot/libero/skill_pipeline/admission.py`：候选成为非当前成功episode的repair winner默认拒绝；shadowed匹配可保留。保护旧行为，但若要有意替代旧skill，需单独验证替代兼容，不能简单去掉保护。
- pack-local grasp/geometry/grounding/place adapters及capability registry可以承载参数化算法；新增底层动作/goal编译primitive仍属于工程能力扩展，不是改提示词即可获得。

## 4. 三个实物案例

### A. Cabinet trigger：执行路径复用，新增的是阈值窗口

本地 `libero_goal_task_from_goal_swap_v1_cross_suite_mining_20260914` 的cabinet与wooden-cabinet early两个trigger都使用既有bowl grasp/plate placement及entry repair profile。

wooden early文档记录：当前库W0为5/15；部分失败q6–q8未触发；原future-target阈值0.18m错过0.10–0.15m窗口，因此调整margin、intent/target距离并提高priority，限制wooden-cabinet语言。文档末尾明确说明限制语言是为了不匹配已经保护的旧task成功run。

这支持“生产单位受task与安全门禁影响而拆成阈值补丁”的假设；不证明合并更好，也未在本轮复核全部原W0/W1 raw traces/score。任务编号使用当时mining记录，不能与20261011冻结lex序号混用。

### B. Hollow bowl grasp：已经复用核心算法

`libero_goal_swap_task09_seed51_65_v1/.../grasp_bowl_plate_hollow_rim_topdown.md`只是选择核心`hollow_bowl_rim_topdown`采样器，黑碗/plate名称限定了适用范围；不是新生成的独立抓取程序。缺失pack-local grasp代码不是遗漏，而是核心profile复用。

要扩大能力应调查已有算法的几何适用范围及语义绑定，不应先凭名称把多个hint强行“合并成新工具”。

### C. Cream-cheese bundle：已有多层代码能力，可研究算法泛化

`libero_goal_swap_task07_seed51_65_v1/drafts/findings.md`与bundle记录：W1诊断错误目标意图/目标静止，组合trigger、grasp、bowl support grounding/geometry；W3复用entrypoint，调整place hover/drop预算。

`code/grasp_profiles.py`按dims及pose识别竖直轴、长轴、计算局部采样及yaw、夹爪宽度，已经有几何参数化；同时含奶酪默认尺寸、采样系数、宽度夹限，不能据此声明适用于所有薄盒。place profiles是具体hover/drop参数，非通用可学习动作策略。

该家族是“执行算法泛化”候选：需要几何、可达性、夹爪跨度、接触与成功验证。它不等同于A类“调用规则泛化”。W1/W3材料是历史作者记录，不是本轮独立重跑结果；本地没有完整证明每阶段真实因果收益的raw validation链。

## 5. 已有跨任务证据与缺口

`docs/results/libero_pro_c4_skill_trigger_catalog_and_generalization.md`已明确修正：现有统计是已评测任务的覆盖审计，不是独立held-out泛化测试。36assets中18trigger/18hint，hint并非独立候选winner。通用bowl入口在多个suite有使用证据，但仍依赖bowl/plate及已有目标解释。

`docs/results/libero_pro_c4_all36_skill_usage_table.md`再次区分hook决策与实际recovery入口，使用后episode成功不是单skill因果成功率。不能用“36条都比较过”或“多task使用”证明泛化。

50seed数据可作旧任务保持与失败状态材料，但曾用于现有分析；不能随意再挑有利样本称独立测试。若用来生成重构候选，则应转为开发/回归材料，不再承担未见泛化结论。

## 6. 验证资源与尚未确认的内容

已经具备：episode身份、query/recovery traces、视频、保存planner problem、受控单episode forced-query probe、离线trigger replay、候选pack隔离与能力检查、固定成功判据。

边界：forced-query probe从同初态跑到指定query，不保证完整还原某个旧failure瞬间；保存planner problem支持规划比较，不等于可物理回放整个接管状态。还需确认完整模拟器状态、机器人/物体速度、controller内部态、历史意图窗口与随机状态是否可保存并恢复。此能力未在本轮找到完整验收链，不能先假设可用。

## 7. 基于调研的决策，而非立即实施

不建议现在整体合并库或直接加入语义检索选择器。先在不改库的前提下补齐两个机制不同的casebook：A类阈值专用trigger、C类几何参数化grasp。每组需要原例/旧成功/同类不同实例/负例及生成可见范围，并记录依赖和验证证据。

接下来具体步骤取决于证据：

1. 如果原算法在新几何上可用而语义gate不匹配，优先研究适用判断泛化，不重写执行器。
2. 如果目标/调用正确但采样失败，优先研究几何感知算法/分支，不仅扩大regex。
3. 如果goal编译或动作primitive缺失，列为工程能力，不用skill抽象掩盖。
4. 如果重构需要替代旧入口，先设计行为兼容与回归证据通道，再讨论门禁调整。

第二轮最需补：两家族完整历史 raw evidence→patch→admission→rollout score链；尺寸/姿态可用范围及依赖图；固定failure-state物理回放可行性；未见对象/goal/布局划分；ASPIRE相关代码与eval协议。需这些后再决定首个GPU试点。

本轮调查并非完整系统综述，也未核验远端所有历史资产；结论按“源码可确认”“文档记录”“待验证假设”分层。没有修改或再运行C0–C4/50seed实验。
