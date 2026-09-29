# cuTAMP 下层抽屉能力（已验证基线）

面向后续 agent 的通用能力扩展流程见
[`cutamp_capability_extension_agent_playbook.md`](cutamp_capability_extension_agent_playbook.md)。

日期：2026-09-28  
状态：LIBERO-90 Task 7 仿真闭环已验证；尚未宣称跨柜体、跨任务泛化。

## 1. 能力边界

当前正式能力是：在 recovery 触发后，根据语言目标选择木柜下层抽屉，绑定 MuJoCo 中的真实 slide joint 和 handle geometry，由 cuTAMP 生成关节操作阶段，由 cuRobo 求解机械臂轨迹，并在 LIBERO 仿真中保持把手接触完成拉动。

它不是：

- “把物体放进已经打开的抽屉”；
- 通用的起始碰撞退让；
- Pick/Place 末端位姿修补；
- 对任意柜体、任意层抽屉已经验证的通用承诺。

这些方向不再与本能力混在同一运行路径中。历史代码仍可从标签 `bottom-drawer-e2e-20260928` 找回；本分支只保留正式闭环与必要观测工具。

## 2. 已验证闭环

验证任务为 LIBERO-90 Task 7 的下层木柜抽屉操作。保留黑碗的真实物理碰撞，没有通过删除场景物体伪造成功。

验证结果：

- 最终抽屉关节位置：`-0.1403661072`；
- 目标区间：`[-0.16, -0.140001]`；
- recovery 环境步数：`289`；
- 正式配置：`experiments/robot/libero/tiptop_repro/configs/libero90_bottom_drawer_open_v1.json`；
- 冻结标签：`bottom-drawer-e2e-20260928`；
- 仓库外证据包：`E:\VLA_recovery_workspace\articulation_smoke_20260923\bottom_drawer_capability_20260928`。

清理分支 `refactor/bottom-drawer-capability-clean` 又用同一 Task 7、seed 90 做了独立复验：GPU 预检通过，完整 episode 成功，实际执行 289 个 recovery env steps，最终关节仍为 `-0.1403661072`。复验证据在上述目录的 `clean_branch_preflight_20260928.json` 和 `clean_branch_task07_20260928/` 中。同步 ZIP 首次运行因可执行位丢失而在子进程启动前失败；修正新副本脚本权限后重跑成功，该部署故障不计为能力试验。

配置中的抓取位姿来自 Task 7 接触几何候选 8。它被封装为 `bottom_drawer_contact_c8_v1` profile，并固定了接触、夹紧和 Cartesian handle-follow 参数。能力运行时不再重新做候选搜索。

## 3. 正式运行链路

```text
任务语言
  -> recovery goal grounding
  -> region/link 名称解析
  -> ArticulatedPart 绑定（joint、handle、行程）
  -> cuTAMP articulation operators
  -> cuRobo IK / handle-follow trajectory
  -> LIBERO executor
  -> 实际 joint progress 与目标区间判定
```

关键代码：

| 职责 | 文件 |
| --- | --- |
| 部件绑定、状态和 profile 数据结构 | `experiments/robot/libero/tiptop_repro/articulation.py` |
| 碰撞世界、IK 和连续把手轨迹 | `experiments/robot/libero/tiptop_repro/articulation_curobo.py` |
| 操作阶段与候选选择 | `experiments/robot/libero/tiptop_repro/cutamp_articulation.py` |
| 仿真执行、接触与进度监测 | `experiments/robot/libero/tiptop_repro/articulation_executor.py` |
| recovery 目标到绑定 link 的解析 | `experiments/robot/libero/tiptop_repro/real_cutamp_adapter.py` |
| recovery 主执行桥 | `experiments/robot/libero/tiptop_repro/libero_tiptop_executor.py` |

## 4. 配置约定

下层抽屉能力只有一个权威配置：`libero90_bottom_drawer_open_v1.json`。旧的多 binding 实验配置已移除，避免同一句语言命中未经验证的旧抓法。

2026-09-29 起，两个已验证抓法同时进入独立 skill pack
`skill_packs/bottom_drawer_articulation_v1`。一个通用 skill 负责准入“打开下层抽屉”
操作，profile registry 再根据当前 MuJoCo 中的柜体锚点、把手位置、抽屉轴、拉出
走廊最近障碍物的相对位置/尺寸/间隙，自动选择命名 `articulation_profile`。
`profiles/articulation.yaml` 保存几何原型、binding、handle-frame grasp 和执行参数，
通用 articulation planner/executor 不再由任务配置分叉。原 JSON 仍保留为无 skill
回退入口和参数一致性回归 fixture。

启用方式为 `--enable_skills --skill_pack bottom_drawer_articulation_v1`。当前选择过程为：

- `runner` 从已读取的 MuJoCo scene 生成紧凑几何描述；
- selector 计算当前场景到两个成功几何原型的归一化 RMS 距离；
- 分数最小且满足最大距离、最小领先幅度时选中对应 profile；
- 缺失、歧义或分布外几何不猜测 profile，也不会静默套用任一抓法。

`source_suite`、task ID 和 BDDL 文件名均不参与 profile 选择。选择诊断会写入
`recovery_hints.params.articulation_profile_selection`，包含实际特征、最近障碍物、
每个候选分数和拒绝原因，便于继续增加新的几何原型。

2026-09-29 的 skill-only GPU 烟测（未传旧 articulation JSON）验证了选择与执行闭环：

| 场景 | 实测最近障碍物 / 走廊间隙 | 自动选择 | 分数 / 领先幅度 | 结果 |
| --- | --- | --- | --- | --- |
| Goal Task01 seed51 | `plate_1_main` / 0.027203 m | `bottom_drawer_goal_task01_height6_tight_v1` | 约 0 / 0.37305 | success，joint=-0.140152，616 steps |
| LIBERO-90 Task7 seed90 | `akita_black_bowl_1_main` / 0.011459 m | `bottom_drawer_contact_c8_v1` | 约 0 / 0.37305 | success，joint=-0.140366，289 steps |

本地证据目录为
`remote_outputs/bottom_drawer_geometry_smoke_20260929`。这只能证明两个已准入几何
簇的选择正确；遇到新的柜体姿态或障碍布局时，应先观察 `out_of_distribution` /
`ambiguous` 诊断，再通过验证结果增加原型或新 profile，而不是放宽到无条件猜测。

随后使用 `probe_articulation_profile_selector.py` 对 seed 51--65 的初始状态做了
不加载 VLA/cuTAMP 的几何选择回归：

| 场景 | selected | profile 一致性 | 最大最佳分数 | 最小领先幅度 |
| --- | ---: | ---: | ---: | ---: |
| Goal Task01 | 15/15 | raised/tight 15/15 | 0.09130 | 0.24367 |
| LIBERO-90 Task7 | 15/15 | candidate-8 15/15 | 0.11981 | 0.25578 |

两组都没有 `ambiguous` 或 `out_of_distribution`。证据保存在
`remote_outputs/bottom_drawer_geometry_probe_20260929`。

配置中：

- `part_id`、`joint_name`、`handle_geoms` 对应 MuJoCo 结构；
- `open_range` / `closed_range` 是任务成功目标；
- `grasps` 是 handle frame 到末端的固定变换；
- `grasp_profiles` 描述该抓法的执行方式；
- `soft_contact_objects` 只表达规划碰撞策略，不从仿真中删除物体；
- `path_settings` 控制关节行程离散和连续轨迹检查。

上层抽屉的既有参考配置仍为 `libero90_task01_articulation.json`。它与下层配置分开，防止把“同一个柜子”误当作“同一种可直接复用的抓法”。

## 5. 保留的观测与准入工具

| 工具 | 作用 |
| --- | --- |
| `probe_bottom_drawer_capability.py` | 在不启动 episode 的情况下，用记录的 problem 严格预检正式配置 |
| `inspect_articulation_ik.py` | 区分位姿不可达、自碰撞和环境碰撞世界拒绝 |
| `probe_articulation_ik.py` | 对记录问题做空世界、standoff、位置和方向对照 |
| `probe_articulation_refine.py` | 检查整段 slide 上的单 seed / multi-seed 连续可解性 |
| `probe_articulation_profile_selector.py` | 不加载 VLA/cuTAMP，批量读取初始状态几何并检查 profile 选择、分数与歧义边界 |
| `collision_attribution_probe.py` | 对碰撞来源做归因 |
| `collision_report.py` | 读取和报告 cuRobo collision world |

一次性抓法搜索脚本、Place 修补脚本和 start-state-retreat 实验不属于正式能力，已从清理分支移除。

## 6. 验证方法

### 本地静态回归

本地不要求 GPU。至少运行 articulation 单元测试以及完整的 `skill_pipeline/tests`，确认配置解析、part binding、profile 选择、trace schema 和既有 recovery 没有退化。

### GPU 预检

GPU 环境中使用保存的 solve problem：

```bash
scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh \
  scripts/recovery/skill_pipeline/probe_bottom_drawer_capability.py \
  --solve-json <recorded.problem.json> \
  --config experiments/robot/libero/tiptop_repro/configs/libero90_bottom_drawer_open_v1.json \
  --report-out <preflight.json>
```

预检必须返回 `ok=true`，并包含被选中的 profile、算子序列、阶段点数和失败候选；它不能替代 episode 执行验证。

### Episode 回归

正式 Task 7 回归必须同时检查：

1. recovery 确实选择 `wooden_cabinet_1_cabinet_bottom`；
2. 执行使用 `bottom_drawer_contact_c8_v1`；
3. 没有删除黑碗或关闭整个柜体碰撞；
4. 抽屉实际关节进入目标区间；
5. 任务成功来自仿真状态，而不是仅仅“轨迹执行完毕”。

之后再跑一次上层抽屉 Task 1 作为回归。只有当新的柜体/层级分别通过上述三层验证，才能加入新的权威配置。

## 7. 扩展新关节能力的准入门

新的抽屉或柜门能力按同一流程加入：先从 MuJoCo 建立 part/joint/handle 真值；再离线生成多种抓法；用 `inspect_articulation_ik.py` 排除纯运动学不可达；用 refine 工具检查完整行程；最后才写入版本化 profile 并跑真实 episode。

一个 profile 只有同时具备“结构绑定、全程轨迹、碰撞策略、仿真执行证据”才可进入正式配置。某个端点 IK 成功、空世界成功或临时忽略环境碰撞，都只能算诊断证据，不能算能力验收。
