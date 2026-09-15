# LIBERO-90 Online Recovery Known-Good Eval Profile

更新日期：2026-09-09

本文记录当前 LIBERO-90 skill recovery 的已验证启动配置。它的目的不是新增 skill，
而是防止评测脚本回到旧参数，导致把配置漂移误判为 skill 退化。

## Harness Profile

注册 benchmark：

```bash
python scripts/recovery/skill_pipeline/harness_run.py \
  --benchmark libero90_online_recovery_known_good \
  --workspace_root /mnt/nas/gezuhao/xinghanbo \
  --repo_root /mnt/nas/gezuhao/xinghanbo/openvla-oft \
  --start
```

默认任务是 LIBERO-90 task74/task75，各 5 ep，保存视频和标注视频。跑更大范围时，
用 `--tasks` 覆盖任务列表，但保留该 profile 的 recovery 和 real cuTAMP 参数。

## Fixed Parameters

关键参数：

| field | value |
| --- | --- |
| `skill_pack` | `libero90_legacy` |
| `model` | `pi0_libero_openpi` |
| `max_recovery_steps` | `280` |
| `max_recovery_calls` | `1` |
| `real_cutamp.num_particles` | `64` |
| `real_cutamp.num_opt_steps` | `40` |
| `real_cutamp.max_loop_dur` | `20.0` |
| `real_cutamp.serialize_trajectories` | `true` |
| `real_cutamp.curobo_plan` | `true` |
| `real_cutamp.prefer_executable_plan` | `true` |
| `real_cutamp.require_executable_plan` | `true` |
| `real_cutamp.table_proxy_profile` | `thin_clipped_lowered` |
| `real_cutamp.static_context_collision_mode` | `all` |

`libero90_smoke` 和 `libero90_skill_regression` 也已改为同一个 280-step recovery
budget，并显式使用 `libero90_legacy` skill pack。

## Validation Record

远端验证：

```text
/mnt/nas/gezuhao/xinghanbo/logs/place_profile_budget_retest_tasks74_75_5487956_20260909_081617
```

结果：

| task | success | recovery calls | skill episodes |
| --- | ---: | ---: | --- |
| task74 | 5/5 | 5 | `book_pick_approach_recovery`: 3, `book_caddy_pick_approach_recovery`: 2 |
| task75 | 5/5 | 5 | `book_pick_approach_recovery`: 3, `book_caddy_pick_approach_recovery`: 2 |

总体 `10/10`，harness gate 通过，视频和 annotated videos 均已生成。

坐标帧修复后的补充 smoke：

```text
/mnt/nas/gezuhao/xinghanbo/logs/framefix_caddy_sites_tasks74_75_f105d11_20260909_2256
```

结果：task74 `4/5`，task75 `5/5`，总体 `9/10`，harness gate 通过。该 run 用于确认
desk-caddy compartment site / opening 已经和 planner-frame object pose 同帧；task74 front
opening center 为 `[-0.367384, -0.136984]`，task75 left opening center 为
`[-0.404714, -0.283134]`。

## Why This Matters

之前的差结果使用了 `max_recovery_steps: 200`，而 task74/task75 的 book-to-caddy
place alignment / yaw / drop 阶段需要更长预算。恢复到 280 后结果回到 10/10。

后续如果发现 LIBERO-90 recovery 回归，先检查 `resolved_spec.json` 和 launch script
是否仍使用本 profile 的关键参数，再进入 skill 诊断。
还要检查 surface/opening metadata 的 `inner_bounds_coordinate_frame` / `coordinate_frame`
是否为预期值，避免 world-frame site 混入 planner problem。
