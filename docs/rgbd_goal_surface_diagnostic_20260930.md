# Plate 可见表面几何诊断（2026-09-30）

## 本轮完成

新增 `visual_goal_surface.py::goal_surface_evidence`，将任务语言绑定的 plate 实例与同一 RGB-D 帧的检测 mask 关联，提取近水平可见平面。只支持 `on plate`；未绑定、非当前可见、历史实例、缺少 mask 来源、内部深度不足、无法拟合或质量未达阈值，均有明确拒绝原因。错误帧和 mask 来源不一致抛出错误。

`VisualObject` 新增本帧 `detection_index` 和 `detection_mask_sha256`。跟踪后的实例 ID 可以跨帧延续，但检测索引按每帧重建；历史实例清空索引和 mask 哈希。表面提取核对索引、类别、mask 哈希，不将 ID 数字当成检测数组位置。

默认将 mask 向内腐蚀 2 像素，只使用其中有效深度，再在调用方显式声明的工作范围中拟合。阈值为至少 200 个内点、残差容差 2 mm、RMS 不超过 1 mm、内点不少于全部有效内部点的 50%；沿用水平面拟合的最大坡度 0.15。输出 mask/内部/有效深度点数、平面法向和系数、可见 XY 范围、内点数、内点占比、RMS 与剩余检查项。

`export_visual_handoff.py` 增加两个可选输入：`--prompts-json` 显式指定冻结提示词变体，必须与检测配置一致；`--goal-surface-workspace-json` 指定 x/y/z 范围并导出 schema 2 的 `goal_surface_evidence`。不指定范围时仍输出 schema 1。默认任务语言模式仍要求该语言对应的提示词。所有模式均为诊断用途、`planning_allowed=false`。

新增 `evaluate_rgbd_goal_surfaces.py` 对整段序列先核对冻结模型配置、检测身份和实际环境步号，再用同一个 provider/tracker 导出逐帧表面证据。

## 已保存数据上的结果

使用静置 10 步后的 task 0、init 1、seed 11、512 像素 agentview 四帧，沿用冻结 `black bowl / plate / silver ramekin` 配置。范围为 x/y ∈ [-1,1] m、z ∈ [0.85,1.1] m，其他阈值均使用默认值；本轮没有重新调模型或提示词。

| 检查 | 四帧结果 |
| --- | --- |
| 表面状态 | 4/4 为 `visible_surface_candidate` |
| 同 tracker 目标 plate ID | 均为 `obj_003` |
| 本帧检测索引 | 2、2、2、1；末帧顺序变化仍正确关联 |
| 原始 mask 点数 / 腐蚀后有效点数 | 5260–5261 / 4604–4605 |
| 拟合内点 | 每帧 3196，约占有效内部点 69.4% |
| 可见边界中心处的平面高度 | 约 0.908339 m |
| RMS 拟合误差 | 约 0.859 mm |
| 可见 XY 百分位范围 | x 约 [0.01215,0.10701] m，y 约 [0.14862,0.24301] m |
| 执行授权 | 始终 `false` |

机器报告见 [四帧几何证据](rgbd_goal_surface_report_20260930.json)。本地原始数据和逐帧交接包位于 `D:\大三上\科研\rgbd-spatial-task0-init1-settled10-sequence-512-20260930`，逐帧文件名为 `visual_goal_surface_handoff_v1.json`。单帧导出会创建新的 tracker，因此其中 ID 仅在该文件内有效；跨帧 ID 结论应使用上述同 tracker 报告。

本地复现序列报告（PowerShell，在仓库根目录运行）：

```powershell
$root = 'D:\大三上\科研\rgbd-spatial-task0-init1-settled10-sequence-512-20260930'
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' `
  scripts/recovery/skill_pipeline/evaluate_rgbd_goal_surfaces.py $root `
  --detections-subdir grounded_sam2_silver_ramekin_v1 `
  --prompts-json 'D:\大三上\科研\rgbd_prompt_silver_ramekin_20260929.json' `
  --workspace-json "$root\goal_surface_workspace.json" `
  --out "$root\agentview_goal_surface_report_20260930.json"
```

## 解释与下一步

这一步提供的是 plate 可见表面的平面近似。可见 XY 范围是内点的 2%–98% 百分位矩形，矩形角点可能落在圆形 plate 外；它不是可容纳物体的放置多边形。平面可能包含 plate 的曲面或边缘，RMS 是点对模型的拟合误差，不能当作传感器精度。约 69% 的内点覆盖也不能证明完整支撑范围或无障碍。

原有 handoff 的 `goal_region_and_clearance` 未解决项继续保留。下一步需要保留精确可见区域、评估目标 bowl 的足迹能否落入区域，并检查障碍与净空，再补抓取和持物验证。没有读取 MuJoCo 物体状态、接触或任务成功信号，也尚未调用在线 cuTAMP/planner/executor。

完整 skill-pipeline 单元测试 **568 项通过**，包括 mask 限定几何、腐蚀范围、深度/范围不足拒绝、替换 mask 与错误帧拒绝、历史/非 plate 拒绝、拟合覆盖门槛，以及冻结提示词变体导出校验。
