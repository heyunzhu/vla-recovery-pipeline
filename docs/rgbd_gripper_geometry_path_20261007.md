# 夹爪碰撞几何路径检查：2026-10-07

## 本轮交付

静态夹爪loader被提取为 `load_static_gripper_geometry`：由已校验XML/mesh、当前gripper qpos、EEF pose生成世界系部件三角形。默认projection复用这一加载器，visual模式未更改。

新增 `visual_gripper_path.py`，沿已有预抓取位置每10mm采样，用以下部件检查有效RGB-D点群：

- hand_collision、finger1_collision、finger2_collision：从三角形支持面推导保守凸外包半空间，并加世界系AABB约束。不是原生cuTAMP/MuJoCo mesh碰撞查询。
- finger1_pad_collision、finger2_pad_collision：静态XML pad box的精确多面体。
- 点落入各部件半空间外扩2mm区域视为诊断相交；margin显式记录。合并计数去除不同部件对同一点的重复，但相邻位姿端点仍可能重复。

每个采样位姿保持当前方向和夹爪开度，仅平移位置；不是IK或真实关节轨迹，也不覆盖机械臂。旧球代理结果同时保留。对原始点群和仅剔除2mm深度吻合visual自身像素后的点群分别计数，不把collision mask用于点剔除。

## 真实历史帧结果

同一step14数据的输出：`D:\大三上\科研\visual-gripper-geometry-path-20261007\planning`。`planning_input.json`保存路径结果，`visible_geometry.npz`保存点群、模型深度及visual自身mask；整体报告根目录 `replay.json`。

| 指标 | 结果 |
| --- | --- |
| 路径采样位姿 | 40 |
| 原始点群相交位姿 | 15 |
| 剔除已吻合自身像素后的相交位姿 | 15 |
| 相交范围 | index 0—14（包含起点/重复端点） |
| 初始位姿原始相交点并集 | 7245 |
| 初始位姿剩余相交点并集 | 187 |

初始位姿剩余点分别命中hand、finger和pad部件；移动初段后主要命中hand外包体。报告提供每个部件命中数和首个像素，示例hand[276,44]、finger1[202,109]、pad1[214,115]、finger2[280,109]、pad2[271,120]。这些首个像素未落在当前物体mask内；不代表该部件所有命中点都已完成分类。

**15个相交位姿不能记作15次外部碰撞。**世界点群含未被解释的自身表面，旧机器人位置在离线点群中不会随候选平移消失；mesh外包体也可能保守扩大。后半段未命中可见点不能证明未知空间清空。

本轮没有把相交结果改成“路径通过”，没有执行动作。

## 验证与限制

33项针对性测试通过（新增6项几何路径测试，加上像素、路径/参考系、rasterizer和规划证据）。检查精确box内外分类、旋转box局部形状、显式margin、部件随路径平移、原始统计保留、自身点移除不授权执行、错误帧/visual几何拒绝。实际五部件模型已在历史数据回放中运行。

完整夹爪连续扫掠体、机械臂碰撞/自碰撞、未知空间、关节IK及solver bridge均未完成。下一步优先补静态Panda关节IK与路点关节轨迹，再按实际关节状态更新各部件，而不是把固定姿态平移当作机器人可执行路径。
