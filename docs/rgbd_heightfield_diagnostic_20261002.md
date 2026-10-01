# Plate 高度场与分辨率诊断（2026-10-02）

## 做了什么

新增 `visual_heightfield.py::visible_heightfield_diagnostic`，直接从绑定 plate 的有效 RGB-D mask 提取可见点，不以全局平面拟合通过为前提。将世界 XY 分为 3 mm 格子，保留每格点数、平均/最低/最高可见 Z；空格保持 NaN、不插值、不填洞。至少 3 个观测点且格内 Z 极差不超过 4 mm 才标记为 witnessed。局部高度变化门槛不要求不同格子高度相同，因此可保留整体曲面。

目标与 mask 索引/哈希、当前帧、任务绑定均验证。仅支持当前可见 plate 的 `on` 关系；目标边缘截断、深度不足等显式拒绝。依旧用完整可见 bowl XY 凸包、当前投影姿态、5 mm 边距做水平平移诊断，未换成底部接触足迹。报告给出满足容纳条件的中心数，以及所有已观测中心中最少还缺多少个包络格子的证据。NPZ 保留逐中心缺证据格子数，不输出执行位姿。

序列评估增加 `--heightfield-diagnostics-dir`，可独立保存高度场网格，或与平面诊断并行。两种 artifact 必须使用不同新目录；旧实验产物保留。接口仍为 `planning_allowed=false`。

## 512 与 1024 的结果

沿用 task 0、init 1、seed 11、静置 10 步。512 为已有四帧序列；补采 1024 同一初始状态的双相机 reset 后帧，两个相机深度有效比例均 1.0，无 VLA/recovery 执行。采集于本次跨日期工作中，目录仍保留开始工作时的 `20261001` 名称，本文按完成时日期记录。服务器目录 `/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init1-settled10-1024-20261001`，本地同名目录位于 `D:\大三上\科研`。

远端使用个人快照中新脚本 `collect_rgbd_snapshot_settled_20261001.py`，上传前检查路径不存在，上传后 SHA-256 与本地一致：`3ee5f334f29c555bd9e408523ea42a4c203023f763df54b15427519e49ad146e`。没有修改全局环境或共享仓库。

1024 检测前查看原始 RGB、标 4 个实例内点和 1 个柜体负点，绑定帧哈希。沿用冻结 `black bowl / plate / silver ramekin`、模型权重与阈值；检测得到 4 个实例，正点 4/4、负点无命中、无 mask 冲突。因为输入大小改变，detector ID 为 `grounded-sam2-45cce0fdcab7`，不能与 512 的 `grounded-sam2-a62b7dbfbf7a` 混作同一配置序列。

| 检查 | 512 原检测，四帧 | 1024 原检测，一帧 | 1024 使用冻结 512 mask 对照，一帧 |
| --- | --- | --- | --- |
| 高度场网格 | 44×43 | 46×45 | 44×43 |
| witnessed 格子 | 每帧 959 | 1551 | 1436 |
| bowl 可见包络跨度 | 约 109.17×109.64 mm | 约 109.75×110.29 mm | 约 123.59×110.34 mm |
| 目标包络格子数 | 每帧 1348 | 1398 | 1456 |
| 最少缺证据格子 | 每帧 419 | 10 | 87 |
| 满足容纳条件的中心 | 均 0 | 0 | 0 |

512 高度场保留的可见 Z 范围约 0.90697–0.91828 m，跨度 11.31 mm。1024 原检测保留约 0.90676–0.91900 m，跨度 12.24 mm。1024 单平面拟合仍因质量门槛拒绝，但独立高度场能保留观测。这验证了曲面表示不必依赖平面准入，不等于放置验证通过。

归一化 mask 对照将 512 首帧检测 mask 用最近邻精确放大 2 倍用于 1024 深度，并将腐蚀从 2 像素变成 4 像素。已检查两帧相机变换、本体状态相等以及 K 前两行倍数关系；类别、mask 的归一化轮廓保持固定，backend 明确标记 `diagnostic-nearest-upscaled-frozen-512-masks`，没有冒充 1024 模型输出。此对照仍发现 target 可见包络变宽，说明更密集的边缘深度采样与 mask 边界相互作用，会影响“全部点的包络”。需要核验边缘混入背景的可能性，不能把变宽当作真实物体尺寸变化。

网格统计规则与上一轮平面格子规则不同，不能将高度场的 witnessed 格子数与平面 839 格直接当作同一指标的准确率提升。1024 原检测的变化也同时包含 mask 变化和像素腐蚀的物理宽度变化。归一化对照减少了这两项混杂，但仍有光栅化/边缘采样差异；目前只是一个场景的诊断，不能报告分辨率泛化收益。

## 证据与复现

- [512 四帧高度场报告](rgbd_heightfield_512_report_20261002.json)
- [1024 原检测报告](rgbd_heightfield_1024_report_20261002.json)
- [1024 冻结 mask 对照](rgbd_heightfield_matched_masks_report_20261002.json)

本地 512 序列报告 `agentview_heightfield_report_20261002_v2.json`，网格目录 `heightfield_20261002_v2`；1024 报告 `visible_geometry_report_20261002_v2.json`、`matched_mask_geometry_report_20261002.json`，网格位于 `agentview/heightfield_diagnostic_20261002_v2.npz` 及 `agentview/frozen512_masks_control_20261002/heightfield_grid.npz`。点位标注、原始检测和逐帧 RGB-D 均保留。

高度场 NPZ 包含 `point_counts`、`witnessed_cells`、`visible_mean_z_m`、`visible_min_z_m`、`visible_max_z_m`、网格原点/间距、可见包络/平移格子、容纳中心和 `footprint_unwitnessed_cell_counts`。最低/最高/平均值也保留未达门槛但有观测的格子，使用时必须同时检查 witnessed mask。

复现 512 序列时，沿用上一轮 `evaluate_rgbd_goal_surfaces.py` 命令，将网格输出参数设为 `--heightfield-diagnostics-dir` 并指定未存在的新目录；模型、提示词、工作范围保持原样。

完整 skill-pipeline 测试 **579 项通过**。新增检查覆盖曲面高度保留、孔洞不插值、局部高度突变拒绝但保留原始值、曲面不需要全局平面准入、mask/帧一致性及深度/范围不足拒绝。

## 接下来推进什么

先核验 target mask 边缘与深度的不连续，结合已同步采集的腕部视角检查可见下部轮廓；将 bowl 碗口包络与可见下部形状分开报告，仍不能将其自动认作真实接触足迹。之后才能定义用于 cuTAMP 的几何代理及其缺失值/拒绝规则。高度场有观测点不保证格子内连续支撑，曲面法向、接触稳定性、完整碰撞体和运动路径均未验证。本轮仍无在线 RGB-D recovery 结果。
