# RGB-D recovery 调用边界：2026-10-07

## 本轮交付

原来的 `visual_policy_eval` 在 forced recovery query 只写入“refused”，随后继续 VLA 动作。本轮增加明确的 `--visual_recovery_admission` 模式：

1. 在线循环采集当前 RGB-D，完成 runner 查询和同步腕部观测保存。
2. 到达指定 query 时，实际调用 `RGBDRecoveryAdmissionController.recover`。
3. 控制器通过同一个 adapter 读取 runner、视觉 perceiver、视觉 client 的交接包，检查对象身份一致；provider 同时重验帧内容摘要。
4. 控制器返回视觉目标/目标区域候选 ID、snapshot ID 和具体缺失能力。
5. 当前能力不足时，在下一次 policy inference 和动作下发之前结束 episode，并保存终态帧。不会继续剩余 VLA action chunk。

原来的诊断模式仍可用于政策轨迹采集。新模式必须同时指定 `--visual_policy_eval` 和非负 `--force_recovery_query`；query 从 0 开始。若预算耗尽前没到指定边界，结果明确记录 `recovery_boundary_reached=false`，不能计作 recovery 试验。

这是**调用边界和准入拒绝的接线**。控制器没有环境或动作接口；未把旧 cuTAMP solver、旧 executor 或 oracle skill pack 接入视觉决策。仍禁止执行 skills，不表示生产 recovery 已迁移。

## 验证

- 34 项针对性测试：控制器、在线循环、runner 分流及诊断接口。检查早/晚边界、拒绝后停止推理和动作、实际步号、未到边界、变更同一步帧拒绝、无环境输入、CLI 参数及原诊断模式行为。
- 真实数据离线回放：`D:\大三上\科研\visual-policy-dual-query-20261004\frames\step000014`。这是 10 月 4 日采集数据，本轮没有启动服务器仿真。
- 输出：`D:\大三上\科研\visual-recovery-admission-20261007\replay.json`。
- 结果：snapshot `visual_policy_37451739767441809973470f03efecdd:step14:agentview`，目标候选 `obj_003`，放置对象候选 `obj_002`；detector 调用 1 次，三入口对象身份一致；拒绝执行，新增动作 0。
- 回放保存输入 SHA-256。三个已列明 oracle 模块的导入 guard 未触发；不代表所有依赖或全部内存访问都已审计。

仍缺：目标属性确认、抓取几何、放置区域与净空、持物/完成验证、视觉 cuTAMP problem adapter、已准入的 RGB-D skill pack、视觉 recovery executor。候选 ID 不证明语义或几何正确。

## 使用

在线评估在原 `--visual_policy_eval` 命令上增加：

```text
--visual_recovery_admission --force_recovery_query 1
```

该模式在 query 1 进入准入并退出；不应作为成功率实验。离线复核使用：

```powershell
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' scripts/recovery/skill_pipeline/replay_visual_diagnostic_interfaces.py --input-dir 'D:\大三上\科研\visual-policy-dual-query-20261004\frames\step000014' --out-file '<新的输出文件>' --recovery-admission
```

## 下一项实质工作

将任务 1 的 grasp profile 迁移成独立视觉候选 skill pack：逐项列出 body/site 名称、真值尺寸、本体局部坐标偏移和忽略碰撞对象的依赖；将能表达的项改为视觉 selector 和显式参考系，不能迁移的项拒绝准入。随后为视觉场景定义规划问题输入，使 cuTAMP 可以消费候选几何及未知区域。这两项完成前不开展 A/B/C 成绩统计。

迁移总进度仍按约三分之一估计，本轮不把“拒绝路径可运行”折算成“在线恢复已完成”。
