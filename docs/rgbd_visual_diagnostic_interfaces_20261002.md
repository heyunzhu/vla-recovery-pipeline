# cuTAMP 视觉诊断接口（2026-10-02）

## 本轮推进

新增 `tiptop_repro.visual_diagnostic_interfaces`，提供两个独立的诊断接口：

| 原接口 | 新诊断入口 | 当前输出 |
| --- | --- | --- |
| `CuTAMPV2OraclePerceiver.perceive(env, obs, ...)` | `CuTAMPVisualDiagnosticPerceiver.perceive(frame=..., task_description=...)` | `VisualRecoveryHandoff` |
| `LiberoRobotClient.get_scene()` | `VisualDiagnosticRobotClient.get_scene(frame=..., task_description=...)` | 同一 `VisualRecoveryHandoff` |
| 原客户端动作执行 | `VisualDiagnosticRobotClient.step(action)` | 无条件抛出 `PermissionError` |

两个新接口只接收明确的 `RGBDObservation` 与任务语言，复用共享 `VisualDryRunAdapter`。不接 env、holding latch、oracle ParsedTask 或 SceneState；旧位置参数调用和混合输入直接拒绝。执行入口不会读取或转发 action，也没有环境句柄和动作回调。

`check_execution_readiness` 返回冻结的 `VisualExecutionReadiness`，包含快照身份、感知状态和 blockers。`planning_allowed`、`execution_allowed` 必须为 false，不能构造授权结果。当前始终包含 `diagnostic_mode` 和 `legacy_scene_state_unavailable`，并附带视觉 handoff 中未满足的检查项。

这两个类不是旧六元组 perceiver 与 SceneState 客户端的可直接替换实现。原 `CuTAMPV2TipTopController` 的 normal recovery 路径仍未接入，不能把新类注入旧 controller 后执行规划。本轮没有生成 TAMPProblem、抓取位姿、碰撞模型或持物成功信号。

## 验证结果

用上一轮服务器正式 runner 采集的 task 0 / init 1 / seed 11 / 512 RGB-D 和冻结检测文件，在独立本地进程中回放。回放程序在导入视觉消费者前启用命名 oracle 模块 guard，校验 detector config、ID、帧 metadata 和 RGB 摘要；输出另附输入文件 SHA-256。

| 项目 | 回放结果 |
| --- | --- |
| 数据来源 | `runner-visual-dry-run-20261002` |
| 感知状态 | `visual_id_candidate` |
| target / goal | `obj_002` / `obj_003` |
| runner task/query、perceiver、client | 同一 handoff 与 binding |
| detector 调用 | 1 次（读取冻结检测结果） |
| action 请求 | 拒绝 |
| planning / execution | false / false |
| 命名 oracle 模块导入尝试 | 0 |
| 本轮创建仿真 / 执行恢复 | 否 / 否 |

本帧 blockers 为：诊断模式、旧 SceneState 不可用、目标属性未核验、物体几何与抓取未确定、目标区域与净空未确定、持物与成功验证未完成。可见点中心不转换为物体 body pose，缺失字段不补真值。

证据：[回放结果与数据哈希](rgbd_visual_interfaces_replay_20261002.json)。guard 仅保护既定三个 oracle 模块导入，不是任意 MuJoCo 内存访问审计。

live canary 脚本已改为调用这两个新类并记录 readiness，但本轮没有重跑服务器。前一轮服务器结果仍对应提交 `2116a86` 之前的 adapter 接口验证；不能把旧服务器结果当成本轮 live 接口验证。

## 复现

在仓库根目录运行：

```powershell
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' `
  scripts/recovery/skill_pipeline/replay_visual_diagnostic_interfaces.py `
  --input-dir 'D:\大三上\科研\runner-visual-dry-run-20261002' `
  --out-file 'D:\大三上\科研\visual-interfaces-replay-new.json'
```

输出文件须不存在。此命令使用已冻结的检测结果，不运行新模型、不创建仿真、不测恢复成功率。

完整 skill-pipeline unittest **600 项通过**。本轮六项新测试覆盖共享读取与阻塞项、旧签名/环境输入提前拒绝、动作不读取不转发、深度变化使缓存失效、检测错误不回退和实例冲突拒绝、readiness 不可授权。全套 oracle 测试也继续通过；由于它们会加载 oracle 模块，guard 的独立进程验证由上述回放完成。

## 后续工作

1. 用更新后的正式 runner dry-run 在服务器验证两个新类与重新采集帧的在线读取；保存独立目录和源码哈希。
2. 让正常评测循环在显式视觉模式中记录这种诊断 readiness，遇到 blockers 时保留 VLA 控制或交给明确的人工路径，不能自动回退 oracle recovery。
3. 逐项补持物/目标验证、可用目标区域和抓取几何的视觉证据，再设计支持这些证据的 planner/executor。完成这些条件之前，继续禁止视觉恢复动作。
