# Target mask 边缘与双视角几何诊断（2026-10-02）

## 交付与方法

新增 `visual_mask_depth_diagnostic.py`，对已绑定 bowl 的同帧 mask 做边界/深度检查及 0、1、2、4 像素腐蚀敏感性对照，保留每个方案的点数、全部可见 XY 跨度、Z 百分位和低高度带跨度，不自动替换原始检测或选择最有利的轮廓。边界邻近像素的光轴深度跳变阈值固定为 15 mm；跳变可能来自真实轮廓、遮挡或背景，并不直接等于误分割。

低高度带取全部满足 `z <= visible_z_percentile_2 + 10 mm` 的有效点，保留更低的尾部以暴露背景污染。该上界规则不代表距离真实桌面或底部 10 mm，锚点也是可见点的统计量。尤其对碗，低处的可见表面可能是碗内底面，不能据此认定外底部接触形状。

双视角检查将 agentview 目标 mask 的世界点投影到同时间、同 episode/env_step 的腕部相机；核对标定版本与白名单本体状态一致。记录投影是否入图、对应深度是否有效、光轴深度是否在 5 mm 内一致、目的深度在预测点前/后。只报告几何关联，`identity_fused=false`，不生成跨相机语义实例或碰撞模型。不同步帧和本体状态拒绝。

新增 CLI `diagnose_rgbd_target_geometry.py`，复用冻结提示词、RGB-D/检测 artifact 与语言绑定校验，输出可重放目标诊断；场景或语言绑定拒绝时保留明确拒绝。当前所有输出 `planning_allowed=false`。

## 保存数据的结果

使用已有 1024、task 0/init 1/seed 11、静置 10 步的双相机帧；没有新增调词或仿真采集。比较 1024 原始模型 mask 与上一轮最近邻放大的 512 冻结 mask：

| 检查 | 1024 原模型 mask | 放大 512 mask |
| --- | --- | --- |
| 原始可见 XY 跨度 | 109.75×110.29 mm | 123.59×110.34 mm |
| 腐蚀 1 像素后跨度 | 109.06×108.85 mm | 109.06×108.89 mm |
| 有效边界像素 / 邻接深度跳变像素 | 504 / 214 | 504 / 165 |
| 0 腐蚀低高度带跨度 | 91.56×85.71 mm | 108.05×99.37 mm |
| 腐蚀 1/2/4 像素低高度带跨度 | 各约 50.02×73.54 mm | 各约 50.02×73.54 mm |

放大 mask 的全部点包络在去掉一圈边缘后，x 跨度由约 124 mm 降到约 109 mm，支持边缘深度关联影响包络的判断。原始 mask 的低高度带也对一圈边缘敏感。去边缘后的低高度带趋同只是观测稳定性，不能证明其为底部接触足迹；没有把 50×74 mm 区域送入容纳判断或 planner。

1024 原模型 mask 的 12102 个源可见点中，10093 点投影进入腕部图像（约 83.4%），其目的深度全部有效。8275 点光轴深度差在 5 mm 内（占全部源点约 68.4%）；1721 点目的深度更近、97 点更远。腕部原始 RGB 目视显示目标 bowl 在左边界被截断，plate 也部分出图。近处深度可能反映遮挡或其他可见表面，不能直接融合为目标外形；这些观测不足以证明完整外部轮廓或隐藏底部。放大 mask 对照的投影统计相近，完整数值见 [机器报告](rgbd_target_boundary_report_20261002.json)。

## 复现与验证

本地数据根目录 `D:\大三上\科研\rgbd-spatial-task0-init1-settled10-1024-20261001`，保存 `target_boundary_report_20261002.json` 及 `target_geometry_cli_report_20261002.json`，腕部原始预览为 `robot0_eye_in_hand/raw_preview.png`。原始 RGB-D、标定、检测与放大 mask 对照均保留。

```powershell
$root = 'D:\大三上\科研\rgbd-spatial-task0-init1-settled10-1024-20261001'
& 'D:\大三上\科研\.venvs\vla-dev\Scripts\python.exe' `
  scripts/recovery/skill_pipeline/diagnose_rgbd_target_geometry.py `
  "$root\agentview" "$root\agentview\grounded_sam2_silver_ramekin_v1" "$root\summary.json" `
  --prompts-json 'D:\大三上\科研\rgbd_prompt_silver_ramekin_20260929.json' `
  --other-camera "$root\robot0_eye_in_hand" --out "$root\target_geometry_replay.json"
```

放大 mask 对照为派生诊断 artifact，不是模型直接输出。该对照用 `load_detections` 核对原始帧哈希后，调用相同 `mask_depth_diagnostic` 和 `cross_view_depth_diagnostic` 函数；CLI 默认仍要求冻结模型提示配置，不将派生 mask 冒充原始检测。

完整 skill-pipeline 测试 **584 项通过**。新增检查覆盖边界深度跳变、原始 mask 不被修改、低深度证据不产生几何、同步不同相机的投影正例、遮挡深度不被融合，以及不同步/本体状态变化拒绝。

## 下一步与边界

当前证据支持把 mask 边界不确定性明确写入几何代理，并区分“全部可见包络”“内缩可见轮廓”“低高度可见表面”。接触足迹仍缺外底部证据；需要结合更合适的视角或明确的物体形状假设与执行反馈验证，不能把内底面直接作为外部接触面。下一阶段可先将缺几何/遮挡的拒绝规则接入 visual adapter 的在线 dry-run，核验不会回退 oracle，再逐步补抓取与执行验证。本轮没有在线恢复动作或成功率。
