# 将历史架子 skill 接到 RGB-D 的受控重放

用户要求打开历史成功案例的 skill 再试同一个回合。本轮在 `xinghanbo-eval` 新建独立运行 `logs/rgbd_saved_skill_20261017`，参考 `rgbd_release_candidate_20261017_v2`。本地分支 `feature/rgbd-recovery`，基线 `62e4bc8410bcf1211c8b86dc8263746f2c8a6795`，本轮修改未提交；冻结 runtime 基于 `7128c1ea6280c227e48561e621fe9da8604c5a6d`，精确源码以运行快照和哈希为准。

## 实际恢复了哪些 skill 内容

上一轮保留了 `cream_cheese_flat_box_topdown_deeper_v2` 抓取 profile、入口姿态复位参数；不能说上一轮完全没有使用 skill。历史 hints 还包含 `geometry_cream_cheese_rack_top_region` 和 `ground_cream_cheese_rack_top_region` 的上层区域配置，这部分此前被视觉回放驱动去掉。

本轮重新使用保存 skill 中 `wine_rack_top_region_surface_v1` 的原始几何 resolver 与数值参数，包括 3 mm 区域 margin、24 mm 最小半宽、3 mm 顶部余量、6 mm 厚度、95 mm 放置候选初始化偏移。原始 hint 与代码哈希保存在 `saved_recovery_hints.json`、`skill_source_sha256.json`。

原 resolver 要求输入命名 site，而 RGB-D 没有仿真 site。本轮显式适配：选择当前观测中最高的支撑平面，以其投影范围、中心构造带有 `current_RGBD_upper_plane` 来源的区域，再把视觉实例 ID 绑定给原 resolver；不查询仿真物体/区域位姿。它是历史 skill 的视觉绑定适配，不能描述为完全不改动地启动原 skill 触发与 grounding 全链路。完整历史 hints 作为来源留档，实际绑定过程由适配器完成。

执行器分别接收：整个可见架子的观测包围范围，用于抬升净空；skill 经观测区域生成的 opening，用于目标 XY/释放高度。规划使用 skill 虚拟表面及其原有候选生成入口，不再启用上一轮的 `candidate_pose_v1` 离散释放约束。因此本轮同时恢复了区域语义、区域构造及对应执行输入，不能作为只改变一个标量的消融。

目标、障碍物仍来自当前 RGB-D，逐帧检测、腕部备用视角、短时漏检边界保持。碗与架子接触排除策略继续为 `oracle_cheese_rack_contacts_v1`；没有恢复严格架子硬碰撞。本体状态来自机器人，仿真成功信号只用于评估。

## 检查与复现

本地和服务器各 31 项相关测试通过，包括观测区域坐标变换、保留原 skill 参数、不允许 resolver 失败后退回仿真区域。使用独立代码、overlay 和日志，不覆盖前轮。

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN=$ROOT/logs/rgbd_saved_skill_20261017
cd "$RUN/code"
PYTHONPATH="$RUN/code" OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 \
 "$ROOT/envs/rlinf-openpi/bin/python" \
 "$RUN/code/scripts/recovery/skill_pipeline/run_observed_rack_recovery.py" \
 --root "$ROOT" --run "$RUN" \
 --collision-policy oracle_cheese_rack_contacts_v1 \
 --tracking-gap-steps 10 --tracking-gap-seconds 0.5 \
 --wrist-fallback --rack-skill --plane-ids plane_00
```

复跑需另建新目录并沿用对应代码快照。`replay_driver.command.json` 和 `plane_00/command.json` 保存实际调用及环境；`rack_skill_binding.json` 保存原 hint、适配后的 hint、观测区域和原 resolver 输出。

## 运行结果

两轮已结束，均未成功；没有放宽跟踪质量门槛来强行跑完。

| 运行 | 原生完整 On 计划 | 最后执行阶段 | 停止原因 |
|---|---|---|---|
| `rgbd_saved_skill_20261017` | 22/64 可行 | Place:hover，step 168 | 主视角漏检；腕部检出 cheese，但配准中位误差 7.72 mm，大于 6 mm 门槛 |
| `rgbd_saved_skill_20261017_v2` | 24/64 可行 | Pick 闭爪，step 132 | 主视角漏检；腕部检出 cheese，但配准中位误差 7.79 mm，大于 6 mm 门槛 |

第一轮已把末端抬到约 **1.331 m** 并开始水平搬运，明显高于上一轮撞架案例的约 1.147 m；但在到达架子前被视觉配准中断，不能据此证明已经消除整个放置路径的碰撞。该轮腕部检测分数约 0.782，239 个观测点，观测/参考重叠比例分别 0.983/0.647。

实现检查还发现，旧 `estimate_object_geometry` 会从 geoms 重新构造 metadata，未保留新写入的 skill inner_bounds；v1 的执行 opening 存在回退到全架子 AABB 的风险。v2 显式将观测 skill 的 world-frame inner_bounds 接给执行器 `_opening_bounds`，仅作用于 opt-in 的这个视觉目标；但 v2 在闭爪阶段就被配准拒绝，因此**该修正的 Place 执行路径尚未经过完整在线验证**，不能宣称端到端接入成功。

v2 腕部 cheese 检测分数约 0.718，291 个观测点，观测/参考重叠比例 1.000/0.557。这里“检测到了”与“能可靠恢复三维姿态”是两个门槛；当前卡在后者。短时漏检预测只允许两路都没有检测到目标时使用，不能自动覆盖“已经检出但几何配准不通过”的帧，因此本例直接停止。没有松手、没有静置观察，两轮最终仿真成功均为 false。

31 项本地/服务器测试通过。两轮的粒子数是单次求解内的结果，不是成功率，也不能把 22→24 归因于 opening 修正；opening 修正属于执行阶段，求解自身存在采样差异。

[两轮摘要](rgbd_saved_skill_20261017_summary.json)、[原始 skill 与视觉区域绑定](rgbd_saved_skill_20261017_v2_rack_skill_binding.json)、[v2 实际驱动参数](rgbd_saved_skill_20261017_v2_replay_driver.command.json)、[v2 源码哈希](rgbd_saved_skill_20261017_v2_source_sha256.json)。复现 v2 时将上述 RUN 改成 `rgbd_saved_skill_20261017_v2` 并使用 v2 快照。

[v1 视频](assets/rgbd_saved_skill_20261017/recovery.mp4)展示高处搬运直到视觉中断；[v2 视频](assets/rgbd_saved_skill_20261017_v2/recovery.mp4)展示修正版在闭爪时停止。视频按仿真时间播放，省略推理等待。证据包分别包含 232/158 个文件，均已验证 archive SHA256、ZIP CRC 及逐文件哈希。

本轮结论是：历史 skill 的区域构造能接到当前观测并产生完整可行计划，高处进入策略也已在 v1 实际执行；完整任务仍受遮挡下三维配准中断影响。不能据此认为 skill 对避碰无效，也不能宣称打开 skill 就已恢复历史成功表现。

后续已对这两帧开展当前深度可见性诊断，详见 [部分观测配准实验](rgbd_partial_tracking_20261017.md)。
