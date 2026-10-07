# 夹爪 pad/collision 表面对照：2026-10-07

## 本轮交付

`project_static_gripper` 新增独立 `geometry_mode=collision`，从经过摘要检查的静态XML提取 group0 mesh 和两个 finger pad box。box按 XML half extents 和局部位姿生成12个三角形，与静态 finger slide qpos、EEF参考系和相机标定一起投影。

默认 visual 模式仍只使用 group1 mesh，默认2mm阈值不变。collision投影仅用于比较，路径消费者明确拒绝拿collision proxy mask剔除观测点；没有把保守碰撞壳体误当成机器人实际可见表面。

新增 `compare_gripper_surfaces.py`，输出投影NPZ、模型摘要和指定像素及5×5邻域的深度残差。邻域分析只读取历史观测，未改变标定/阈值/目标选择。

## 真实历史帧结果

输入同一episode step14，关注此前两个最近剩余像素。输出目录：

`D:\大三上\科研\visual-gripper-surface-contrast-20261007`

| 像素 | 观测深度m | visual残差mm | collision残差mm | visual邻域残差中位数mm | collision邻域残差中位数mm |
| --- | --- | --- | --- | --- | --- |
| [271,123] | 0.934524 | 5.074 | 5.031 | 0.418（15有效点） | 0.856（15有效点） |
| [288,109] | 0.913007 | 6.869 | 6.526 | 0.533（21有效点） | 0.602（21有效点） |

两个准确像素在两种模型下均不满足2mm一致阈值。增加collision/pad投影并未解决原残差。局部邻域大多数点拟合较好，支持检查局部边界/采样差异，但中位数不证明异常像素属于机器人，也不证明没有前景物体。

旧路径的11个相交中心结论仍保留，本轮没有重新把它们改判为“清空”。两个像素归属仍unknown。

## 验证

27项针对性测试通过，包括box近表面深度/三角形数、无效尺寸拒绝、collision投影不能剔除点、机器人像素/路径/既有rasterizer/规划证据回归。实际XML及pad几何由真实历史帧回放运行。执行动作0，solver/execution未授权。

## 下一步

末端球代理不能等价完整夹爪碰撞体。下一项应使用实际夹爪collision几何构造路径采样体，并将观测一致点与未解释点分别传入检查；继续保留边界未知，补充关节IK与完整机械臂约束。不要再通过调宽像素阈值制造路径通过结果。
