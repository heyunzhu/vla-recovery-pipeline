# 用现有 LIBERO-Pro pack 跑新任务

日期：2026-10-03

评测对象是按 `docs/libero_pro_build_new_tasks_2026-10-03.md` 登记好的 suite。当前 object pack 是 `skill_packs/libero_object_task_from_spatial_swap_mining_base_20260918`。它的 36 条 skill 都在 `fail_only`，`online` 是空的。`--enable_skills` 不会加载它们。挖掘验证用 `--enable_mining_skills`，并且不要同时打开 `--enable_skills`。

每次同时跑两个条件，任务列表、seed、init 下标相同：

- pack：`--enable_mining_skills`，真实 cuTAMP。
- 对照：两个开关都不开。对照用来看 VLA 自己能不能做成，以及 pack 有没有把本来能做成的回合弄失败。

不要设 `--force_recovery_query`。那个开关跳过 trigger 竞争，只合并 hint，不能用来回答「这条 skill 有没有触发」。

一次 smoke 可以每条任务 1 个 episode。要写成功率，把 `--num_trials_per_task` 加到和源评测同一量级，并保持 `episode_seed_start` 一致。

带 Place 的恢复必须显式传 `--max_recovery_steps 200`。runner 默认是 80，再减去默认的 `place_reserve_steps=80` 之后，Pick 轨迹只剩 1 步，会报 `optimized_motion_budget_exhausted`。这和物体能不能被抓住无关。`--max_recovery_calls` 用 2，和 object 轴 50-seed 以及 `MINING_MAX_RECOVERY_CALLS` 一致。2026-10-03 第一次 smoke 漏了这两项，那次 0/3 不作数。修正后的一集结果见 `docs/libero_pro_object_axis_mrs200_rerun_2026-10-03.md`。

## 进程里要有的环境

文件和数据都在 `/mnt/nas/gezuhao/xinghanbo` 下面。不要改全局环境变量，不要改 `~/.libero/config.yaml`。`LIBERO_CONFIG_PATH` 只在这次进程里指向已有的 `libero_config_pro`，那里的 `benchmark_root`、`bddl_files`、`init_states`、`assets` 已经指到 LIBERO-PRO。

```bash
export ROOT=/mnt/nas/gezuhao/xinghanbo
export CUDA_VISIBLE_DEVICES=0
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
export LIBERO_CONFIG_PATH=$ROOT/libero_config_pro
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export PYTHONPATH=$REPO:$ROOT/LIBERO-PRO
```

`REPO` 是这次评测用的代码目录。解释器是 `$ROOT/envs/openpi_jax_py311/bin/python`。模型是 `$ROOT/models/pi0_libero_openpi`。cuTAMP 走 `$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh`，调用前 `chmod +x`。`git archive` 出来的脚本没有执行位，不 chmod 会在第一次 recovery 上报 `PermissionError`。脚本靠 `ROOT` 找到 `$ROOT/envs/tiptop-planning-py310` 和 `$ROOT/third_party/cuTAMP`。

`CUDA_VISIBLE_DEVICES` 选一张还有空闲显存的卡。`XLA_PYTHON_CLIENT_PREALLOCATE=false` 避免 JAX 占满整张卡。

## 命令

在 `REPO` 里执行。`--task_ids` 是 suite 里的 1-based 下标。suite 名以 `_task` 结尾时，`auto` 会把 BDDL 语言同时交给策略和 recovery。

```bash
python -m experiments.robot.libero.skill_pipeline.runner \
  --pretrained_path "$ROOT/models/pi0_libero_openpi" \
  --config_name pi0_libero \
  --task_suite_name pro_object_axis_20261003_task \
  --task_ids 1,2,3 \
  --num_trials_per_task 1 \
  --episode_seed_start 1 \
  --policy_in_process \
  --save_video \
  --openvla_repo_root "$REPO" \
  --task_language_source bddl \
  --engine_language_source bddl \
  --max_recovery_calls 2 \
  --max_recovery_steps 200 \
  --max_replans 1 \
  --enable_mining_skills \
  --skill_pack libero_object_task_from_spatial_swap_mining_base_20260918 \
  --use_real_cutamp_backend \
  --real_cutamp_require_feasible \
  --real_cutamp_curobo_plan \
  --real_cutamp_serialize_trajectories \
  --prefer_real_cutamp_executable_plan \
  --require_real_cutamp_executable_plan \
  --real_cutamp_grasp_dof 6 \
  --real_cutamp_runner_python "$REPO/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh" \
  --real_cutamp_runner_timeout_sec 900 \
  --real_cutamp_debug_dir "$LOG/pack/cutamp_debug" \
  --log_dir "$LOG/pack" \
  --exp_name pack
```

对照去掉 `--enable_mining_skills`、`--skill_pack` 和全部 `--real_cutamp_*` / `--use_real_cutamp_backend`，`--log_dir` 改到 `$LOG/baseline`。其余参数保持同一套，这样两边的 init 下标和 seed 对齐。

object 轴步数是 280，由 `max_steps_for_suite` 决定。新 suite 若没写进这个函数，进程会在加载任务时退出。

## 读结果

日志在 `--log_dir/--exp_name/` 下面。每条任务一个 `taskNN/ep00/episode.json`。

先看这三列，不要把随机任务标成「该用的 skill 触发了所以泛化成功」：

| 记录 | 从哪读 | 含义 |
| --- | --- | --- |
| `success` | `episode.json` | 这一集任务有没有完成 |
| `recovery_calls` | `episode.json` | 有没有进入 recovery。0 表示没有 skill 把门打开 |
| `skill_id` | `recovery_trace.jsonl` 里 `kind=rule` 的事件 | 实际赢下触发的那条 skill |

然后和对照比同一条任务：

- pack 成功、对照不成功：这一集 pack 把完成数抬高了。
- 两边都成功，或都失败：完成数没有变化。recovery 仍要单独记下，失败且 `recovery_calls>0` 只说明进了门，不说明做成了。
- 对照成功、pack 失败：记成干扰，并按改动轴分开计数。

`recovery_trace.jsonl` 为空且 `recovery_calls=0`，就是没有触发。cuTAMP 的 `failure_reason` 在 driver 日志的 `[agg-diag]` 行，例如 `optimized_motion_budget_exhausted`。那是恢复动作没做完，不是没触发。

2026-10-03 第一次 smoke 漏了 `--max_recovery_steps`，三条 pack 都在 Pick 的第 1 步停住。那个日志还在 `/mnt/nas/gezuhao/xinghanbo/logs/pro_object_axis_20261003_object_pack/`，不要拿来当任务结果。同一天按上面的命令重跑之后，改目标和改摆放各 1 集 pack 成功、对照失败；改朝向两边都失败且 pack 没有触发。数字和日志目录见 `docs/libero_pro_object_axis_mrs200_rerun_2026-10-03.md`。
