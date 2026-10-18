# 观测释放候选约束与双视角跟踪重放

本轮以同一个 cheese/rack episode 检查短时遮挡、释放位姿接口和完整执行。没有引入仿真物体位姿或资产形状；碰撞接触规则继续使用已记录的 `oracle_cheese_rack_contacts_v1`，因此结果不能描述为严格检查碗与架子硬碰撞的成功。

## 实现

- 重新检出目标时，用新的 RGB-D 几何进行重绑定，取消误用的盲推夹爪模式门槛；仍保留原配准质量和身份一致性检查。
- 主视角未获得可接受结果时，尝试同一仿真时刻的腕部 RGB-D。两路均漏检才进入最多 10 步、0.5 秒的短时预测；预测不能确认抬升或成功。
- 执行后感知改为当前视觉场景入口，并复用已解析的任务绑定，避免重新启动视觉服务或调用旧 nomination 入口。
- 显式启用 `candidate_pose_v1` 时，原生放置的 XY/yaw 和高度约束使用同一个观测释放候选的 XYZ/yaw。候选表示直立悬空释放位姿，不声称其为稳定接触姿态。其余碰撞、运动学、自碰撞检查保持启用。其他任务默认不启用此改动。
- 接口代理框改为观测斜面投影的水平包围范围；不再硬编码 30 mm 水平尺寸。

## 验证与状态

本地、服务器各 29 项相关测试通过。先对上一轮保存的三个 On 问题分别执行原生求解，结果为 `plane_00: 0/64`、`plane_01: 7/64`、`plane_02: 0/64`。这只证明中间候选存在规划可行解，不等于抓取执行或放置成功。另两例应继续依据原生约束日志分析，不能直接归因为真实几何穿透。

随后对 `plane_01` 启动全新 RGB-D 完整回放（v1）：运行 202.75 秒，未成功，最终评测器也未判成功。主视角 step 123 没检出 cheese，腕部视角以 0.652 分数检出并通过几何配准，抬升探测与后续执行没有再触发前轮两处接入错误。但 On 规划 0/64，回退到可行的 Holding 计划（49/64），没有执行到释放；另有 60 步静置，最终 step 193。视频与 262 文件校验过的证据包见本文目录下 `assets/rgbd_release_candidate_20261017/`。

发现 v1 的采样代理平面仍被后端输出为 `mujoco_part_meshes`，因此“其他碰撞检查保留”同时保留了一个不应存在的虚构实体。尤其当前将代理框扩为观测投影范围，增大了这个错误的影响。修复为：显式候选模式下为该代理标注已有 `placement_region` affordance，沿用后端已有目标放置区域碰撞排除逻辑；真实观测障碍物仍走原策略，释放位姿约束不变。v2 保存问题的中间候选为 12/64 可行，完整重放目录为 `rgbd_release_candidate_20261017_v2`。

## v2 最终结果与当前卡点

全新重放用时 216.73 秒，完整 On 计划 **14/64 可行**，包含 Pick、Place、张爪和返回。代理平面的原生表示已确认为 `excluded_target_support_surface`；显式候选约束确实应用。29 项服务器测试再次通过。

实际执行完成抓取、抬升并向架子搬运，但没有松手，`recovery_success=false`，最终仿真评测也为 false。176 次跟踪均为实际观测：主视角 174 次、腕部视角 2 次，没有使用预测状态完成本轮执行。当前失败不再是每帧漏检立即中止，也不再是之前代理矩形的 XY 约束。

执行桥在 Place 阶段使用 lift/hover/XY 修正的启发式控制。此次 hover 目标距离约 408.9 mm，25 步后仍差 53.7 mm，报 `trajectory_tracking_budget_exhausted`；随后 XY 修正的 3 步仅推进约 0.26 mm，报 `trajectory_tracking_stalled`，对象到该执行器目标中心仍约 73.0 mm。释放检查为 `z_not_in_release_band`，执行器返回 `place_hover_xy_not_aligned`、`opened=false`、`handoff_to_vla=true`。独立重放 `policy_loaded=false`，因而保持夹持并静置 60 步，结束在 step 231。**没有到达候选释放位姿，不能把这个结果解释为候选释放后滑落或仿真提前成功停止。**

这里只确定了控制层报错和实际停止位置；3 步修正停滞究竟来自控制器限位、机器人与环境接触，还是当前控制策略，需要再用该时刻的控制状态和接触诊断区分，不能仅凭规划可行就认定物理执行必然可达。后续应先让执行器使用规划得到的释放位姿/路径，并对实际观测的位姿作到达验证；当前基于代理 AABB 中心的通用放置启发式与离散释放候选仍未完全对齐。

### 后续接触诊断：确认夹爪撞架子

用户从视频指出撞架后，使用同一初始物理状态和记录的全部 131 条动作，独立离线回放；不重新调用视觉或规划器，不改原实验。终点 step 171 的末端位置、姿态、手指关节、机械臂关节位置与速度全部逐值一致，因此该回放复现了原始停止状态。

接触记录确认：step 166 开始 `wine_rack_1_g4` 与 `gripper0_finger1_collision` 接触；step 168 又出现 `wine_rack_1_g1` 与 `gripper0_hand_collision` 接触。最后三步 XY 修正期间仍持续发生架子—夹爪接触，终点手指接触的穿透量约 0.204 mm。这支持用户的判断：夹爪在接近架子时被实体接触挡住，超时/停滞是其外在报错，不能只归为步数预算不足。该区间记录没有奶酪—架子接触；确认的是夹爪手指和手掌撞架，而非奶酪已正常落在架子上。

当前对齐历史真值的策略排除了目标架子的硬碰撞，因此 14/64 规划可行不代表已验证架子附近的夹爪避碰；同时实际执行使用 lift/hover 启发式。下一项修复应保留必要的目标—支撑接触，但检查机器人手指/手掌与架子的避碰，并让进入路径和释放候选一起验证，不能靠继续向前推或单纯增加步数解决。

远端诊断目录 `logs/rgbd_rack_contact_replay_20261017`。[接触摘要](rgbd_rack_contact_replay_20261017_summary.json)、[状态一致性核验](rgbd_rack_contact_replay_20261017_comparison.json)、[回放脚本](rgbd_rack_contact_replay_20261017_reproduce.py)。仿真真值只用于本次离线诊断，没有提供给 recovery。

### 为什么历史真值能够成功：执行高度不同

进一步直接读取历史 oracle `run/task08/ep00/recovery_trace.jsonl`，与 v2 的执行事件比较，发现同一 lift/hover 启发式得到不同进入高度。历史真值的目标为上层 `wine_rack_1_top_region`，还带有 95 mm 放置偏移，其 `surface_aabb_top=1.182960 m`、`lift_z=1.280371 m`，实际水平接近前末端高度 `1.274894 m`；RGB-D 中间观测层的临时释放代理 `surface_aabb_top=1.054290 m`、`lift_z=1.151996 m`，实际末端高度 `1.146824 m`。后者水平进入低了约 **128.1 mm**，随后发生已确认的架子—夹爪接触。

历史真值的水平目标中心约 `[-0.268033,-0.181548] m`，本轮执行器使用代理 AABB 中心 `[-0.278546,-0.218589] m`，XY 目标也不同。真值完成 hover 后继续下降，释放检查 `ok=true`，物体中心约 `[-0.269031,-0.181073,1.171744] m`，随后记录 `place_open`。本轮没有达到对应释放阶段。

因此两次结果并不矛盾：碰撞排除规则相同不等于走同一条路径。真值记录支持“高处进入、再下降释放”；RGB-D 将局部候选代理用于全架子净空估计，导致以较低高度水平进入架体。不能把真值成功解释为关闭了仿真实体碰撞，也不能把当前失败只归因于目标形状的毫米级误差。历史真值是否全程无擦碰仍未做接触回放；本比较不作该额外断言。[提取的执行对照数据](rgbd_oracle_rgbd_execution_comparison_20261017.json)。

[v2 视频](assets/rgbd_release_candidate_20261017_v2/recovery.mp4)按仿真时间播放，省略视觉推理等待；包含停止后的静置画面。[精简执行诊断](rgbd_release_candidate_20261017_v2_execution_diagnosis.json)保留动作失败数据。284 文件的证据包已验证 SHA256、ZIP CRC 和逐文件哈希，位于 `assets/rgbd_release_candidate_20261017_v2/evidence.zip`，SHA256 为 `d2e62b550838fa7a6209094fec1c085df8b49115c527a2da5c78dda2061750d5`。

## 复现与出处

本地分支 `feature/rgbd-recovery`，基线 commit `62e4bc8410bcf1211c8b86dc8263746f2c8a6795`；本轮源码为未提交修改，精确版本以远端 `source_sha256.json` 和代码快照为准。运行 overlay 基于先前冻结的 `7128c1ea6280c227e48561e621fe9da8604c5a6d`，仅替换指定后端函数区域及相关脚本，不能直接用旧本地后端覆盖整个冻结后端。

服务器目录 `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_release_candidate_20261017`。`coordinator.py`、`*.preflight.command.json`、`replay_driver.command.json`、`plane_01/command.json` 记录精确参数和环境。

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$ROOT/logs/rgbd_release_candidate_20261017
cd "$RUN/code"
PYTHONPATH="$RUN/code" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
 "$ROOT/envs/rlinf-openpi/bin/python" \
 "$RUN/code/scripts/recovery/skill_pipeline/run_observed_rack_recovery.py" \
 --root "$ROOT" --run "$RUN" \
 --collision-policy oracle_cheese_rack_contacts_v1 \
 --tracking-gap-steps 10 --tracking-gap-seconds 0.5 \
 --release-pose-constraint --wrist-fallback --plane-ids plane_01
```

以上是 v1 实际驱动参数；v2 将 RUN 改为 `$ROOT/logs/rgbd_release_candidate_20261017_v2`，其余参数一致，使用 v2 代码快照。精确调用另存 [v2 驱动参数](rgbd_release_candidate_20261017_v2_replay_driver.command.json)，源码版本另存 [v2 哈希](rgbd_release_candidate_20261017_v2_source_sha256.json)。复跑应另选新日志目录并复用对应代码快照，避免覆盖证据。权重、环境、初始状态和原生 runner 仍由驱动及每例 command 记录绑定。
