# 视觉规划证据输入：2026-10-07

## 本轮交付

新增 `visual_planning_input.py`，在 recovery admission 控制器中实际运行。读取共享 provider 的当前 mask，构建 `VisualPlanningInput`，保存可见几何及准入缺口。输出数据格式为 `rgbd_planning_evidence_v1`，不冒充旧 `SceneState` 或 `TAMPProblem`。

provider 现持有不可变 mask 副本，避免检测器返回数组随后被改写。取 mask 时重新验证完整帧摘要，包含 RGB、深度、有效性、内外参、时间和机器人状态；新规划入口还重建交接包并检查绑定证据未变。点群数组也不可修改。

在线控制器把规划摘要写入 admission 结果；当前不会保存完整在线点群文件或调用 solver。离线回放新增 `--planning-dir`，将实际点群导出为 `visible_geometry.npz`，摘要为 `planning_input.json`，并记录输入帧内容摘要和 NPZ SHA-256。

## 字段含义

| 输出 | 来源与限制 |
| --- | --- |
| desired_goal | 语言绑定的视觉 ID 和关系；只是期望目标，already_satisfied 为 unknown |
| 每个当前实例的可见点群/均值/边界 | 当前 mask 内有效深度反投影到世界系；不是 body pose 或完整尺寸；保留完整 mask 点群，未按工作区裁剪 |
| observed_world_points | 声明的 canary 工作区内所有有效可见点，包括机器人和目标；不是已分类障碍，也不证明自由空间 |
| goal_surface | 已有 plate mask 内拟合的可见表面候选；不是完整支撑区域或放置证书 |
| grasp_candidate | 独立视觉候选包的 selector 与几何结果，保留原拒绝原因 |
| robot_state | 允许的本体观测；不是旧 planner 的基座系 q_init 转换 |
| holding_state / goal_state | unknown，未注入 handempty、holding 或成功谓词 |
| unknown_space / solver_allowed | unclassified / false，不能凭点群缺失判定无障碍 |

固定 workspace 为 x[-0.5,0.4]、y[-0.5,0.5]、z[0.75,1.5]m，来自当前 canary 配置；不是从场景真值读出的桌面范围。

## 与现有 cuTAMP 输入的差距

读取审查了 `tiptop_repro/tamp_scene.py` 和 `real_cutamp_backend.py`；没有导入或执行这些 oracle 依赖模块。

| 旧后端实际消费 | 当前可提供 | 仍缺 |
| --- | --- | --- |
| TAMPObject pos/quat/radius/height/half_extents、collision parts | 可见点群与边界 | 完整几何/姿态表达、未知空间及碰撞策略；不能用可见中心/边界直接替换 |
| GraspCandidate pos/quat/approach/width | 可见碗沿 anchor 和参考系候选，可能拒绝 | 接触宽度、姿态、完整接近轨迹、碰撞验收 |
| place_candidates | 目标可见表面候选 | 目标完整 footprint、支撑稳定性、扫掠净空 |
| init_atoms/current_grasp | unknown 持物/完成状态 | 视觉谓词及持物验证；不能借用 truth/contact |
| q_init、机器人基座转换 | 白名单 joint/EEF proprio | 独立静态机器人基座标定和后端坐标契约 |
| movables/surfaces/statics、goal_atoms | 当前视觉 ID 和期望关系 | 独立 solver bridge 与类别/角色可靠性验证 |

## 本轮验证

45 项测试通过（7 项新规划证据测试及 provider、控制器、在线循环、候选包回归）。检查实际点群与均值一致、目标期望与初始事实分离、mask/点群不可变、目标以外深度改变拒绝、交接包绑定篡改拒绝、冲突场景无规划 mask、NPZ round trip 与摘要。

真实历史帧：`D:\大三上\科研\visual-policy-dual-query-20261004\frames\step000014`。输出目录：`D:\大三上\科研\visual-planning-input-20261007`。本轮没有新增服务器 rollout。

结果为 `evidence_prepared_with_gaps`；目标表面为 `visible_surface_candidate`。grasp 几何仍因既有 canary 工作区/位移约束拒绝。solver/execution 均 false，恢复动作 0；不报告规划、抓取或任务成功。

四个当前实例可见点数分别为 bowl `obj_001` 2430、plate `obj_002` 5262、目标候选 bowl `obj_003` 2994、ramekin `obj_004` 1821。目标表面拟合有 3196 个内点，RMS 约 0.859 mm；这些数值描述可见采样和拟合误差，不是完整几何误差。

## 下一步

优先拆分 grasp 几何生成与机器人接近规划的约束，记录候选失败到底是高度还是当前 EEF 位移。随后对当前机器人静态模型定义基座/末端坐标契约，建立碰撞点群及 unknown-space 检查。满足这些字段后再实现独立 cuTAMP solver bridge，而非反复增加准入拒绝包装。
