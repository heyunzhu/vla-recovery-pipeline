# RGB-D 视觉场景与 cuTAMP 最小交接接口

更新日期：2026-09-29。本文供 RGB-D 迁移与 cuTAMP/skill 开发者约定接口；当前实现是**离线诊断交接包**，不是可执行的 visual recovery。服务器仿真深度属于传感器观测；物体 body 位姿、geom、site、contact、非机器人关节和 `done`/任务成功信号仍不能进入视觉决策。

## 当前可交付的数据

`experiments/robot/libero/skill_pipeline/visual_recovery_handoff.py` 将同一 RGB-D 帧的 `VisualSceneAdmission` 和任务语言组成 `VisualRecoveryHandoff`，无 env/sim 参数。`scripts/recovery/skill_pipeline/export_visual_handoff.py` 可从冻结 RGB-D 和检测产物导出 JSON，并核对检测提示确实由该任务语言生成。

| 字段 | 含义 | 使用边界 |
| --- | --- | --- |
| `snapshot_id`、`episode_id`、`env_step`、`timestamp_s`、`camera_id` | 数据时序与相机身份 | 同一决策必须消费同一个快照，不可拼接不同时间的物体和本体状态。 |
| `calibration_version`、`frame_rgb_sha256`、`perception_backend_id` | 观测及检测来源 | 用于复现和拒绝不一致输入，不是物体置信度。 |
| `robot_state` | 白名单本体状态，包括关节、夹爪与末端状态 | 不含非机器人关节或接触真值。 |
| `visible_objects` | 视觉实例 ID、类别、可见表面 3D 质心/边界、像素框、深度覆盖和追踪状态 | 可见质心**不是**物体 body 中心；可见边界**不是**完整碰撞几何。检测原始分数未校准。 |
| `binding` | 目标、目标区域参照物与任务空间关系的 ID 候选 | `candidate_requires_attribute_check` 不代表颜色等描述已核验。 |
| `status`、`reason`、`mask_conflicts`、`unresolved_checks` | 显式拒绝或剩余检查项 | `scene_refused` 时不输出场景和目标；`binding_refused` 时无可执行目标。 |
| `planning_allowed` | 当前统一为 `false` | 在后续属性、目标区域、抓取/碰撞几何与验收闭合前，不得把候选送进在线 planner/executor。 |

现有 `tiptop_repro/scene_reader.py::SceneState` 的物体位姿、完整几何、关节、接触与 holding 均由 `read_scene(env, obs)` 取得。`cutamp_controller_v2.py::CuTAMPV2OraclePerceiver.perceive`、`skill_pipeline/runner.py::_parse_episode_task/_query_state` 和 `libero_tiptop_executor.py::LiberoRobotClient.get_scene` 均依赖这条 oracle 路径。不能把 `visible_centroid_world_m` 直接填进 `ObjectState.pos`，也不能在视觉缺项时退回 `read_scene`。需要明确版本化的 visual adapter，并由其对缺失几何返回不可规划结果。

## 保存帧 canary

首段 spatial task 0 序列的 `agentview` 第 0 帧和第 3 帧已分别导出 `visual_recovery_handoff.json`，位于本地序列根目录的 `step000/agentview/` 和 `step003/agentview/` 下，原始数据不提交 Git。冻结任务语言来自序列 `summary.json`。

| 帧 | 交接状态 | 关键证据 |
| --- | --- | --- |
| step 0 | `scene_refused` | 原始 bowl/ramekin mask 重叠；不输出视觉场景或目标。 |
| step 3 | `visual_id_candidate` | target `obj_002`、goal `obj_003`，`black bowl` 未核验；有 5 个可见检测，其中还包含左侧柜体的 `plate` 误检；`planning_allowed=false`。 |

这两个结果只能验证交接字段和拒绝语义。step 3 的绑定不能绕开误检检查，也没有抓取、放置或任务完成结果。

## 与 cuTAMP 对接时要定下的四件事

1. **首个共同任务。**选一个已在 oracle cuTAMP 路径跑通的 pick/place 任务，固定 task/init/seed、相机、分辨率与预算。这样视觉失败能与规划能力区分。
2. **规划器最少需要哪些几何。**逐字段列出目标位置、形状代理、桌面/容器区域、碰撞安全距及坐标系的必需项；视觉缺项返回明确拒绝，不套用 MuJoCo proxy。
3. **何时允许执行。**约定类别与属性、目标区域、抓取候选、持物状态及放置验收各由什么观测验证；第一版可缩小到一种普通放置，不含抽屉、柜门与遮挡物体。
4. **责任边界和评测。**visual 模式的 runner、perceiver、executor 共用同一快照；仿真成功信号只进入独立评测。记录准入率、误绑定、拒绝原因、在线成功率与 oracle 访问次数，并与相同任务条件下的 oracle 模式对照。

完成这四项约定后，下一次代码改动才是替换在线入口，而不是继续给现有 oracle `SceneState` 补一个外观相似的对象。

## 新 cuTAMP 分支的整合状态

2026-09-29 从服务器只读核对 GitHub：`feature/cutamp-articulated-manipulation` 最新为 `c1de978`，包含单自由度抽屉/门能力；当前视觉分支基于 `feature/bddl-language-and-goal` 的 `326f4f7`。两条分支的 merge-base 仍是 `main` 的 `6f5638c`，分别有 34 和 10 个独有提交，不能把新分支视为已包含任务语言绑定的直接后继。新分支的 `runner.py::_query_state`、`CuTAMPV2OraclePerceiver.perceive` 和 `LiberoRobotClient.get_scene` 仍调用 `read_scene(env, obs)`。因此视觉入口替换需求未消失；当前 pick/place canary 无需先合并关节操作提交。最终整合基线应由两条工作的维护者共同确定后再迁移，避免覆盖任务绑定或误称已接入新版 cuTAMP。

## 2026-09-30 可见表面证据扩展

交接导出现在支持显式冻结提示词变体，并可在显式工作范围中导出 schema 2 的 plate 可见表面证据；实例与当前 mask 的索引/哈希关联已加入 `visible_objects`。默认任务语言校验仍保留。几何输出包含平面近似与可见边界，不能作为可执行放置区域；`goal_region_and_clearance` 未解决项及 `planning_allowed=false` 保留。详见 [plate 表面诊断](rgbd_goal_surface_diagnostic_20260930.md)。

## 2026-09-30 可见区域容纳检查

已补 plate 实际 mask/深度采样限制与 bowl 可见水平包络容纳诊断，逐帧保存可重放网格。四帧均未找到满足当前完整可见包络容纳条件的位置；这不代表任务物理上不可完成，平面 patch 丢失的曲面和真实接触足迹仍需处理。完整测试 574 项通过，执行授权仍为 false。详见 [容纳诊断](rgbd_visible_placement_diagnostic_20260930.md)。

## 2026-10-02 曲面表示进展

新增独立可见高度场，保留 plate 曲面和缺深度区域；已完成 512 四帧、1024 单帧及归一化冻结 mask 对照。高分辨率减少了当前包络检查的缺证据格子，但所有尝试仍拒绝，边缘深度与接触足迹问题尚未解决。完整测试 579 项通过。详细数值、混杂因素和原始产物见 [高度场诊断](rgbd_heightfield_diagnostic_20261002.md)。
