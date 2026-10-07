# 路径近邻点与静态夹爪投影：2026-10-07

## 本轮交付

新增 `visual_robot_pixels.py`，使用静态 PandaGripper XML、visual mesh、两个 finger slide qpos、白名单 EEF pose 和相机标定，生成当前视角的夹爪深度投影。复用已测试的 perspective-correct rasterizer，不创建仿真器或读取场景物体信息。

模型目录显式指定：`--robot-model-dir` 配合离线 replay 的 `--planning-dir`。检查已审查的 gripper XML SHA-256、实际 XML/mesh 文件摘要以及文件路径在模型目录内；变更模型拒绝投影。这里投影 visual group 1 mesh，没有完整 arm，也不包含所有 collision/pad box 几何。

仅当模型和有效观测深度相差不超过2mm时标记 `RobotPixelEvidence`。报告绑定完整输入帧摘要，mask和mesh depth输出不可变；路径消费者重新验证mask严格遵循声明深度阈值，裸mask不能直接传入。

原始路径诊断完整保留。在第二组距离统计中去掉模型深度吻合点，其他点仍保留；原有深度探测与 unknown-space 判定不因剔除自身点变成自由空间。

## 实际历史数据回放

输入：`visual-policy-dual-query-20261004/frames/step000014`。

模型：`D:\大三上\科研\static-panda-model-20261004`。

输出：`D:\大三上\科研\visual-path-robot-pixels-20261007\planning-with-witnesses\planning_input.json` 及 `visible_geometry.npz`，整体报告根目录 `replay-with-witnesses.json`。NPZ包含模型深度和depth-matched gripper mask。

| 指标 | 结果 |
| --- | --- |
| 模型投影像素 | 8542 |
| 2mm内与有效观测深度吻合 | 7058 |
| 剔除吻合点后的可见点数 | 255086 |
| 原球代理路径相交中心 | 11 |
| 剩余点群相交中心 | 11 |
| 剩余点群最小距离 | 14.922mm |
| near-plane跳过三角形 | 0 |

## 相交证据的含义

前10个相交中心（0—9）的最近剩余点均为像素[271,123]，模型投影覆盖，但观测深度比模型深5.074mm；第10号中心的最近剩余点是[288,109]，差6.869mm。两个点均不落在现有物体mask内。

这些点没有满足2mm一致阈值，因此没有被移除。不能因为“在夹爪投影内”或“分割未分类”就认定为机器人像素，也不能记作外部障碍。可能涉及模型视觉表面、姿态/投影误差、边界或遮挡；本轮没有独立证据确认具体原因。11个相交中心不是11个独立障碍点。

## 验证及范围

25项针对性测试通过（机器人像素、路径/参考系、既有rasterizer、规划证据）。覆盖原始检查保留、只移除吻合点、阈值不符/错误帧/裸mask拒绝、前景遮挡不能凭silhouette移除、最近点像素索引、模型摘要变更拒绝及既有几何回归。实际XML/mesh投影由历史帧回放验证；合成mask测试不作为真实机器人识别精度证据。

本轮没有新增服务器动作。机器人像素归属、完整夹爪/机械臂碰撞、连续扫掠体、IK和solver bridge仍未验收；execution_allowed始终false。

下一步优先检查两个剩余像素附近的局部模型/观测深度和边界，用实际夹爪collision/pad几何补齐诊断，再决定哪些点有足够证据标记自身。不能通过扩大阈值清除相交计数。
