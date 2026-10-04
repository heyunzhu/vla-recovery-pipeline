# 2026-10-04：48 步同步双相机实验启动与连接中断

## 当前状态

为覆盖夹爪接近和遮挡阶段，已启动新的 48 步真实 Pi0 实验，复用上轮通过真实验证的逐查询双相机 runtime。27 个源码文件在服务器再次通过哈希检查。使用 CPU 策略推理，CPU affinity 为 0–7，冻结本地 CPU 检测每 4 步交接一次；检查时八张 GPU 都有任务，未启动 GPU 训练或策略推理。

实验尚未完成核验：

- 第 10、14、18 步的当前固定相机检测已实际完成并成功交接，三次均未触发场景拒绝。
- 第 22 步固定相机观测已完整下载，metadata 中 episode 为 `visual_policy_482262864e4f406ab823671d8f1ff841`，env_step=22，时间戳约 1.10 秒。
- 下载该步 summary.json 时 SSH 超时，relay 中止，尚未为第 22 步发送检测或 READY。
- 随后 SSH 连接及 TCP 22 端口检查仍超时，无法核验远端最终状态、完整 wrist 数据、episode 结果或 worker 退出。

**不能将这次运行报告为完成 48 步或完成 12 组双相机采集，也没有 recovery、持物或任务成功结论。** 服务器检测等待超时设为 600 秒；远端可能仍在等待，也可能已经超时中止，必须在恢复连接后读取状态。

## 断线期间完成的代码

1. 新增 `diagnose_query_cross_view.py`，按查询读取同步固定相机和腕部 RGB-D，将当前原始物体检测 mask 投影到腕部视角，报告图像外、无效深度、深度一致及遮挡状态。原类别冲突保持不变，不运行腕部物体检测或身份融合。预设 2/5/10 mm 三种容差。
2. 用上轮已完整核验的 8 步双相机数据检查该 CLI，完成两个查询、三种容差共六组投影；这只是脚本 canary，不属于此次 48 步轨迹结果。产物保存在 `D:\大三上\科研\dual-query-cross-view-canary-20261004`。
3. relay 增加 SSH/SCP exit code 255 的最多三次重试及连接保活设置，其他远程命令错误直接抛出。重试仍不能绕过持续网络故障，也不会忽略检测错误。
4. 三项针对性测试通过：暂时的传输失败后继续、远程命令 exit code 1 不重试、连续传输失败在三次后停止。新投影脚本的编译检查通过。

没有更改服务器已运行的 runtime；新 relay 修复会在下次续接时使用。本轮没有修改全局环境或其他用户文件。

## 部分证据与路径

- [已交接步数、缺失产物和部分文件哈希](rgbd_dual_48_interrupted_audit_20261004.json)
- 本地部分产物：`D:\大三上\科研\visual-policy-dual-48-20261004`。
- 服务器输出：`/mnt/sdb/24_yyx/demo/visual-policy-dual-48-20261004`。
- runtime：`/mnt/sdb/24_yyx/projects/visual-policy-dual-query-runtime-20261004`。
- 实验 tmux：`visual-dual-48-20261004`。
- 日志：`/mnt/sdb/24_yyx/visual-policy-dual-48-20261004.log`。
- 启动文件：`D:\大三上\科研\run_visual_policy_dual_48_20261004.sh`。

## 连接恢复后的续接

先读取服务器 abort.json/episode.json、日志和 tmux 状态，并核对第 22 步 metadata/RGB 哈希及 READY 是否存在。

- 若同一 episode 仍暂停等待第 22 步 detector，使用 `relay_visual_policy_detector.py --resume-step 22 --max-steps 48` 配合相同 host、路径、冻结 prompts 和模型参数续接；必须完成该当前帧检测，不能跳过。
- 若已超时中止，保存本次 abort、trace 和 worker 信息，使用新的输出目录重新启动，不能往已中止轨迹追加动作或伪造同步腕部观测。
- 若 episode 已结束，先取回完整目录核验实际动作计数和所有查询相机，再决定是否需要补采。

完整采集后运行 `audit_visual_query_camera_pairs.py` 核对双相机同步、更新、策略输出和退出记录，再运行新的逐查询投影脚本分析同一步的遮挡区域。
