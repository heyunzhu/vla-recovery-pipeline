# object 轴三任务 smoke 重跑（max_recovery_steps=200）

日期：2026-10-03

suite 是 `pro_object_axis_20261003_task`，pack 是 `libero_object_task_from_spatial_swap_mining_base_20260918`。同一天早些时候的 smoke 漏了 `--max_recovery_steps`。runner 默认 80，`place_reserve_steps` 也是 80，带 Place 的 Pick 预算被收成 1 步，三次都停在 `optimized_motion_budget_exhausted`。视频里 recovery 只有大约 0.3 秒，看起来什么都没做。那次 0/3 是步数配置问题，不是这三条任务做不成。

这次按 object 轴 50-seed（日志目录名带 `mrs200`）和挖掘入口的常量重跑：`MINING_MAX_RECOVERY_STEPS=200`，`MINING_MAX_RECOVERY_CALLS=2`。仍然是 seed 1、每条 1 集，不是成功率。

## 命令里和第一次不同的地方

- `--max_recovery_steps 200`。第一次没写，落到默认 80。
- `--max_recovery_calls 2`。第一次写成 1。这次三条实际用了 1 次或 0 次。
- `--task_language_source bddl` 和 `--engine_language_source bddl`。suite 名以 `_task` 结尾时 `auto` 也会这样选，这里写明。
- `--seed 90`、`--max_replans 1`。都是 runner 默认值，和第一次相同，只是写进了命令。

其余和 `docs/libero_pro_run_pack_eval_2026-10-03.md` 相同：进程内 `LIBERO_CONFIG_PATH` 指向 `libero_config_pro`，`--enable_mining_skills`，真实 cuTAMP，`grasp_dof=6`，不设 `--force_recovery_query`。对照关掉 skill 和 cuTAMP。

进程环境比第一次多了 `XLA_PYTHON_CLIENT_MEM_FRACTION=0.50`。只设 `XLA_PYTHON_CLIENT_PREALLOCATE=false` 时，JAX 仍把空卡预占到大约九成，恢复 checkpoint 时会在 2.25GiB 的连续分配上 OOM。这次用物理 2 号卡，`CUDA_VISIBLE_DEVICES=2`。0 号卡上已有别的进程占着大约 26GB，没有动它。

## 结果

日志：`/mnt/nas/gezuhao/xinghanbo/logs/pro_object_axis_20261003_object_pack_mrs200/`。pack 从 2026-10-03 13:02:32Z 到 13:06:05Z，对照到 13:08:35Z。

| 任务 | pack | 对照 |
| --- | --- | --- |
| 1 改目标，alphabet soup 进篮子 | 成功。`recovery_calls=1`，26 步结束。skill：`object_basket_persistent_wrong_intent_group_a` | 失败，280 步，`recovery_calls=0` |
| 2 改摆放，cream cheese | 成功。`recovery_calls=1`，26 步结束。skill：`object_basket_cream_cheese_precontact_wrong_intent` | 失败，280 步，`recovery_calls=0` |
| 3 改朝向，cream cheese | 失败，280 步，`recovery_calls=0`，没有 skill | 失败，280 步，`recovery_calls=0` |

前两条的 Pick 轨迹走完了。driver 日志里 `[agg-diag]` 对 `Pick(alphabet_soup_1_main, grasp1, q1)` 和 `Pick(cream_cheese_1_main, grasp1, q1)` 都是 `success=True`，环境步是几十步，不是 1 步。对照两条都走满 280 步仍失败，所以这两集是 pack 把完成数抬高了。一集不能写成成功率。源任务 cream cheese 进篮子在 50-seed 上是 40/50，见 `docs/libero_object_axis_50seed_validation_2026-09-20.md`。

改朝向这一集 skill 没有进门，对照也同样失败。按 `docs/libero_pro_build_benchmark_2026-10-03.md` 的读法，这不是干扰，也不是步数预算再犯。recovery trace 是空的。

第一次那份无效日志留在 `/mnt/nas/gezuhao/xinghanbo/logs/pro_object_axis_20261003_object_pack/`，不要和这次的目录混用。
