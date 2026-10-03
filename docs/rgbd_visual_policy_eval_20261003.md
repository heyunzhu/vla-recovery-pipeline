# 视觉状态下的策略诊断评测分支（2026-10-03）

## 本轮实现

正式 runner 新增显式 `--visual_policy_eval`。该分支要求 `--task_goal_source language_rgbd` 和真实 `--pretrained_path`，在旧 oracle skill 初始化/评测循环之前分派到 `visual_policy_loop.run_from_args`。与 `--visual_dry_run` 互斥。

它复用原有 OpenPI policy adapter、policy observation 构造和 action chunk 行为，但使用独立的视觉诊断循环与 trace。每次策略查询前，先从当前环境采集 RGB-D，通过共享 provider 获取视觉 handoff，记录 `VisualExecutionReadiness`；随后进行策略推理并只执行该策略的动作。动作须为有限的非空 `[N,7]` 数组。

没有把原真值循环的 target body pose、holding、contact、关节状态和位置历史字段补成零或可见中心；没有初始化原 recovery controller。旧 skill hooks、wrong-object/contact 等依赖真值的触发器不运行。当前支持显式 `--force_recovery_query` 测试请求拒绝：对应查询记录 `recovery_requested=true`、`recovery_decision=refused` 与 blockers，继续执行 VLA chunk。其他查询记录 `not_requested`。

这实现了**独立视觉诊断评测分支中的策略循环路由**，尚未替换旧正常 skill/recovery 循环，也不是可执行 RGB-D recovery。

## 检测交接

`ExternalFrameDetector` 在每个 query 的实际 env_step 建立新目录，保存 observation 与 summary，打印 `VISUAL_POLICY_FRAME_READY`。环境在等待检测时保持当前状态；外部冻结模型处理该帧、上传 `detector`，最后写 READY。每帧执行 config/prompt/image size、detector ID、metadata/RGB 摘要校验，整段 episode 的 config 必须不变。

超时、配置改变或帧不匹配直接终止评测并写 `abort.json`，不进入 oracle fallback。策略输出无效或 query 写入失败时，当前 chunk 不执行。env 与可关闭的 policy 在 finally 中清理。

provider 的 backend ID 是外部 artifact 包装器标识；trace 中另记 `artifact_detector_id`，避免将包装器 ID 当作模型 ID。

## 输出与判断范围

- `visual_query_trace.jsonl`：版本化视觉诊断记录，包含 snapshot、视觉绑定、readiness、请求/拒绝决策与缺失的 oracle 字段。
- `frames/stepXXXXXX/`：每个实际 query 的 RGB-D 与检测文件。
- `episode.json`：policy/settle/recovery 动作计数、query 数、checkpoint、配置和 benchmark done。
- `abort.json`：遇到错误时的失败记录，明确 `oracle_fallback=false`。

这些 trace 使用 `trace_kind=visual_policy_diagnostic`，不是旧 `make_query_record` 的 oracle trace。暂未接入旧统计器和视频路径。`benchmark_done` 来自环境 step 的 done，仅供 benchmark 评测；`visual_success_verified=false` 明确表示尚无视觉成功验收，不能把 done 称为视觉 recovery 成功。

## 验证与当前运行条件

完整 unittest **608 项通过**，新增八项检查：

1. 强制 recovery 被拒绝后，策略 chunk 继续；5 步动作在 env_step 0/2/4 形成三次视觉 query。
2. 检测失败在策略动作前停止。
3. 非有限策略动作在执行前拒绝。
4. benchmark done 与视觉成功验收分开记录。
5. 正式 runner 提前分派新分支，不进入旧初始化。
6. 必须指定 checkpoint，禁止 skill 模式。
7. 外部 detector 校验配置并拒绝 episode 内配置变化。
8. detector 超时明确失败。

策略循环测试使用受控 fake policy/env 验证控制流，不能替代真实 VLA rollout。上一轮服务器在线验证仍只验证无策略动作的 held-frame dry-run。

本轮只读确认：个人目录存在 `/mnt/sdb/24_yyx/models/pi0_libero_openpi`，含 params、assets 和 DOWNLOAD_COMPLETE 标记；没有逐一重新验证模型文件。服务器有 `openpi-jax` 与 `libero-official` 分立环境；已验证 `libero-official` 当前没有 openpi/jax。现有 policy subprocess adapter使用同一 Python 环境，因此真实评测需先解决 OpenPI/LIBERO 共存或跨 Python worker，不能直接使用该 LIBERO 环境启动新分支。

本次 GPU 检查中 0–7 全部有约 19–37 GB 显存占用，利用率约 35–100%，没有启动 GPU 任务。因此**本轮未完成真实 checkpoint 的服务器 rollout**，没有新增成功率结果。

## 复现配置

在同时具备 LIBERO、OpenPI 和 checkpoint 的个人环境中：

```bash
python -m experiments.robot.libero.skill_pipeline.runner \
  --visual_policy_eval --task_goal_source language_rgbd \
  --pretrained_path /mnt/sdb/24_yyx/models/pi0_libero_openpi \
  --task_suite_name libero_spatial --task_ids 1 --episode_index_start 1 --seed 11 \
  --visual_prompts_json /path/to/frozen_prompts.json \
  --visual_output_dir /path/to/new-output \
  --visual_resolution 512 --visual_policy_max_steps 8 --action_chunk 4 \
  --num_steps_wait 10 --force_recovery_query 0
```

只支持 ordinary spatial/object/goal 的一个显式任务、一个 trial、普通 task language；禁止 skills/mining、依赖真值的 diagnostics、视频和 generated/Pro 配置。输出目录须未存在。每个新 frame 都需生成匹配的检测 artifact，不能复用上一 query 的 metadata。

下一步先处理个人环境中 OpenPI/LIBERO 的运行桥接；有空闲 GPU 后运行短程真实策略验证，检查多 query 的检测交接和 refusal trace。视觉 grasp、支撑区域、持物及成功验收仍需逐项补证据，恢复动作继续禁止。
