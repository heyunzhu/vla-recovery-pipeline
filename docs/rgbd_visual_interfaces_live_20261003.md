# 视觉诊断接口在线验证（2026-10-03）

## 结果

已在 5880 服务器的个人环境，通过正式 `skill_pipeline.runner` 入口重新运行 task 0 / init 1 / seed 11 / 512 分辨率的视觉 dry-run。环境先执行 10 步静置，然后保持当前帧；本地 CPU 运行固定版本 Grounding DINO + SAM2，完整回传冻结检测 artifact 后，服务器读取并核验，再次从保持的环境获取 RGB-D。

本次实际调用 `CuTAMPVisualDiagnosticPerceiver.perceive`、`VisualDiagnosticRobotClient.get_scene` 和 `check_execution_readiness`；验证与正式 runner 的 task binding / 状态查询共享 handoff，最后调用客户端动作入口并确认拒绝。不是上一轮离线回放的重述。

| 检查 | 实测 |
| --- | --- |
| 正式入口 | `skill_pipeline.runner` |
| runner 视觉 task/query 路由 | true |
| 新视觉诊断类路由 | true |
| task/query/perceiver/client handoff | 共享同一对象 |
| 感知状态 | `visual_id_candidate` |
| target / goal | `obj_002` / `obj_003` |
| detector backend | `grounded-sam2-a62b7dbfbf7a` |
| 模型产生检测 | 4 个实例 |
| 共享 provider detector 调用 | 1 次 |
| planning / execution allowed | false / false |
| client 动作请求 | 拒绝 |
| 检测等待期间环境推进 | false |
| policy / recovery 动作 | 0 / 0 |
| 命名 oracle 模块导入尝试 | 0 |
| 正常 VLA 评测循环接入 | false |
| 完整生产 recovery 接入 | false |

报告：[服务器原始结果](rgbd_visual_interfaces_live_report_20261003.json)。

执行阻塞项仍为：诊断模式、旧 SceneState 不可用、目标属性未核验、物体几何与抓取未确定、目标区域与净空未确定、持物与目标完成验证未确定。实例匹配成功不能授权恢复动作；这里没有恢复成功率。

Guard 只拦截既定三个 oracle 模块导入，并不证明任意 MuJoCo 状态访问均已审计。相机标定、深度转换、时钟与白名单机器人本体信息由 sensor 读取。

## 采集身份修正

之前 live canary 的 episode 字符串只包含 suite/task/init，同一配置多次运行会重复。本轮为每次采集增加 seed 和随机 UUID，使独立运行的帧身份不同，旧检测 metadata 无法直接通过新帧身份检查。固定 seed 不保证跨 episode 的跟踪 ID 延续；各次运行使用新 provider。

本次 snapshot：

```text
libero_spatial_task0_init1_seed11_visual_dry_run_6dc614e846b44de880b09337b61aa1a0:step10:agentview
```

## 产物与复现

- 个人服务器 runtime：`/mnt/sdb/24_yyx/projects/visual-interfaces-runtime-20261003`
- 个人服务器输出：`/mnt/sdb/24_yyx/demo/visual-interfaces-live-20261003`
- 本地数据：`D:\大三上\科研\visual-interfaces-live-20261003`
- 源码包：`D:\大三上\科研\visual_interfaces_runtime_20261003.zip`
- 包 SHA-256：`21b8137a9b1983c7b4d222e896b93bb08cc68c52d55d54fd3ed9d0288c9bbbcd`

上传后核验源码包及 20 个源码文件 SHA-256，见 [源码清单](rgbd_visual_interfaces_live_source_sha256_20261003.json)。只在个人新目录部署，没有修改共享环境或同学的 checkout。服务器命令退出码为 0，环境已关闭，没有遗留运行任务。

```bash
cd /mnt/sdb/24_yyx/projects/visual-interfaces-runtime-20261003
LIBERO_CONFIG_PATH=/mnt/sdb/24_yyx/config/libero \
PYTHONPATH=/mnt/sdb/24_yyx/projects/LIBERO-f78abd68ee283de9f9be3c8f7e2a9ad60246e95c:/mnt/sdb/24_yyx/projects/visual-interfaces-runtime-20261003 \
/mnt/sdb/24_yyx/envs/libero-official/bin/python -u \
  -m experiments.robot.libero.skill_pipeline.runner \
  --visual_dry_run --task_goal_source language_rgbd \
  --task_suite_name libero_spatial --task_ids 1 --episode_index_start 1 --seed 11 \
  --visual_resolution 512 --num_steps_wait 10 --visual_prompts_json frozen_prompts.json \
  --visual_output_dir /mnt/sdb/24_yyx/demo/visual-interfaces-live-new-run
```

输出目录必须未存在。收到 `VISUAL_FRAME_READY` 后，取回该 observation，用已固定权重和 prompt JSON 运行 `run_grounded_sam2_snapshot.py`，把该帧 detector 目录上传完整，最后写 `detector/READY`。超时为 600 秒。不能用旧运行的检测文件代替新帧结果。

本轮完整 unittest **600 项通过**。正常 VLA/recovery 评测循环还没有消费新 readiness；下一步需要显式视觉模式中的控制路由和拒绝记录，保持缺失证据不回退 oracle 的边界，再逐项补可执行恢复的视觉条件。
