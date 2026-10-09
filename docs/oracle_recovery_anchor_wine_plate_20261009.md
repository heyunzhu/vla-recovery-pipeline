# 真值 recovery 成功锚点：酒瓶放到盘子上

2026-10-09。在启智 `可上网GPU资源` 的 `xinghanbo-eval` 启动并复跑；未操作其他实例。首次连接刷新遇到 OpenSSH bootstrap 错误，重试成功。实验完成后实例保持运行，实验进程已结束。

## 选定样例与历史证据

- Suite：`libero_goal_task`，task04（1-based；底层 task_id=3）。
- 任务语言：`Put the wine bottle on the plate`。
- episode_idx=0，init_state_idx=0，episode seed=1；base seed=90，episode_seed_start=1。
- 目标：`wine_bottle_1_main`；放置物：`plate_1_main`。
- 历史运行：`continual_skill_core60_pilot_20261006/lanes/lane2/026_C4_libero_goal_task/run/task04/ep00`。
- 历史 episode 成功，触发 1 次 recovery；query_idx=5、env_step=35，技能 `wine_bottle_plate_wrong_object_handoff`。
- 历史恢复轨迹包含真实抓取轨迹执行、闭爪、放置；放置事件 success=true、done=true，非仅规划成功或 VLA 自行完成。

上述路径均相对于服务器根目录：
`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/`。

## 本次复跑配置

复用历史冻结的 `continual_skill_core60_pilot_20261006/runtime_repo`、`core60_entrypoint.py`、LIBERO-Pro 配置与 init 文件，以及冻结的 C4 技能包：
`checkpoints/libero_object_task_from_spatial_swap_mining_base_20260918`。

关键配置保持历史值：Pi0 `pi0_libero_openpi`，action_chunk=5，settle=10，语言来源 BDDL；真实 cuTAMP，6 DOF，64 particles，40 optimization steps，20 秒 loop budget，序列化轨迹、cuRobo、要求可执行计划；recovery budget=200、最多2次调用、1次 replan。未强制触发，仍使用原技能触发条件。

只将任务范围缩小为 task04、1个 episode、episode_index_start=0，并将日志/debug/锁路径改到独立新目录。使用同一历史入口与技能包，不部署当前 RGB-D 分支改动。重新求解的随机候选轨迹不保证与历史逐步相同。

服务器新目录：
`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/oracle_anchor_wine_plate_20261009`。

目录保存 `run.sh`、历史 episode/summary/environment、源码 SHA256、新 driver.log、episode/query/recovery trace、video、solver problem/result/stdout/stderr、结束时间与退出码。

## 本次实际结果

| 检查 | 结果 |
|---|---|
| 正常触发 | query_idx=5、env_step=35，与历史相同 |
| 技能 | wine_bottle_plate_wrong_object_handoff |
| recovery_calls | 1 |
| 原生求解 | available=true、feasible=true |
| 满足约束候选 | 16 |
| 求解耗时 | 66.577 秒，含实际后端整体调用；不是20秒优化预算的同义指标 |
| 可执行计划 | 存在 |
| 抓取轨迹 | 两段执行成功，分别30／7步 |
| 闭爪 | 执行成功，34步 |
| 放置 | 执行成功，47步，done=true |
| episode success | true |
| abort_episode | false |
| 进程退出码 | 0 |

episode 的 num_env_steps=26 是 runner 记录的政策推进计数，不能当作包含全部 recovery 动作的总控制步数。恢复动作按 recovery_trace 单独记录，另有入口抬升等事件。

本地下载：`analysis_outputs/oracle_anchor_20261009/historical_ep00/` 和 `analysis_outputs/oracle_anchor_20261009/replay/`（Git 忽略的大型产物）。

下载后已本地重新检查 episode、trigger、solver result、place done、退出码与视频文件，并保存 `analysis_outputs/oracle_anchor_20261009/verification.json` 和关键产物 SHA256。query5 的 JPEG 与历史并非逐字节相同，故本次是同配置单例成功复现，不是历史轨迹逐步确定性重放。

## RGB-D 对照边界

这例已证明同一任务、seed/init 和历史配置下的真值 recovery 完整成功，可替代此前未成功的临时真值诊断作为锚点。它不证明 recovery 的因果收益或 RGB-D 能力。

本次未改动历史 runner 的采集逻辑，保存的是其原有 RGB 查询图像与视频，尚未保存恢复时刻的同步深度。下一步应以此配置为基础，增加不推进物理状态的 RGB-D 采集，保存 query5 的恢复入口帧，并区分入口抬升前与实际 solver 输入时刻，核对是否再次成功。随后保持技能/求解配置固定，分别验收视觉实例绑定和视觉几何替换。
