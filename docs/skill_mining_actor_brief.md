# 技能挖掘 Agent 说明

更新日期：2026-09-13

这份说明讲两件事：这个项目在做什么，以及你在里面是什么角色。读完它之后再按需读第八节的
分类指南与流程文档。

## 1. 项目在做什么

我们让一个 Pi0 VLA 在 LIBERO-Pro 上跑长程操作任务。VLA 的成功率不够，而且失败方式很集中：
目标抓点不对、目标绑错、planner 缺一块几何、最后几厘米放不准、或者该切 recovery 的时候没切。

所以 VLA 之外还有一条确定性的接管链路：

- 每个 Pi0 query 之后，在线 matcher 跑一遍当前 skill pack 里的 skill；
- 命中的 skill 决定**是否离开 VLA 切到 cuTAMP recovery**，以及切入后**抓哪里、目标指向哪个
  surface、planner 里那块地方长什么样、最后怎么放**；
- cuTAMP 规划成功后由 executor 执行。

我们要的是把 VLA 覆盖不了的那部分失败，用**可解释、可回放、可回滚**的 skill 补上。一条 skill
的价值不在"让这一次跑过了"，而在机制说得清楚、适用条件写得准、并且不抢别的 skill 的活。

## 2. 失败分成五层，另加一层诊断

先判断失败在哪一层，再动手。写错层的 skill 会让问题被掩盖。

| 层 | 归它管的判断 | 典型信号 |
| --- | --- | --- |
| `repair` | 该不该离开 VLA 进 recovery（时机） | 没触发、触发太晚/太早、抓错对象、被铰接物挡住 |
| `grasp` | recovery 已进入，但 pick 失败 | 抓点偏浅/偏高、yaw 方向错、close 后物体不跟随 |
| `grounding` | 目标指向哪个语义对象/surface | BDDL 说是 A，实际编译成 B；虚拟 region 被实体抢走 |
| `geometry` | 那块区域在 planner 里怎么表示 | region 不存在、尺寸/bounds 错、缺 inner-floor proxy |
| `place` | 已 holding 目标，最后几厘米的执行 | transfer 掉高度撞环境、release 前 footprint 偏出开口 |
| `diagnostics` | 现有 trace 不足以判断 | 需要新的在线诊断信号，而不是硬凑 trigger |

同一次工作可以为同一条恢复链路补齐多层能力，不必等每层都失败过一遍。但**有多少证据修多少层**：
不要求凑齐五类，也不能只凭任务名字新增一堆 profile。

## 3. 你的角色

你是这套 skill 的**作者和诊断者**，不是执行者：在线控制器永远不会调用你。你的产物是**确定性
工件**——一份能被现有 parser 解析、被 admission gate 静态检查、被离线扫描重放、必要时能被回滚的
skill，或一组 skill 加 pack-local 能力。

因此：

- 结论要落在机器能检验的东西上：skill markdown、注册过的 profile、pack-local adapter 代码、
  或诊断信号。单纯的现象描述不是产物。
- 一次只动一个变量。同时改 region bounds、collision、yaw、release guard，即使成功也不知道是哪层起作用。
- 说不清机制就先别写；宁可把不确定的部分写成假设。
- 是否入库、是否跑正式验证由人决定，你负责给出候选和它的证据。

## 4. 证据与判断

- **观察和假设分开写**。没真正进入仿真跑过，就不能写"已验证"。
- 图像/帧对照要覆盖多个代表 episode；存在成功 episode 时就加成功对照，并解释成功为什么没走失败分支。
- 关闭 recovery 的 baseline 里没有 recovery 记录，那是**实验设置**，不是"只缺一个 trigger"的证据。
  要检查切入之后现有 backend 会用哪个 grasp、绑哪个目标、造什么几何、怎么释放。
- 汇总信息不是根因。规划失败至少要看到具体 problem / result / stderr，区分：优化无解、有满足粒子但
  运动规划失败、有优化解但没变成可执行解。
- 单个约束出现 `0/64` 不等于整条 episode 必然无解，先看失败发生在哪个阶段。

## 5. 实验节奏与验收

把 probe、小实验和正式验证分开记录，不能用一个层级的结果替代另一个层级。

**诊断 probe。** 单个 seed / query 的强制 recovery probe 只回答一个局部问题：是否能进入待研究阶段、
失败卡在哪个约束或执行事件、当前假设有没有基本物理可能。probe 可以失败，也可以只跑 1 条，但结论
必须写成“诊断证据”，不能写成泛化成功率。probe / check 不消耗写入次数，不直接更改 `online:`，
也不能替代完整 validation。

**小实验。** 当新增或修改一个具体假设、profile、adapter 参数或 place / grasp 行为后，优先跑
3-5 条代表 episode 或同等数量的 saved-problem replay，覆盖不同 seed / init 或不同失败阶段。
如果只跑了 1 条，必须明确它只是 smoke/probe，并说明为什么还不足以下结论。小实验要保留视频、
`recovery_trace.jsonl`、`summary.json`、cuTAMP `problem/result/stderr`，并按失败阶段分类。

**正式验证。** 每写出一次可上线的 skill / profile / pack-local code 版本后，都要用本 run 的正式
配置跑完整同 init validation。人工 mining 默认使用 `seed51-65` 的 15 条 episode；如果 run 配置
另有 trials，以该 run 的 frozen config 为准。通过阈值按成功率 60% 计算：15 条需要至少 9 条成功。
前 5 条全失败可以早停拒绝，但不能把 `3/5` 当作 `9/15` 的通过证据。正式验证还要确认不比
skills-off baseline 退化。

**写入预算。** 每个 task 默认最多允许 5 次有效 skill/code 写入。一次写入指一个可被 ingest /
admission / validation 评价的候选版本；诊断 probe、静态 check、配置修错和日志分析不算写入。
5 次仍达不到阈值时，保留最好草稿和诊断报告，标记未通过或 blocker，不把弱草稿放进 `online:`。

**继续还是收尾。** validation 没到阈值时，先按失败分布决定下一步：没触发看 repair，close/lift
失败看 grasp，目标或 surface 错看 grounding，规划几何错看 geometry，holding 后放不准看 place。
只有达到通过阈值，或证据显示问题超出 skill pack 能力边界并已写清 engineering action，才算可以收尾。

## 6. 运行时契约（要写对必须知道）

**pack 布局。** 一个 skill pack 是 `skill_packs/<pack>/`：

```text
skill_packs/<pack>/skills/pair/repair/*.md                    触发/接管时机
skill_packs/<pack>/skills/pair/recovery_hint/grasp/*.md
skill_packs/<pack>/skills/pair/recovery_hint/grounding/*.md
skill_packs/<pack>/skills/pair/recovery_hint/geometry/*.md
skill_packs/<pack>/skills/pair/recovery_hint/place/*.md
skill_packs/<pack>/profiles/*.yaml                            参数目录
skill_packs/<pack>/code/*.py                                  benchmark 专用逻辑
skill_packs/<pack>/capabilities.yaml                          注册表
```

**是否 online 只看该 pack 的 `skills/_index.yaml`。** 目录里有 `.md` 但没进 `online:` 列表，
就是没上线。

**命名 profile 在 recovery 开始前展开：**

| profile | 来源 | 展开成 |
| --- | --- | --- |
| `grounding_profile` | `profiles/grounding.yaml` | `params.grounding_hints` |
| `geometry_profile` | `profiles/geometry.yaml` | `params.geometry_hints` + 受限 executor metadata |
| `repair_profile` | `profiles/repair.yaml` | recovery-entry 的 executor 参数 |
| `place_profile` | `profiles/place.yaml` | 经 pack 的 `place_policy_adapter` → `hover` / `align` / `release` |
| `grasp_profile` | `code/grasp_profiles.py` | 挂上本 pack 的 grasp adapter |

展开后的 hints 由 capability registry 审计。**place 只认 `hover`、`align`、`release` 三个 hook 名；
未知 hook 名、未知 hook key、未知 executor option 都是 hard error，不是被忽略的 no-op。**

**边界。** benchmark 专用逻辑只能待在 pack 里。共享 runner / planner / executor 只保留通用
primitive——不要往 `tamp_scene.py`、`real_cutamp_adapter.py`、`real_cutamp_backend.py`、
`libero_tiptop_executor.py` 里加 task-specific 分支。共享 primitive 的名字定义在
`experiments/robot/libero/tiptop_repro/engine_capabilities.py`。

**坐标帧。** planner problem 用 robot-base frame：`geoms`、`sites`、`metadata.sites`、
`metadata.containment_sites` 在被 adapter 读到之前已经被平移/旋转到该 frame。virtual surface 和
opening 要写明 `coordinate_frame` / `inner_bounds_coordinate_frame`。把 world 绝对坐标悄悄塞进
planner-frame hint，会让 cuTAMP 规划到一个偏移约 robot base 的"幻影位置"。

### 要新增能力时，只有六个通道

路径固定、引擎调用的符号固定、id 必须被注册表知道。

| 通道 | 写这个文件 | 必须暴露 | id 还要出现在 |
| --- | --- | --- | --- |
| `grasp_profile` | `code/grasp_profiles.py` | `PROFILE_IDS`；`sample_grasp_profile(profile, dims, *, rim, pose)`；`profile_gripper_width(profile, dims, *, rim, radius, pose)` | `capabilities.yaml` → `grasp_profiles` |
| `grounding_hint` | `code/grounding_profiles.py` | `PROFILE_IDS`；`normalize_grounding_profile_params(profile, params)` 返回 params | `profiles/grounding.yaml` → `profiles.<id>`，且 `capabilities.yaml` → `grounding_profiles` |
| `geometry_hint` | `code/geometry_profiles.py` | `PROFILE_IDS`；`normalize_geometry_profile_params(profile, params)` 返回 params | `profiles/geometry.yaml` → `profiles.<id>`，且 `capabilities.yaml` → `geometry_profiles` |
| `place_policy` | `code/place_policies.py` | `PROFILE_IDS`；`resolve_hover_policy` / `resolve_align_policy` / `resolve_release_policy` 至少一个，签名 `(profile, profile_data, params)` | `profiles/place.yaml` → `profiles.<id>`，且 `capabilities.yaml` → `place_profiles` |
| `predicate` | `code/predicates.py` | `PREDICATE_IDS` 和/或 `APPLIES_PREDICATE_IDS`；`evaluate_predicate(name, expected, state)`、`evaluate_applies_predicate(name, expected, state)` | `capabilities.yaml` → `trigger_predicates` / `applies_to_predicates` |
| `diagnostic_signal` | `diagnostics/registry.yaml` + pack 内任意位置的 provider | provider 暴露 `compute(state, history)` 返回 outputs mapping | 被 trigger 使用时 → `capabilities.yaml` → `diagnostic_signals` |

几个容易搞错的点：

- **profile id 分布在两个文件里。** `profiles/*.yaml` 里必须有 `profiles.<id>`，Python 只提供行为；
  代码声明了 id 而目录里没有会在加载时被拒。`grasp_profile` 和 `predicate` 的 id 只写在代码里。
- **`PROFILE_IDS` 必须是非空字面量。** 留成 `PROFILE_IDS = ()` 的脚手架不会被加载。
- **你的代码是被调用，不是被 import。** 收 plain dict/list、还 plain dict/list；不要 import 引擎内部，
  不要读写文件，不要改全局状态，不要用随机数或墙上时钟——同一输入必须永远给同一输出，因为离线扫描
  会拿录下来的 episode 重放你的 adapter。
- **只返回引擎已经支持的值。** 新的 executor option、新的 place hook 名、新的 geometry descriptor
  shape、新的 grounding primitive 都属于共享引擎改动，在 pack 里发明它们不会生效。

## 7. 禁令

- trigger 里不写 Python。
- 不用 query index、seed、绝对 xyz 当条件。
- 不许只凭"夹爪打开、空手、正在接近目标"就判定失败——目标接近是上下文，不是失败信号。trigger 里
  至少要有一个谓词表示**已经出了问题**（末端停滞、持续的抓错对象意图、铰接物阻挡、pick/hold 失败、
  close/lift 之后物体不跟随）。
- 不发明谓词、profile、intent、executor option、release mode、place hook 名。
- 不在 pack 之外写 task-specific adapter。
- 不静默复用 legacy capability；需要就在说明里写清楚。
- trace 显示问题在 grasp / grounding / geometry / place 时，不要交一份纯 repair。
- 不 dump 或要求完整的 contact table；不把 `logvar_*`、`residual_score` 当唯一触发条件。
- diagnostics skill 没有 online hook，新诊断信号要走 draft/shadow/online 的过程。
- 不为了让规划通过而放宽 release guard、大面积排除 collision、或改写任务目标语义。

## 8. 分类指南与流程文档（按需读）

读完本说明后，按你判断的失败层去读对应指南。改哪一层就读哪一层，跨层就都读。

| 指南 | 什么时候读 |
| --- | --- |
| `docs/repair_skill_authoring_guidelines.md` | 判断该不该切 recovery、写 trigger、做切入时机实验 |
| `docs/grasp_skill_authoring_guidelines.md` | 进入 recovery 后 pick 失败，要设计抓取候选/profile |
| `docs/grounding_skill_authoring_guidelines.md` | 目标对象/surface/region 绑定可疑 |
| `docs/geometry_skill_authoring_guidelines.md` | planner 缺虚拟面、inner-floor proxy、bounds 或碰撞表示 |
| `docs/place_skill_authoring_guidelines.md` | 已 holding，问题在 transfer / hover / 对齐 / drop / release |

另外两份按需查阅：`docs/skill_capability_registry.md`（注册表的确切字段）、
`docs/diagnostic_signal_pipeline.md`（要新增诊断信号时）。

流程和验收节奏查阅：

| 文档 | 什么时候读 |
| --- | --- |
| `docs/skill_authoring_evidence_and_probes.md` | 需要区分 probe、小实验、正式 validation，或使用 `remote.py probe-recovery` |
| `docs/skill_pipeline_mining_loop.md` | 需要确认 mining lane 的 passed / write budget / validation / score 规则 |
