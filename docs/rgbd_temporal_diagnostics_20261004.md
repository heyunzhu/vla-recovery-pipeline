# 视觉持物与目标关系的时序诊断（2026-10-04）

## 新增能力

新增 `VisualTemporalDiagnostics`，连续消费同一 episode、固定相机、任务语言和 detector 的当前 RGB-D/handoff。它只处理本体观测、实例可见中心/范围和视觉绑定，不接受环境、接触表、物体 body pose 或 benchmark done。

已接入视觉策略循环：后续每条 query trace 新增 `visual_temporal_diagnostics`。当前恢复 readiness 不变；新增证据不自动删除抓取、持物或支撑阻塞项。

### 持物相关证据

检查两帧夹爪是否持续闭合、手的平移是否充分、目标可见中心是否随手平移、相对运动残差、末端旋转、可见范围变化、目标距离和 goal 参考物是否静止。至少三个连续观测、两个满足条件的区间才返回 `holding_motion_candidate`。

当前实验阈值：两帧夹爪开度和均为 0–25 mm，手平移至少 10 mm，目标可见中心移动至少 8 mm，跟随残差不超过 3 mm，末端旋转不超过 0.05 rad，可见范围变化不超过 20%，goal 中心变化不超过 3 mm，目标可见中心距末端不超过 120 mm。

这些阈值是代码中明确的诊断规则，尚未通过抓取正负样本校准。稳定的可见中心不是刚体姿态，跟随现象不能单独证明接触或 attachment。闭合但无运动、夹爪状态不连续、旋转/遮挡变化和参考物移动都会阻止累计。手移动但目标不跟随时，可报告 `motion_not_consistent_with_holding`；这仍是当前可见运动的判断，不是不可见接触的完整真值。

### 目标关系相关证据

当前只覆盖 `on` 关系的粗略可见接近检查：目标可见中心落在 goal 可见 XY bounds 中、可见高度顺序合理、目标/goal 中心稳定、夹爪开度至少 40 mm、手离目标至少 80 mm，以及可见范围稳定。连续两个有效区间后返回 `visible_goal_proximity_candidate`。

可见 XY bounds 不是安全放置区域，目标可见最低点不是外底面。本诊断不据此宣称支撑接触、完整 footprint containment 或任务成功。

所有结果均保持 `holding_verified=false`、`goal_verified=false`、`planning_allowed=false`。需要补接触/attachment、外底几何、支撑/footprint 和任务属性证据。固定相机、当前 observed/tracked ID、深度覆盖至少 80%、相邻模拟时间间隔 0.05–0.5 秒是累计条件；身份或标定变化、丢失目标、时间断裂会中断累计。

## 实际数据回放

使用上一轮真实 Pi0 8 步 rollout 的第 10/14 步重新读取冻结 detector 文件，复用共享 provider 跟踪，再运行新诊断。没有启动模型、仿真或发送动作；这次是**新时序逻辑的离线验证**，不是新服务器 rollout。旧服务器 trace 保持原样。

| 项目 | 实测回放 |
| --- | --- |
| 手平移 | 10.85 mm |
| 目标可见中心变化 | 约 0.015 mm |
| 跟随残差 | 10.85 mm |
| 目标中心距末端 | 约 350.5 mm |
| 末端旋转 | 0.0233 rad |
| 两帧持物诊断 | insufficient_evidence：夹爪未全区间持续闭合 |
| target 中心在 goal 可见 XY bounds 内 | false |
| 目标关系诊断 | insufficient_evidence |
| 持物/目标完成已验证 | false / false |
| 命名 oracle 导入尝试 | 0 |

第二帧夹爪已接近闭合，但第一帧不满足闭合条件，所以整个区间不能作为持物跟随证据。目标仍几乎静止，且目标中心远离手。这支持当前证据不足的结果；微小可见中心变化来自该仿真观测和分割，不是实际传感器精度声明。

报告：[回放结果与输入哈希](rgbd_temporal_replay_report_20261004.json)。两个当前帧的视觉绑定与原真实 query 的 snapshot、target/goal ID 校验一致。重复读同一帧只返回缓存副本，不能重复计数；变更 depth 或 handoff 后重用帧 ID 会拒绝。

## 测试与复现

完整 unittest **622 项通过**。八项新检查覆盖：三帧跟随候选不授权接触、静止目标不随手、静止闭手/开手不足、稳定开放后的粗略 goal 候选不授权支撑、目标丢失中断累计、移动相机/身份重新分配拒绝累计、缓存防篡改、错误 provenance 和 episode 切换拒绝。策略循环测试另检查新诊断写入 query trace。

```powershell
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' `
  scripts/recovery/skill_pipeline/replay_visual_temporal_diagnostics.py `
  --input-dir 'D:\大三上\科研\visual-policy-rollout-20261004' `
  --out-file 'D:\大三上\科研\temporal-replay-new.json'
```

输出文件必须未存在。原始 RGB-D/检测保存在上述本地目录，输入报告附 SHA-256。Guard 范围仍只有三个指定 oracle 模块导入，不等于任意 MuJoCo 内存访问审计。

## 后续工作

扩展真实 policy rollout 到接近、抓取、抬升和释放段，收集更长的当前可见轨迹，验证候选条件能否在实际正负案例中触发。随后结合目标 mask/点云变化、机器人运动和多相机证据，校准当前阈值并逐项解决 holding/goal verification，而不是依赖 benchmark done 或夹爪闭合单独判成功。
