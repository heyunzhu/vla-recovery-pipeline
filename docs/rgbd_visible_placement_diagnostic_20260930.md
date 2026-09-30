# 可见区域容纳诊断（2026-09-30）

## 本轮交付

新增 `visual_placement_region.py::visible_placement_diagnostic`，在已绑定的 plate 可见平面上建立 XY 网格，检查当前 bowl 可见轮廓的水平包络是否能平移进入该区域。没有读取物体模型、MuJoCo 物体位姿、接触或成功信号。返回诊断报告和可重放 NumPy 网格；所有输出 `planning_allowed=false`。

plate 的二维边界矩形只用于确定网格范围。每格必须把中心和四角投影回同一相机，五个采样均落在腐蚀后的 plate mask、有效深度和已拟合平面的残差容差内，才算有可见表面证据。外部、深度空洞、被遮挡或不满足平面条件的格子均不支持，不补洞，也不把矩形内全部空间视为可用区域。有限采样不能证明每格内部连续无洞，报告明确为 sampled containment。

bowl 取其 mask 内全部有效深度点的 XY 凸包，以可见 XY 边界中心为平移参考，保持当前姿态在水平面的投影；不搜索旋转。加入 5 mm 诊断边距及格子半对角线的包络，使用 3 mm 网格逐格检查。target 深度覆盖需至少 90%、有效点至少 20，mask 不能碰图像边缘；当前实例和 mask 哈希必须匹配。不存在满足条件的中心时返回 `no_sampled_visible_footprint_fit`，不输出执行位姿。

**可见 XY 包络不是 bowl 底部的接触足迹。** 它可能包含碗口，未知背面和底部也没有补全。即使找到采样容纳位置，也不能证明真实放置的稳定性、完整碰撞体或运动路径可行。隐藏形状、接触足迹、全支撑、语义、扫掠体积、抓取/持物与执行仍为未解决项。

## 冻结四帧数据的结果

使用 10 步静置后 task 0/init 1/seed 11 的 agentview 连续帧；模型、提示词、工作范围及平面阈值沿用上一轮。新增网格/边距参数在本轮检查前固定为 3 mm / 5 mm，没有为获得候选降低阈值。

| 诊断量 | 四帧结果 |
| --- | --- |
| target / goal，同 tracker | `obj_002` / `obj_003` |
| target 可见 XY 包络跨度 | 约 109.17 × 109.64 mm |
| plate 全 mask 有效深度的 XY 跨度 | 约 134.35 × 135.71 mm |
| plate 已拟合平面的可见百分位跨度 | 约 94.86 × 94.39 mm |
| plate 可见 Z 的 2%–98% 范围 | 约 0.90698–0.91815 m，高差约 11.17 mm |
| 已取网格 / 有可见平面证据的格子 | 31×31 / 每帧 839 格 |
| 加边距后的 target 网格包络 | 每帧 1348 格 |
| 满足采样容纳条件的中心 | 四帧均 0 |
| 结果 | 四帧均拒绝：`no_sampled_visible_footprint_fit` |

结果说明当前“可见完整水平包络落入单一平面 patch”的条件未满足。plate 全部可见轮廓其实更大、表面也存在高度变化；仅用近水平内点会舍弃部分曲面。bowl 可见宽度也不能等同底部接触宽度。因此不能把拒绝解释为任务物理上不可完成，更不能用它估计 recovery 成功率。

机器报告见 [逐帧容纳诊断](rgbd_visible_placement_report_20260930.json)。本地数据根目录为 `D:\大三上\科研\rgbd-spatial-task0-init1-settled10-sequence-512-20260930`，详细报告为 `agentview_visible_placement_report_20260930_v2.json`，逐帧 NPZ 位于 `visible_placement_v2`。旧 v1 产物保留。NPZ 包含 `support_cells`、`visible_footprint_fit_centers`、`footprint_offsets_xy`、`origin_xy_m`、`cell_m`、`goal_observed_plane_mask` 和 `visible_hull_offsets_xy_m`，可重放格子检查与 mask 限制。

## 复现与验证

序列评估脚本增加可选 `--placement-diagnostics-dir`，在共享 tracker 的逐帧表面报告内写入 `visible_placement` 及 NPZ 路径。诊断目录必须为新目录，防止覆盖已保存网格；原来的纯平面评估仍可独立运行。以下命令重新计算报告，运行前确认输出目录尚不存在：

```powershell
$root = 'D:\大三上\科研\rgbd-spatial-task0-init1-settled10-sequence-512-20260930'
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' `
  scripts/recovery/skill_pipeline/evaluate_rgbd_goal_surfaces.py $root `
  --detections-subdir grounded_sam2_silver_ramekin_v1 `
  --prompts-json 'D:\大三上\科研\rgbd_prompt_silver_ramekin_20260929.json' `
  --workspace-json "$root\goal_surface_workspace.json" `
  --placement-diagnostics-dir "$root\visible_placement_replay_new" `
  --out "$root\agentview_visible_placement_replay_new.json"
```

完整 skill-pipeline 测试 **574 项通过**。新增检查覆盖：未知孔洞不填补、圆形区域不能变成包围矩形、边距扩大后候选减少、实际相机投影的正例、缺深度形成不支持区，以及 target mask 被替换/深度覆盖不足时拒绝。

## 下一步

将 plate 的可见曲面保留为高度场或多个局部 patch，分开报告平面拟合损失与语义 mask 范围；为 bowl 进一步寻找可由多视角 RGB-D 支持的接触区域，不能用碗口宽度或 MuJoCo 几何代替底部。容纳证据建立后仍需完整碰撞代理与运动净空检查，再与 cuTAMP 约定实际输入。当前在线视觉 recovery 仍未执行。
