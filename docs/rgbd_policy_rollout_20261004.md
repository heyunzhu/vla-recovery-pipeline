# 真实环境 8 步视觉策略诊断（2026-10-04）

## 本轮完成

从正式 `skill_pipeline.runner --visual_policy_eval` 入口，在个人服务器 LIBERO 环境运行 task 0 / init 1 / seed 11，先静置 10 步，然后由真实 Pi0 checkpoint 执行 8 步策略动作。每个 action chunk 长度为 4，因此形成 env_step 10、14 两次视觉查询；每次都重新采集当前 RGB-D，运行本地冻结 Grounding DINO/SAM2，再将匹配 artifact 回传服务器。

Pi0 在独立 OpenPI Python 3.11 worker 中使用 CPU；LIBERO 主进程使用 Python 3.8。限制到 8 个逻辑 CPU 核，OMP/OpenBLAS/MKL 线程数为 1，策略 worker 无 GPU 可见性。仿真沿用 EGL 渲染。任务在个人 tmux 中运行，已结束，环境和模型 worker 已关闭。

## 实际结果

| 项目 | 结果 |
| --- | --- |
| 真实 checkpoint | `pi0_libero_openpi`，权重实际加载 |
| 静置动作 | 10 |
| 策略动作 | 8 |
| recovery 动作 | 0 |
| policy/视觉 query | 2，env_step 10 和 14 |
| 两次模型动作输出 | 都为有限的 50×7，输出随观测改变 |
| 每次执行的 chunk | 前 4 步 |
| 两次 detector 配置 | 相同：`grounded-sam2-a62b7dbfbf7a` |
| 每帧检测实例 | 4 |
| 两次感知状态 | `visual_id_candidate` |
| target / goal ID | 两次均为 `obj_002` / `obj_003` |
| 第 0 次强制 recovery | requested=true，decision=refused |
| 第 1 次 recovery | not_requested |
| planning / execution readiness | 两次均 false / false |
| 命名 oracle 模块导入尝试 | 0 |
| benchmark done | false |
| visual success verified | false |

第一段 4 步动作后，两帧时间戳从 0.50 秒到 0.70 秒，RGB、深度均发生变化，固定相机的 K 和外参保持相同。本体末端位置变化向量为 `[0.008284, 0.006633, 0.002251]` 米，位移约 **10.85 mm**。该位移对应两次 query 之间的 4 步，不能解释为全部 8 步的末端位移；最后第 18 步未另存 RGB-D。

本次确认真实策略动作执行后，循环能够采集新帧、重新检测并再次推理；recovery 请求拒绝后，仍由 VLA 控制。绑定颜色仍未核验，支撑/抓取/持物/完成验证未满足，恢复动作继续禁止。这段 8 步短程实验没有完成任务，也没有恢复成功率。

## 证据

- [原始 episode 结果](rgbd_policy_rollout_episode_20261004.json)：实际动作计数、checkpoint、worker metadata、范围标记。
- [两条原始 query trace](rgbd_policy_rollout_query_trace_20261004.jsonl)：视觉绑定、缺失字段、阻塞项与 recovery 拒绝。
- [本地核验摘要和产物哈希](rgbd_policy_rollout_audit_20261004.json)：两帧变化、模型输出 shape/有限性、动作与拒绝记录、worker close ACK、全部保存文件的 SHA-256。
- [部署源码哈希](rgbd_policy_rollout_source_sha256_20261004.json)：上传后核验 25 个源码文件。

本轮没有修改评测源码，使用已提交 `cd9a054` 的代码。既有完整测试为 614 项，上轮已通过；本轮完成真实环境集成验证，没有重复运行不变的单元测试。

Guard 的证据仅覆盖既定三个 oracle 模块的导入，不等于全进程所有 MuJoCo 内存访问审计。相机/深度标定及本体观测通过 sensor 读取，环境 done 用于 benchmark 范围记录。

## 产物与复现

- runtime：`/mnt/sdb/24_yyx/projects/visual-policy-rollout-runtime-20261004`
- 服务器数据：`/mnt/sdb/24_yyx/demo/visual-policy-rollout-20261004`
- 本地完整数据：`D:\大三上\科研\visual-policy-rollout-20261004`
- 本地源码包：`D:\大三上\科研\visual_policy_rollout_runtime_20261004.zip`
- 包 SHA-256：`61b08af7468db093740039d08be81b442d81ab18cf8a3f462aecba948652101b`

复现时使用未存在的输出目录：

```bash
taskset -c 0-7 env OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  LIBERO_CONFIG_PATH=/mnt/sdb/24_yyx/config/libero \
  PYTHONPATH=/mnt/sdb/24_yyx/projects/LIBERO-f78abd68ee283de9f9be3c8f7e2a9ad60246e95c:/mnt/sdb/24_yyx/projects/visual-policy-rollout-runtime-20261004 \
  /mnt/sdb/24_yyx/envs/libero-official/bin/python -u \
  -m experiments.robot.libero.skill_pipeline.runner \
  --visual_policy_eval --task_goal_source language_rgbd \
  --task_suite_name libero_spatial --task_ids 1 --episode_index_start 1 --seed 11 \
  --num_steps_wait 10 --action_chunk 4 --visual_policy_max_steps 8 \
  --pretrained_path /mnt/sdb/24_yyx/models/pi0_libero_openpi \
  --visual_policy_python /mnt/sdb/24_yyx/envs/openpi-jax/bin/python \
  --visual_prompts_json frozen_prompts.json --visual_resolution 512 \
  --visual_output_dir /mnt/sdb/24_yyx/demo/visual-policy-rollout-new --force_recovery_query 0
```

在 runtime 目录执行，并使用 tmux 保存会话。收到每个 `VISUAL_POLICY_FRAME_READY` 后，取回对应 observation，使用冻结模型和 prompts 运行 `run_grounded_sam2_snapshot.py`，上传 detector，最后写 READY。第二帧必须重新检测，不能复用第一帧 metadata。

## 现在可以汇报

“已完成 RGB-D 视觉诊断分支与真实 Pi0 策略的短程联调：在 LIBERO 中执行 8 步策略动作，完成两次动作前后的 RGB-D 采集、冻结检测和视觉状态查询，验证 recovery 请求被拒绝后策略仍可继续运行。目前目标实例在两次查询中一致，完整 recovery 的视觉抓取、持物和目标完成验证仍在推进，尚未报告恢复成功率。”

下一步扩展连续观测，并补持物与目标完成判断所需的视觉证据，逐步缩小当前恢复阻塞项。
