# LIBERO-Pro Mining 复盘：从人工介入到 daemon 介入

本文记录 2026-09-10 到 2026-09-12 的 LIBERO-Pro mining 情况，重点对比：

1. goal-swap 上相对成功的 mining；
2. 引入本地 Codex daemon 后，goal-task mining 暴露出的调度问题和规划问题。

## 当前状态

- 已停掉当前 `libero_goal_task task10` mining 的远端进程。
- 本地 Windows 定时任务 `CodexMiningDaemon` 已禁用，避免继续自动接入。
- 停止标记已写入当前 run：
  `mine/STOPPED_BY_USER.txt`
- 当前未完成 run 在 W3 validation 启动后被人工停止，状态机文件仍显示 `awaiting_kind=validation`，这是中途终止造成的残留状态：
  `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task10_seed51_65_mining_daemon_guidelines_20260912_063923`
- W3 是由修复后的 daemon 接上 W2 后启动的，随后被人工停止。

## 成功或基本可用的 mining

这些 run 主要发生在 `libero_goal_swap`，流程相对正常：失败 rollout 进入 Codex 介入，写出 trigger / grasp / grounding / geometry / place 等 skill 或 profile，随后同 init validation 达到或接近通过阈值。

| suit/task | 任务 | 远端目录 | 结果 | 写入次数 | 主要产物 |
|---|---|---|---:|---:|---|
| goal_swap task05 | put the bowl on top of the cabinet | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task05_seed51_65_mining_7e978f7_20260910_1800` | 9/15，通过 | 1 | `bowl_cabinet_wrong_object_or_open_pick`, `grasp_bowl_cabinet_hollow_rim_topdown` |
| goal_swap task07 | put the cream cheese in the bowl | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task07_seed51_65_mining_32486bb_20260910_2145` | 11/15，通过 | 3 | `cream_cheese_bowl_low_hover_balanced` |
| goal_swap task09 | put the bowl on the plate | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task09_seed51_65_mining_32486bb_samepack_20260910_233003` | 10/15，通过 | 1 | `bowl_plate_target_approach_handoff`, `grasp_goal_swap_black_bowl_rim_diagonal_topdown` |
| goal_swap task05 same-pack | put the bowl on top of the cabinet | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task05_seed51_65_mining_32486bb_samepack_20260911_045336` | 12/15，通过 | 1 | `bowl_cabinet_target_holding_handoff`, `grasp_goal_swap_black_bowl_cabinet_rim_topdown`, `cabinet_top_surface_geometry_explicit` |

比较典型的是 task07：前两轮 skill 不够，后续写到 `cream_cheese_bowl_low_hover_balanced` 后通过。这类成功 run 的共同点是：Codex 介入时能看到 rollout/triage，能写出具体执行产物，validation 结果也能被状态机正确接住。

## 未完全成功但有信息价值的 goal-swap run

| suit/task | 远端目录 | 结果 | 现象 |
|---|---|---|---|
| goal_swap task03 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task03_seed51_65_mining_32486bb_samepack_20260911_003730` | 状态不干净，曾写到 W2 | `grasp_goal_swap_wine_bottle_body_high_topdown`，后续仍有 `no satisfying` |
| goal_swap task10 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task10_seed51_65_mining_32486bb_samepack_20260911_024505` | `system_blocked` | 最后 `wine_rack_top_place_lift_budget`，triage 为 `optimized_motion_tracking_stalled`，约 2/5 |

这些 run 说明流程能推进，但 task 本身可能需要更深入的 rack / bottle / place 能力。

## daemon 后的 goal-task mining

`libero_goal_task` 是从 goal-swap pack 泛化过来的新 suit。引入 daemon 后，主要问题不只是 task 难，而是调度链路本身开始污染 mining 结论。

| suit/task | 远端目录 | 结果 | 主要问题 |
|---|---|---|---|
| goal_task task07 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task07_seed51_65_mining_1cb091e_20260911_082548` | `system_blocked` | 语言/目标错配，skill 指向 `cream_cheese_language_wine_bottle_goal_mismatch_handoff`，validation 0/15 |
| goal_task task04 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task04_seed51_65_mining_681daf5_20260911_2135` | 已 abort | 启动时任务选择错误，记录为 `aborted_wrong_task04` |
| goal_task task02 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task02_seed51_65_mining_681daf5_20260911_223020` | `write_budget_exhausted` | 5 次写入后仍未过，若干事件 resolved/error 混杂 |
| goal_task task08 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task08_seed51_65_mining_e14d484_20260912_052636` | 14/15，通过 | baseline/现有 skill 已足够，0 write |
| goal_task task10 | `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task10_seed51_65_mining_daemon_guidelines_20260912_063923` | W3 validation 启动后人工停止 | W0/W1/W2 均 0/5；daemon 起初未自动接上，修复后接上 W2 并启动 W3 |

## 当前 task10 的具体情况

任务：`Put the cream cheese on the rack`

目录：
`/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task10_seed51_65_mining_daemon_guidelines_20260912_063923`

当前 pack：
`/mnt/nas/gezuhao/xinghanbo/openvla-oft/skill_packs/libero_goal_task_from_goal_swap_v1`

已写入或参与的相关 skill：

- `cream_cheese_rack_wrong_object_pregrasp_handoff`
- `grasp_cream_cheese_flat_box_topdown_deep`
- `ground_cream_cheese_wine_rack_top_region`
- `geometry_wine_rack_top_region_surface`
- `grasp_cream_cheese_rack_libero_topdown`
- `geometry_wine_rack_top_region_low_surface`
- `place_cream_cheese_rack_lift_budget`

validation 结果：

| round | validation 目录 | 结果 | 主要现象 |
|---|---|---:|---|
| W0 | `mine/validation/mine_val_task10_w0` | 0/5 | `No satisfying particles` / `Motion planning failed` |
| W1 | `mine/validation/mine_val_task10_w1` | 0/5 | 仍然是 `robot_to_world` collision 与 `pos_err` |
| W2 | `mine/validation/mine_val_task10_w2` | 0/5 | grasp sampler 已变为 `libero_topdown`，但仍 `No satisfying particles` |
| W3 | `mine/validation/mine_val_task10_w3` | 中途停止 | 修复 daemon 后自动接上 W2 并启动，随后按要求停掉 |

W2 triage 明确显示：

- `success: 0/5`
- 所有 episode 都触发 recovery；
- 主签名是 `no satisfying`；
- cuTAMP blocker 仍然包括：
  - `Collision robot_to_world <= 0.001 has 0/64 satisfying`
  - `[KinematicConstraint] pos_err <= 0.005 has 0/64 satisfying`
- W2 已经把 grasp sampler 从深抓取切到 `libero_topdown`，但无解仍持续存在。

这说明 W1 的修正方向没有触及根因。现在更像是 rack surface / 静态碰撞 / goal geometry / TAMP problem 构造的问题，而不是单纯 grasp profile 的问题。

## daemon 问题

这次“没有 daemon 自动接上”的原因不是单点故障，而是多层叠加。

### 1. 定时任务投到了旧 thread

Windows 任务：
`CodexMiningDaemon`

原 wrapper：
`C:\Users\dx\AppData\Local\CodexMining\daemon.cmd`

它原来设置：

```bat
set CODEX_AGENT_THREAD=01a0901f-778a-7c21-af12-4eb21621eaf1
```

这个 thread 不是当前工作线程。结果是 daemon 即使触发，也可能把 intervention queue 到旧对话里。

### 2. daemon workdir 分裂

手动调试使用：
`E:\VLA_recovery_workspace\openvla-oft\experiments\.pro\daemon_work`

定时任务默认使用：
`C:\Users\dx\AppData\Local\CodexMining\work`

这导致同一个远端 mining event 在本地有两套 attempts / prompts / result marker。手动修复后的状态不会被定时任务共享，定时任务的失败也不一定出现在仓库内的 `.pro/daemon_work`。

### 3. 旧坏 run 阻塞扫描

定时任务默认扫描多个 mining run。它一直撞到这个旧目录：

`/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task_task10_seed51_65_mining_e14d484_20260912_053803`

该目录缺少：

`mine/mine_state.json`

旧代码在读取这个文件失败时直接让 daemon 退出，导致 daemon 还没扫到当前有效 run 就失败。

### 4. queue 消息会延迟出现

`codex queue` 是 fire-and-forget。之前 W1 attempt1 / attempt2 的 queue message 延迟到当前线程后，仍然触发了“请写 result.json”的消息。虽然我们做了幂等处理，但这说明如果没有严格 event/attempt 状态校验，旧消息会干扰当前判断。

### 5. 本地 wrapper 曾经没有明确固定 run-root

自动 daemon 用 `--max-runs` 扫描，而不是 `--run-root` 指定当前 mining。这对长期监控多个 run 有用，但在调试阶段会被旧 run 污染。当前 task10 的问题就来自这里。

## 已做的停止与修正

已停止：

- 远端当前 task10 mining 相关进程：无残留 `run_mining_lane` / `run_skill_eval` / watcher。
- 本地 Windows 定时任务 `CodexMiningDaemon`：已禁用。

已修本地代码：

- `mine_state()` 对远端缺失 / 读取失败不再让 daemon 整体崩溃；
- daemon 的 draft verify 会检查 `bundle.yaml` 中 `drafts[].file` 是否真实存在，避免再次出现 `drafts/drafts/...` 这种 ingest 才发现的路径错误；
- 定时任务 wrapper 已改为当前 thread，并改用仓库下 `.pro/daemon_work`。

注意：这些修正还没有构成最终稳定方案，只是阻止当前问题继续扩大。

## 对比结论

成功的 goal-swap mining 说明“Codex 读 evidence -> 写 skill/profile -> admission -> 同 init validation”的主流程本身可以工作。

daemon 后失败的 goal-task mining 暴露的是两个不同层面的问题：

1. **调度层不稳**：thread、workdir、旧 run、queue 延迟、错误状态复用都会导致介入不及时或介入到错误位置。
2. **任务能力层仍不足**：task10 的 rack 放置问题在 W2 后仍是 cuTAMP `0/64`，且 grasp 已改为 `libero_topdown` 仍无解，说明需要重新诊断 TAMP problem，而不是继续只调 grasp 或 trigger。

下一步如果恢复 mining，建议先只指定单个 `--run-root` 做 daemon smoke，不要全局扫所有历史 mining；同时先对 task10 做 problem 级 replay，核查 rack surface、静态碰撞、目标 region 和 place candidate 的坐标/尺寸。
