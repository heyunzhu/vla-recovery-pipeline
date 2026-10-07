# 抓取几何与接近约束拆分：2026-10-07

## 本轮改变

- `derive_visible_rim_geometry` 提取当前可见高处碗沿、机器人 hand Y 方向和 pad offset，并生成世界系候选位置；仍检查 mask/depth 质量和近似向下的 hand Z。
- `assess_rim_approach` 独立报告高度范围与距当前 EEF 的距离是否满足旧动作 canary 限制。通过该检查仍不代表 IK 可达或路径无碰撞。
- 旧 `make_visible_rim_candidate` 保留原有高度范围 [0.915,1.05]m 和距离上限 0.2m；超限仍抛出异常。原有服务器动作脚本不受放宽。
- 独立候选包改用拆分后的几何生成器，manifest 明确更新为 v2；可保存超出直接动作距离的几何候选，作为后续规划输入。
- 新增预抓取平移路点 proposal：调用已有 `make_pregrasp_plan`，按可见目标 mask 点群生成上方路线，保留原工作区、0.35m 位移、深度与 clearance 限制。输出禁止执行。

预抓取路线只到 mask 中央上方，尚未衔接到碗沿 anchor；不是完整抓取轨迹。未做关节 IK、扫掠体、障碍净空或碰撞验证，也不改变 online admission 拒绝状态。

## 真实历史帧回放

同一输入 `visual-policy-dual-query-20261004/frames/step000014`。

输出：`D:\大三上\科研\visual-grasp-approach-split-20261007\planning-with-waypoints\planning_input.json` 及 `visible_geometry.npz`；整体回放报告为该根目录的 `replay-with-waypoints.json`。本轮未启动服务器仿真或下发动作。

碗沿候选结果：

- 高度 0.935449m，落在旧范围内。
- 距当前 EEF 0.318190m，超过 0.2m。此次拒绝来自距离检查，未触发高度检查。
- 几何 anchor [-0.067783,0.146154,0.949047]m；pinch candidate [-0.067906,0.146160,0.935449]m。
- geometry_status 为 `visible_rim_candidate`；approach pose gate 为 refused。不能由此推断该位置可抓住目标。

预抓取 proposal 生成成功，三个世界系位置为：

1. [-0.198567,-0.015692,1.176233]m
2. [-0.084566,0.201810,1.176233]m
3. [-0.084566,0.201810,1.069641]m

proposal 标记 `unverified_waypoint_proposal`，execution_allowed=false。机器人和仿真本轮动作均为 0。旧失败记录原样保留，不将以前的 refused 改记成成功。

## 验证与下一步

48 项相关测试通过。新增检查 EEF 位置改变不移除相同碗沿几何、距离与高度分别报告、旧动作入口超限仍拒绝、通过 pose gate 仍无可达性/碰撞证书、跨步候选拒绝、路点 proposal 不能授权执行。受支持的旧动作候选输出与拆分几何输出保持一致。

下一项是静态机器人模型的基座/末端参考系契约和路点的观测碰撞检查，再补预抓取到碗沿的轨迹衔接。完整 cuTAMP solver bridge、独立技能在线准入和 A/B/C 实验仍未完成。
