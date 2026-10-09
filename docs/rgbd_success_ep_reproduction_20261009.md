# 酒瓶放盘子成功样例：完整命令、分支与提交

日期：2026-10-09。平台：启智 `可上网GPU资源`，仅使用 `xinghanbo-eval`。

## 对应分支与 commit

- 仓库：<https://github.com/heyunzhu/vla-recovery-pipeline>
- 分支：`feature/rgbd-recovery`。
- 本轮视觉恢复代码与实验记录提交：`31e7cd387a63f1c19abfb135d30cde2e948a2fc2`。
- 提交标题：`feat: validate RGB-D recovery anchor without oracle object state`。
- 获取该版本：

```bash
git clone --branch feature/rgbd-recovery https://github.com/heyunzhu/vla-recovery-pipeline.git
cd vla-recovery-pipeline
git checkout 31e7cd387a63f1c19abfb135d30cde2e948a2fc2
```

**版本归属说明：**上述提交是在成功实验结束后整理提交的代码版本。实际成功运行先于该提交，使用下面的历史冻结 runtime 加独立视觉代码副本。不能把该 commit 描述为唯一的运行环境，也不能仅 checkout 后直接替代冻结 runtime。

历史 runtime 的来源 HEAD 是 `7128c1ea6280c227e48561e621fe9da8604c5a6d`；冻结时有未提交的 `runner.py`、`cutamp_runner_py310_overlay.sh` 修改及新增脚本。准确依赖是保存的 `runtime_repo`，不是裸 checkout 该历史 HEAD。来源记录在真值成功目录的 `historical_environment.txt`，关键文件哈希在 `source_sha256.txt`。

## 哪个成功样例

| 项目 | 配置 |
| --- | --- |
| Suite / task | `libero_goal_task` / task04（1-based，底层 task_id=3） |
| 实际语言 | `Put the wine bottle on the plate` |
| Episode / init | ep00 / init_state_idx=0 |
| Episode seed / base seed | 1 / 90 |
| 原策略触发恢复 | query_idx=5，控制步35 |
| 技能 | `wine_bottle_plate_wrong_object_handoff` |

有两种已成功运行，不要混淆：

1. **真值完整 ep**：从任务开始运行 Pi0，原技能自然触发恢复，完成任务。
2. **最终 RGB-D 恢复重放**：从该 ep 保存的恢复入口物理状态开始，不加载 Pi0，执行视觉恢复。物体类别、实例ID、几何、运行位置与完成判据来自视觉/本体信息；仿真 reward/done 向恢复屏蔽，最终真值只作为评测标签。

最终 RGB-D 结果不是从任务开头跑完的纯视觉 VLA ep，也没有对完整控制器内部状态做逐步确定性恢复。入口开放夹爪的控制指令按测量重建。

BDDL 文件名仍是 `put_the_bowl_on_the_plate.bddl`，因为历史 swap benchmark 将目标换成了酒瓶。请保留下面原始路径，不要凭文件名替换成另一个任务。

## 服务器前提

以下命令均在 `xinghanbo-eval` 的 Linux 终端执行。不要覆盖已成功的实验目录；下面用新的时间戳输出目录。

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
HIST=$ROOT/logs/continual_skill_core60_pilot_20261006
REPO=$HIST/runtime_repo
```

需要保留的资产（不随 Git checkout 提供）：

- `$HIST/runtime_repo`、`$HIST/core60_entrypoint.py`、`$HIST/cutamp_flock.sh`、`$HIST/libero_config`、`$HIST/bddl_files`。
- `$HIST/checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918`：冻结 C4 技能包。
- `$ROOT/envs/rlinf-openpi`：仿真/Pi0 Python 3.11；`$ROOT/envs/tiptop-planning-py310`：检测/规划 Python 3.10。
- `$ROOT/third_party/LIBERO-PRO`、`$ROOT/third_party/cuTAMP`、`$ROOT/third_party/curobo`。
- 真值完整 ep 需要 `$ROOT/models/pi0_libero_openpi`。
- RGB-D 需要 `$ROOT/logs/rgbd_exact_box_20261008/pydeps` 以及其中模型目录 `models/grounding-dino-tiny`、`models/sam2.1-hiera-tiny`。
- RGB-D 需要 `$ROOT/logs/rgbd_bottle_geometry_recovery_20261009/static_panda_model`，含已核验机器人 XML/网格。
- RGB-D 起点：`$ROOT/logs/rgbd_obstacle_recovery_20261009/replay_fixture`，含 `initial_physics_state.npy` 与 `config.json`；其状态是 benchmark 初始条件，不是感知输入。
- 完整成功副本：`$ROOT/logs/rgbd_visual_ids_replay_v3_20261009`，含 `visual_code`、`capture_support`、`distractor_prompts.json`。

## A. 真值完整 ep 的完整命令

原成功目录为 `$ROOT/logs/oracle_anchor_wine_plate_20261009`，其中 `run.sh` 保存了实际启动命令。以下保留其参数，只换成新的输出目录并显式创建目录。

```bash
set -euo pipefail
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
HIST=$ROOT/logs/continual_skill_core60_pilot_20261006
REPO=$HIST/runtime_repo
RUN=$ROOT/logs/oracle_anchor_wine_plate_repro_$(date +%Y%m%d_%H%M%S)
mkdir "$RUN"
export ROOT CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
export LIBERO_CONFIG_PATH=$HIST/libero_config
export XLA_PYTHON_CLIENT_PREALLOCATE=false XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
export PYTHONPATH=$REPO:$ROOT/third_party/LIBERO-PRO
export OMP_NUM_THREADS=2
export CUTAMP_FLOCK_LOCK=$RUN/cutamp.lock
export CUTAMP_REAL_RUNNER=$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
cd "$REPO"
set +e
timeout 1800 "$ROOT/envs/rlinf-openpi/bin/python" "$HIST/core60_entrypoint.py" \
 --pretrained_path "$ROOT/models/pi0_libero_openpi" --config_name pi0_libero \
 --task_suite_name libero_goal_task --task_ids 4 --num_trials_per_task 1 \
 --episode_index_start 0 --episode_seed_start 1 --seed 90 --policy_in_process --save_video \
 --openvla_repo_root "$REPO" --task_language_source bddl --engine_language_source bddl \
 --max_recovery_calls 2 --max_recovery_steps 200 --max_replans 1 \
 --log_dir "$RUN" --exp_name run --enable_mining_skills \
 --skill_pack "$HIST/checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918" \
 --use_real_cutamp_backend --real_cutamp_require_feasible --real_cutamp_curobo_plan \
 --real_cutamp_serialize_trajectories --prefer_real_cutamp_executable_plan \
 --require_real_cutamp_executable_plan --real_cutamp_grasp_dof 6 \
 --real_cutamp_runner_python "$HIST/cutamp_flock.sh" --real_cutamp_runner_timeout_sec 900 \
 --real_cutamp_debug_dir "$RUN/cutamp_debug" > "$RUN/driver.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$RUN/exitcode.txt"
date -u +%Y-%m-%dT%H:%M:%SZ > "$RUN/finished_utc.txt"
echo "RUN=$RUN exit=$rc"
exit "$rc"
```

这次保存的成功结果：query5/步35触发1次恢复；16个可行候选；抓取、闭爪和放置执行成功；episode success=true，abort=false，exit=0。后端66.577秒。详细证据见 [真值锚点记录](oracle_recovery_anchor_wine_plate_20261009.md)。

## B. 最终 RGB-D 恢复的完整命令

下面从**实际成功的冻结视觉副本**复制支持代码，保留全部实跑环境变量与入口参数。它是精确来源明确的推荐复现方式。不要直接再次运行原成功目录的 `run.sh`：程序要求新的 snapshots/visual_execution 输出目录。

```bash
set -euo pipefail
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
HIST=$ROOT/logs/continual_skill_core60_pilot_20261006
REPO=$HIST/runtime_repo
SOURCE=$ROOT/logs/rgbd_visual_ids_replay_v3_20261009
RUN=$ROOT/logs/rgbd_visual_ids_repro_$(date +%Y%m%d_%H%M%S)
mkdir "$RUN"
cp -a "$SOURCE/visual_code" "$RUN/visual_code"
cp -a "$SOURCE/capture_support" "$RUN/capture_support"
cp "$SOURCE/distractor_prompts.json" "$RUN/distractor_prompts.json"
export ROOT CUDA_VISIBLE_DEVICES=0 MUJOCO_GL=egl PYOPENGL_PLATFORM=egl
export LIBERO_CONFIG_PATH=$HIST/libero_config
export XLA_PYTHON_CLIENT_PREALLOCATE=false XLA_PYTHON_CLIENT_MEM_FRACTION=0.50
export PYTHONPATH=$REPO:$ROOT/third_party/LIBERO-PRO
export OMP_NUM_THREADS=2
export ORACLE_ENTRYPOINT=$HIST/core60_entrypoint.py
export ANCHOR_CAPTURE_DIR=$RUN/snapshots
export ANCHOR_DIAGNOSTIC_HOOK=$RUN/capture_support/visual_selection_oracle_geometry_hook.py
export ANCHOR_VISUAL_CODE=$RUN/visual_code
export ANCHOR_PROPRIO_HAND_STATE=1
export ANCHOR_RGBD_OBSTACLES=1
export ANCHOR_VISUAL_EXECUTOR=1
export ANCHOR_VISUAL_IDS=1
export ANCHOR_SAVE_REPLAY_FIXTURE=1
export ANCHOR_REPLACE_BOTTLE_GEOMETRY=1
export ANCHOR_REPLACE_PLATE_GEOMETRY=1
export CUTAMP_FLOCK_LOCK=$RUN/cutamp.lock
export CUTAMP_REAL_RUNNER=$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
cd "$REPO"
set +e
"$ROOT/envs/rlinf-openpi/bin/python" \
 "$RUN/visual_code/scripts/recovery/skill_pipeline/replay_anchor_recovery.py" \
 --fixture "$ROOT/logs/rgbd_obstacle_recovery_20261009/replay_fixture" \
 --bddl "$HIST/bddl_files/libero_goal_task/put_the_bowl_on_the_plate.bddl" \
 --run-dir "$RUN" --capture-every 5 --restore-open-gripper-command \
 --evaluation-done-only > "$RUN/driver.log" 2>&1
rc=$?
printf '%s\n' "$rc" > "$RUN/exitcode.txt"
echo "RUN=$RUN exit=$rc"
exit "$rc"
```

`ORACLE_ENTRYPOINT`、`ANCHOR_SAVE_REPLAY_FIXTURE` 是保留原实跑脚本的环境项；此重放入口不加载 Pi0 或调用原 oracle entrypoint。`capture_support/anchor_sensor` 是必要的独立传感器包，不能只复制主 hook。完整视觉版本必须同时启用上述六个替换开关，并保留 `--evaluation-done-only`。

这次实际结果：13个可行候选，求解33.883512秒，154个恢复环境步，恢复success=true，最终仿真评测success=true，exit=0。110个执行状态含初始拟合1个和当前深度更新109个；碰撞问题含1个瓶子、2个支撑面和479个静态盒，来源全部RGB-D。

## 结果检查与冻结源码

新运行结束后，把下面的 `RUN` 改成终端打印的新目录，执行：

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$ROOT/logs/rgbd_visual_ids_replay_v3_20261009
"$ROOT/envs/rlinf-openpi/bin/python" - "$RUN" <<'PY'
import json
import sys
from pathlib import Path
p = Path(sys.argv[1])
r = json.loads((p / "replay_result.json").read_text())
assert (p / "exitcode.txt").read_text().strip() == "0"
assert r["recovery_success"] and r["final_simulator_success_for_evaluation"]
assert r["simulator_reward_done_hidden_from_recovery"]
assert r["initial_state_exactly_restored"] and not r["policy_loaded"]
assert r["gripper_command_reconstructed"] and not r["full_controller_checkpoint_restored"]
problems = list((p / "cutamp_debug").glob("*.problem.json"))
assert problems
for f in problems:
    problem = json.loads(f.read_text())["problem"]
    for group in ("movables", "surfaces", "statics"):
        for obj in problem[group]:
            assert obj["geometry"]["source"].startswith("rgbd_"), obj["name"]
            assert obj["name"].startswith("rgbd_") or obj["name"] == "table"
associations = list(p.glob("hybrid_association_step*.json"))
assert associations
for f in associations:
    assert json.loads(f.read_text())["oracle_body_association_used"] is False
print({k: v for k, v in r.items() if k != "attempts"})
PY
```

可行候选数、规划耗时和环境步数受随机求解/机器负载影响，不要求新运行与原结果完全一致；检查完整恢复和评测成功，不能仅检查feasible=true。

原始命令、冻结源码、采样、问题/结果和执行记录保存在：

- 服务器成功目录：`$ROOT/logs/rgbd_visual_ids_replay_v3_20261009`。
- 服务器完整压缩包：`$ROOT/logs/rgbd_visual_ids_evidence_20261009.zip`。
- 本地完整压缩包：`analysis_outputs/proprio_migration_20261009/visual_ids_evidence.zip`。
- 压缩包 SHA256：`cd1bbf9ab2cdce925a1e7ea40e27a3969da12097ad60708cc9a8764559af0e6b`。
- 原成功 hook SHA256：`e8417e7c0a2e9c1f9462710202a87793ab411d5e118397f8275355bcbc6c5871`。提交版本更新了说明文字；实际成功副本的字节来源以此哈希和压缩包为准。
- 迁移过程、失败诊断及适用边界：[完整实验记录](rgbd_recovery_proprio_and_execution_20261009.md)。

当前结论限于这个任务/seed/init，依赖直立可辨识瓶子、盘子近似静止和静态机器人模型等假设。此文补齐运行命令，不增加新的实验成功样本。
