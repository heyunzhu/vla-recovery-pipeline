# cuTAMP 能力扩展 Agent 作业手册

日期：2026-09-29  
适用仓库：`vla-recovery-pipeline`  
读者：负责为 recovery / cuTAMP 增加新操作能力的 coding agent  
参考实例：下层抽屉能力、Goal Task01 抓法迁移及几何 profile selector

## 1. 文档目的

本文把“从一个失败任务出发，将可复现的解决办法正式变成 cuTAMP 能力”的过程整理成可执行流程。
目标不是让 agent 为单个 episode 写一段能动起来的脚本，而是得到以下产物：

1. 明确的能力语义和适用边界；
2. 可观测、可序列化的场景状态；
3. cuTAMP 能搜索或选择的算子、约束及参数；
4. cuRobo 能生成的连续轨迹；
5. MuJoCo 中经过真实接触和状态变化验证的执行闭环；
6. 可由 skill pipeline 选择、可拒绝分布外输入的版本化 profile；
7. 跨 seed 回归、旧能力回归以及可审计的证据包。

最终能力必须满足：**不是靠 task ID、suite 名称、直接设置仿真状态、删除障碍物或关闭碰撞才成功。**

## 2. 先判断需要扩展哪一层

收到新任务后，agent 必须先完成分层判断。不要一开始就修改 cuTAMP 核心。

| 层级 | 典型现象 | 应做什么 | 不应做什么 |
| --- | --- | --- | --- |
| L0：现有能力已足够 | 目标、候选、规划、执行都正常，失败来自预算或部署 | 修运行参数、部署或明显 bug | 新增 profile 或算子 |
| L1：已有 primitive，缺少适合当前几何的参数 | 已能表示 Pick/Place/Open；某种抓法或接触参数失败 | 新增版本化 profile、几何 selector 和 skill | 复制一套 planner/executor |
| L2：已有 primitive，通用执行机制不完整 | 有 Open 算子，但缺少短拉进度门、连续 handle-follow、接触停滞处理 | 修改共享 articulation/grasp/place 执行机制并加可选参数 | 在 task 脚本里私自执行动作 |
| L3：真正缺少操作 primitive | 无法表示推、旋、按、铰链门、多阶段重抓等动作 | 新增谓词、算子、采样器、状态传播、连续约束和 executor 支持 | 用一个 profile 名称假装能力已经存在 |

判断依据必须来自 trace、problem、视频和代码路径，而不是语言名称。

以下问题可以快速定位层级：

- recovery goal 是否绑定到正确对象或关节部件？
- problem 中是否存在需要的 primitive / action schema？
- planner 是否生成了正确阶段？
- 是否存在 IK 解，但完整行程不可行？
- 规划可行后，物理执行是否真正改变了目标状态？
- 同一配置是否只在某种几何布局上成功？

下层抽屉 Task7 到 Goal Task01 的迁移属于 **L1 + 少量 L2**：Open primitive 已经存在，主要缺口是新的抓取 profile，以及短拉真实进度门和接触停滞控制流修正。

## 3. Agent 的输入、输出与停止条件

### 3.1 最小输入

开始前至少需要：

- 一个明确的任务语言和验收谓词；
- 一个可稳定复现的失败 episode；
- 对应 `query_trace.jsonl`、`recovery_trace.jsonl`；
- cuTAMP debug 的 `.problem.json` / `.result.json`；
- 失败视频或关键帧；
- 当前 active skill pack、profile registry 和 capability registry；
- 当前实际运行的 cuTAMP / cuRobo 环境版本。

若缺少 debug problem 或视频，先补观测，不要直接设计 profile。

### 3.2 最终输出

一个正式扩展至少应产生：

```text
共享引擎改动（只有 L2/L3 需要）
skill_packs/<pack>/
  pack.yaml
  capabilities.yaml
  profiles/<capability>.yaml
  skills/pair/recovery_hint/<scope>/<skill>.md
  skills/_index.yaml
tests/
诊断或离线 probe
设计/状态文档
GPU trace、视频和汇总报告
git commit
```

### 3.3 必须停止而不是继续调参的情况

- 目标对象/部件仍然不确定；
- 坐标系或变换方向没有验证；
- 只能通过删除障碍物、关闭整个环境碰撞或直接写 qpos 成功；
- 成功只由 episode 最终状态给出，无法证明 recovery 自己完成；
- 候选只通过端点 IK，没有完整路径检查；
- 当前几何同时接近多个 profile，selector 没有明确领先；
- 新任务实际上要求新的 primitive，但 agent 只能继续堆 profile 参数。

## 4. 总体流程

```text
冻结基线
  → 收集证据
  → 失败归因与扩展分层
  → 建立结构/几何真值
  → 定义能力契约
  → 生成可解释候选
  → 分层离线筛选
  → MuJoCo 短物理探测
  → 完整闭环
  → profile + skill + selector 封装
  → 跨 seed / 旧能力回归
  → 文档、证据和提交
```

每一阶段都必须留下产物和通过条件。后续阶段不能用成功结果反向掩盖前一阶段缺失的证据。

## 5. 阶段 A：冻结基线与工作区

### A1. 确认仓库、分支与服务器路径

记录：

- 本地仓库绝对路径；
- 当前分支和 HEAD；
- 服务器代码副本；
- Python / cuTAMP / cuRobo 环境；
- 数据、模型和日志目录；
- GPU 号和关键环境变量。

禁止直接修改服务器全局环境或 `site-packages`。依赖补丁必须能由仓库脚本或固定 overlay 重现。

### A2. 保存原始基线

至少保存：

- 原始命令；
- seed、init-state index、预算；
- 成功/失败视频；
- query/recovery trace；
- solve problem/result；
- 当前代码 commit。

基线必须包含一次“没有新能力”的真实失败。若任务本来就能完成，不应声称新增能力带来改善。

## 6. 阶段 B：失败归因

按以下顺序检查，避免把下游症状误判为抓取问题。

| 类别 | 需要检查的证据 | 常见修复层 |
| --- | --- | --- |
| 语义/grounding | 语言、目标对象、目标部件、目标谓词 | grounding skill 或 parser |
| 结构绑定 | joint、body、handle、range、轴、参考位姿 | articulation binding |
| 候选生成 | grasp 数量、位置、朝向、夹爪宽度 | profile / sampler |
| 运动学 | approach IK、全行程 IK、关节跳变 | cuRobo / path refinement |
| 碰撞 | 自碰撞、桌面、柜体、障碍物、重复几何 | collision world / proxy |
| 接触执行 | 单侧/双侧接触、夹紧、滑脱、停滞 | executor / profile |
| 成功判定 | 实际 joint/object progress、任务谓词 | executor result gate |
| 预算/部署 | timeout、step budget、脚本权限、环境版本 | 运行配置 |

建议统一使用故障标签：

```text
invalid_target_binding
invalid_articulation_binding
no_candidate
ik_infeasible
continuous_path_infeasible
collision_blocked
approach_tracking_failed
handle_contact_probe_no_progress
handle_slip_or_no_progress
target_not_reached
budget_exhausted
deployment_error
```

agent 在文档中必须写出“已排除什么、尚未排除什么”。

## 7. 阶段 C：建立结构和几何真值

### C1. 结构信息来自仿真器

关节物体至少读取：

- `joint_name`、joint type、axis、anchor、range；
- moving body 和 moving geom IDs；
- handle site 或 handle geoms；
- 当前 joint position；
- 固定柜体和周围障碍物几何；
- robot base pose。

不要从 BDDL 的 region 范围或 task 名称猜关节结构。语言只负责表达意图，例如“打开下层抽屉”；MuJoCo 负责回答具体关节和几何是什么。

### C2. 统一坐标系

任何候选搜索之前，必须声明：

- 世界坐标、机器人基座坐标、对象/把手坐标；
- 四元数顺序；
- 变换是 `A_from_B` 还是 `B_from_A`；
- grasp matrix 表示 `handle_from_ee` 还是 `ee_from_handle`。

至少用一个已知点做数值对照。此次下层抽屉 selector 曾暴露过典型问题：MuJoCo scene reader 给世界坐标，而保存的 cuTAMP problem 使用机器人基座坐标。两者若不统一，正确 profile 会被误判为分布外。

### C3. 保留真实障碍物

可使用精确 geom、分部 AABB 或经过记录的保守 proxy，但必须说明来源。允许的简化包括：

- 桌面薄层、裁剪后的桌面范围；
- 将复杂对象拆为多个碰撞部件；
- 明确且局部的接触例外。

禁止：

- 删除导致失败的物体；
- 关闭整个柜体或整个环境碰撞；
- 同时保留运动部件动态几何和初始静态副本；
- 用一个覆盖整个柜体的粗大 box 阻塞真实自由空间。

## 8. 阶段 D：定义能力契约

在写代码前，用一页内容回答：

1. 输入状态是什么？
2. 目标状态是什么？
3. 新增或复用哪些谓词？
4. 新增或复用哪些算子？
5. 连续参数有哪些？
6. 哪些约束必须硬满足？
7. executor 怎样确认物理成功？
8. 哪些场景明确不支持？

关节操作示例：

```text
输入：part、joint s0、handle pose、robot q0、障碍几何
目标：joint s ∈ target_range，最终 handempty
算子：MoveFree → GraspHandle → OpenArticulated → ReleaseHandle
约束：IK、连续性、handle pose consistency、碰撞、joint limit
成功：实测 joint 进入 target_range，任务谓词满足
```

如果现有 cuTAMP domain 无法表达所需动作，进入 L3；新增谓词名称但不接搜索、rollout、cost、refinement 和 executor，不算完成。

## 9. 阶段 E：生成候选

### E1. 候选必须在局部坐标系中表达

抓取或接触候选应相对对象/把手生成，例如：

- roll / pitch / yaw 小集合；
- handle-frame xyz offset；
- approach standoff；
- opening width、contact width、squeeze width；
- 推/拉方向和接触点；
- hinge/slide 的目标关节值。

不要把某个 episode 的世界坐标写进 profile。

### E2. 从粗搜索到局部搜索

推荐顺序：

1. 少量语义明确的姿态族；
2. 空世界或放宽环境碰撞检查结构性可达；
3. 恢复真实碰撞，筛选完整路径；
4. 围绕最有希望的候选做毫米级和角度级局部网格；
5. 物理短探测；
6. 完整执行。

此次 Task01 使用的局部搜索为 roll `-10/0/+10°`、handle-frame x/y `-6/0/+6 mm`，共 27 个候选；18 个通过完整离线轨迹，最终物理成功来自“抬高 6 mm + 更紧 squeeze”，而不是继续盲目增加 roll。

### E3. 控制搜索规模

每个新增维度都要有失败假设。候选很多但没有失败归因，只会增加 planner 负担并降低可解释性。

## 10. 阶段 F：分层验证候选

必须按从便宜到昂贵的顺序运行。

### F1. 结构 gate

检查：

- part/joint/handle 均能唯一绑定；
- target range 合法且方向正确；
- grasp matrix finite；
- 序列化往返不丢字段；
- profile 参数能被 registry 和 capability registry 接受。

失败时不要启动 GPU episode。

### F2. 单点 IK gate

分别检查：

- approach 起点；
- 接触位姿；
- 行程中点；
- 目标终点。

空世界可解、真实碰撞不可解说明问题在 collision world；两者都不可解说明候选姿态或机器人可达性有问题。

### F3. 全行程连续性 gate

不能用四个端点代替连续路径。至少检查：

- 稠密 joint samples；
- position/orientation residual；
- 最大 robot joint jump；
- 每个 sample 的自碰撞和环境碰撞；
- 最终平滑/插值后的轨迹。

对应工具包括：

```text
scripts/recovery/skill_pipeline/probe_articulation_ik.py
scripts/recovery/skill_pipeline/probe_articulation_refine.py
scripts/recovery/skill_pipeline/collision_attribution_probe.py
```

### F4. MuJoCo 短物理探测

规划可行不等于抓持有效。先执行一小段操作，并以真实状态变化为 gate。

抽屉示例：

```text
contact_probe_distance_m = 0.015
contact_probe_min_progress_m = 0.004
```

短拉后 joint 没有同向进度，立即失败，不要继续浪费完整预算。对推动、旋钮、按钮等能力，应定义对应的短物理响应指标。

### F5. 完整闭环

完整闭环必须检查：

- recovery 自己的 execute event 成功；
- 实测目标状态进入目标区间；
- episode success 与 recovery success 一致；
- 没有 VLA 在 recovery 失败后偶然补完；
- 没有直接写仿真状态；
- 没有删除障碍物或关闭全局碰撞。

## 11. 阶段 G：把成功封装成能力

### G1. profile 拥有参数，skill 只负责准入

推荐职责：

| 组件 | 内容 |
| --- | --- |
| 通用 planner/executor | 算子、约束、轨迹、执行机制 |
| profile registry | binding、局部 grasp/contact、路径和控制参数 |
| Markdown skill | 语言/对象语义范围，选择 profile 或 selector |
| capability registry | pack 允许使用的 profile 和参数 |
| selector | 根据实时可观测状态在已验证 profile 中选择 |

不要把整份 articulation 配置复制进 Markdown skill；也不要把 benchmark-specific 参数写回共享 planner。

### G2. 新 profile 的命名和版本

名称应表达对象/部件、策略和版本，例如：

```text
bottom_drawer_contact_c8_v1
bottom_drawer_goal_task01_height6_tight_v1
hinge_door_outer_handle_left_v1
```

profile 必须带 evidence/source 字段，能追溯到 sweep、episode 和 commit。

### G3. 保留兼容与参数一致性测试

在迁移旧 JSON 或实验配置时，先写 parity test，证明 registry 展开后的参数与已验证配置一致。旧配置可以暂时保留为：

- 无 skill fallback；
- regression fixture；
- 历史复现入口。

确认迁移稳定后再决定是否删除，不能边迁移边悄悄改变数值。

## 12. 阶段 H：根据实际几何选择 profile

### H1. 不允许按 suite/task ID 选择

以下字段不能作为物理 profile 的最终选择依据：

```text
source_suite
task_id
seed
BDDL filename
query index
```

它们可以用于报告分组，不能替代几何和状态。

### H2. 推荐几何特征

按能力选择足够且稳定的特征。关节操作可包括：

- handle 在 robot base 中的位置；
- joint anchor、axis、type 和 range；
- 柜体/部件尺寸；
- 操作扫掠走廊；
- 最近障碍物到走廊的 AABB 间隙；
- 最近障碍物相对方向和尺寸；
- 当前机器人构型或粗可达性指标；
- 已知接触/holding 状态。

特征必须来自当前 observation / MuJoCo scene。不同坐标系先统一到 robot base 或对象局部坐标系。

### H3. 原型评分与拒绝机制

当前下层抽屉使用归一化 RMS 原型距离：

```text
r_i = (feature_i - prototype_i) / scale_i
score = sqrt(mean(r_i²))
```

选择必须同时满足：

- 最佳分数小于 `max_normalized_rms`；
- 最佳与第二名之差大于 `min_score_margin`；
- 所需特征完整。

否则返回：

```text
missing_geometry
no_scorable_candidates
ambiguous
out_of_distribution
```

不得为了“多覆盖任务”简单放宽阈值。新几何应先作为 OOD 证据，经候选搜索和闭环验证后加入新原型或新 profile。

### H4. selector 验证

先离线遍历初始状态，不加载 VLA 和 cuTAMP：

```bash
python scripts/recovery/skill_pipeline/probe_articulation_profile_selector.py \
  --task-suite-name <suite> \
  --task-id <id> \
  --seed-start 51 \
  --count 15 \
  --output <report.json>
```

报告至少统计：

- 每种 selection status 数量；
- 每种 profile 数量；
- 最大最佳分数；
- 最小领先幅度；
- 最近障碍物和间隙；
- 每个 seed 的特征。

随后才跑少量完整 skill-only GPU episode，并确认没有传旧的强制 profile 配置。

## 13. 阶段 I：准入和回归

### I1. 最小测试矩阵

| 测试 | 是否需要 GPU | 通过条件 |
| --- | :---: | --- |
| registry/schema/capability 单测 | 否 | 全部通过 |
| profile parity / candidate 单测 | 否 | 数值和候选符合预期 |
| selector 单测 | 否 | 正确选择、标签交换不影响、缺失/OOD/歧义拒绝 |
| 记录 problem 的 planner preflight | 视环境而定 | 正确 primitive、阶段和 profile |
| 初始状态 selector sweep | 否/仅 MuJoCo | 无意外 profile、边界有裕量 |
| 单 seed 完整 episode | 是 | recovery 和任务真值成功 |
| 多 seed 回归 | 是 | 达到预先设定门槛，失败可归因 |
| 旧能力 canary | 是 | 不退化 |
| 全 skill pipeline 测试 | 否 | 不引入其他 pack 回归 |

### I2. 三种成功率分开报告

必须分别统计：

1. planner feasible rate；
2. recovery execute success rate；
3. episode task success rate。

只报告 episode 总成功率会掩盖 recovery 失败后 VLA 补完、或者 planner 成功但物理执行失败。

### I3. 负例也要测试

至少包含：

- 错误对象/部件；
- 缺失 handle；
- 分布外柜体姿态；
- 两个 profile 分数接近；
- 不支持的 holding 状态；
- 目标已经满足；
- 碰撞真实无解。

正确拒绝是能力的一部分。

## 14. Agent 工作纪律

### 14.1 每轮只验证一个假设

例如：

```text
假设：失败来自抓取高度，而不是 roll。
改动：只扫描 handle-frame z。
观测：短拉 joint progress、双侧接触、完整拉动。
结论：接受/拒绝假设。
```

不要一轮同时修改 grasp、桌面 proxy、预算、碰撞例外和成功阈值；即使成功也无法知道原因。

### 14.2 先修观测，再修能力

如果不知道碰撞发生在哪里、joint 是否移动、profile 是否真正进入 planner，先增加 trace/probe。不可观测的成功不能进入正式 pack。

### 14.3 不将实验脚本变成正式执行路径

一次性 sweep、可视化、碰撞 attribution 可以保留为工具；正式 episode 必须经过正常 runner → skill runtime → cuTAMP → cuRobo → executor 链路。

### 14.4 不用放宽成功判定制造成功

允许在环境任务已经满足时接受末端 pose 的 near miss，但必须记录：

- 实测目标状态；
- 任务谓词；
- 末端误差；
- 为什么物理目标优先于轨迹末点。

不得仅因轨迹执行了一部分就返回成功。

### 14.5 保持工作区可恢复

- 改动前保存 commit；
- 不覆盖用户无关修改；
- 实验数据放仓库外固定目录；
- 重要证据同步回本地；
- 每个正式能力有独立设计/状态文档；
- 完成后工作区应干净。

## 15. 建议的 Agent 执行记录模板

```markdown
# <能力名称> 扩展记录

## Scope
- task / language:
- desired primitive:
- supported / unsupported:
- baseline commit:

## Baseline Failure
- episode / seed / init state:
- failure label:
- video / trace / problem:

## Layer Decision
- L0 / L1 / L2 / L3:
- evidence:

## Scene Contract
- target / part / joint / handle:
- coordinate frames:
- obstacles:
- target state/range:

## Candidate Search
- parameters and grid:
- number generated:
- structure pass:
- IK pass:
- full-path pass:

## Physical Validation
- short-probe result:
- full execution result:
- measured state progress:
- failure cases:

## Packaging
- profile:
- skill:
- selector features:
- capability registration:

## Regression
- unit tests:
- selector sweep:
- full episodes:
- old capability canaries:

## Evidence And Commit
- local evidence:
- server evidence:
- commit:
- remaining limitations:
```

## 16. 新能力准入检查表

只有全部必要项通过，agent 才能写“能力已实现”。

### 语义与结构

- [ ] 目标对象/部件唯一；
- [ ] joint / handle / range 来自 MuJoCo 或明确资产配置；
- [ ] 任务成功区间与环境评测一致；
- [ ] 坐标系和变换方向经过数值对照。

### 规划

- [ ] cuTAMP problem 中存在真实 primitive；
- [ ] 新算子贯通搜索、状态传播、约束和细化；
- [ ] 候选经过完整路径而非端点检查；
- [ ] 碰撞世界保留真实障碍物；
- [ ] planner 失败有明确原因。

### 执行

- [ ] 接近、接触、操作、释放阶段均可观测；
- [ ] 使用实际状态变化确认短探测和最终成功；
- [ ] 未直接修改目标 qpos/pose；
- [ ] 未删除障碍物或关闭全局碰撞；
- [ ] recovery success 与 episode success 可区分。

### 封装与泛化

- [ ] 参数进入版本化 profile；
- [ ] skill 不内联整套 planner 配置；
- [ ] profile 在 capability registry 注册；
- [ ] selector 使用实时几何/状态，不使用 suite/task ID；
- [ ] 缺失、歧义和 OOD 输入 fail closed；
- [ ] 多 seed 和旧能力回归通过。

### 证据

- [ ] trace、problem/result、视频、汇总报告齐全；
- [ ] 文档说明成功与失败边界；
- [ ] 本地和服务器证据路径可追溯；
- [ ] 测试结果和 commit 已记录；
- [ ] 工作区干净。

## 17. 当前可复用代码和文档

| 目的 | 路径 |
| --- | --- |
| 关节结构、binding、路径 | `experiments/robot/libero/tiptop_repro/articulation.py` |
| 关节碰撞与 cuRobo | `experiments/robot/libero/tiptop_repro/articulation_curobo.py` |
| articulation planner | `experiments/robot/libero/tiptop_repro/cutamp_articulation.py` |
| MuJoCo 执行与进度门 | `experiments/robot/libero/tiptop_repro/articulation_executor.py` |
| skill profile registry | `experiments/robot/libero/skill_pipeline/articulation_profiles.py` |
| 实时几何描述与评分 | `experiments/robot/libero/skill_pipeline/articulation_geometry.py` |
| profile selector probe | `scripts/recovery/skill_pipeline/probe_articulation_profile_selector.py` |
| 已验证下层抽屉能力 | `docs/design/bottom_drawer_capability.md` |
| Task01 候选搜索与物理验证 | `docs/design/articulation_libero_goal_task01_status_20260929.md` |
| 原生关节能力设计 | `docs/design/cutamp_articulated_manipulation.md` |
| 通用 grasp skill 写法 | `docs/grasp_skill_authoring_guidelines.md` |

## 18. 最终原则

为 cuTAMP 增加能力的核心不是“找到一组能跑通的参数”，而是完成下面的闭环：

> 从真实失败中提出可验证假设；从仿真器读取结构和几何；在局部坐标系中生成候选；用完整连续路径和物理状态变化筛选；将成功方案封装成版本化 profile；用实时几何选择并对未知输入拒绝；最后用多 seed 和旧能力回归证明它没有退化。

只要其中任意一环仍依赖 task 名称、隐藏真值、碰撞关闭或直接状态修改，它就仍是实验补丁，而不是可复用的 cuTAMP 能力。
