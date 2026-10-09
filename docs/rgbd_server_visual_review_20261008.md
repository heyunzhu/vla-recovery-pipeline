# 启智 RGB-D 视觉诊断复核（2026-10-08）

仅访问 `可上网GPU资源` 的 `xinghanbo-eval`。实例运行正常，4090 GPU 在检查开始与结束时均为 0% 利用率、9 MiB 显存；未修改其他实例。此次新增实验只对保存图像运行感知及绑定回放，环境动作和规划调用均为 0，感知进程已经退出。

## 数据与范围

服务器实验根目录：
`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008`。

本轮新增产物在该目录的 `review_visual_20261008/`。本地下载产物位于 `analysis_outputs/rgbd_server_review_20261008/`（Git 忽略），包括原始 RGB-D、联合查询检测、配置、原始 grounding boxes、mask/绑定审计。

task 1 保存帧为 `libero_spatial_task1_init0_settle10`，env_step=10，agentview，256×256。RGB SHA256：`cb995b62d7938e5ae626fa6fab994793cb79d63a0e9f11fa8c9ffb9d6569e40c`。语言：`pick up the black bowl next to the ramekin and place it on the plate`。

## 本轮实际回放与新 GPU 感知对照

| 输入 | 检测数 | 绑定结果 |
|---|---:|---|
| task 1 原有逐类别查询 | 10 | goal_ambiguous，4 个 plate 候选 |
| task 1 新联合查询 | 4 | goal_ambiguous，2 个 plate 候选 |
| 原 snapshot 联合查询 | 1 | reference_not_observed |
| 原 snapshot 逐类别查询 | 13 | reference_ambiguous |
| task 6 自动检测 | 7 | goal_ambiguous，3 个 plate 候选 |
| task 6 原有手工检测 | 5 | visual_id_candidate |

task 1 逐类别检测有三个区域各自被赋予 bowl、ramekin、plate 三种类别，共 9 对跨类别 mask 逐元素完全相同（IoU=1）。provider 给这些检测分别分配视觉 ID；取消重叠拒绝没有完成类别消歧。

新联合查询使用同一保存帧、相同模型、相同 0.25 box/text 阈值和语言提示；新 detector ID 为 `grounded-sam2-ba6db81743d7`。两个 plate 分数分别为 0.396459、0.315363。对原图与 grounding boxes 作目视检查，前者框在左下碗状区域，后者框在右下盘子；这只是单帧人工检查，不是独立标注集或精度评测。bowl 与 ramekin 查询也落在同一个区域。选择最高 plate 分数或提升阈值不能据此视为可靠修复。

## 服务器今天已有的规划结果（本轮未重跑）

task 6 手工检测、去掉未命名障碍后，初始目标碰撞 cost=0；pad-model HandEmpty 推断后进入优化，但没有可行计划。下移抓取参考点约 25.27 mm 后仍失败；记录的各粒子位置误差最小值约 22.37 mm，大于日志中的 5 mm 门槛。逐约束最小值可能来自不同粒子，不能组合成一个候选的验收结果。

对应真值诊断也失败：task 6 位置误差最小值约 4.37 mm，仍有 robot_to_movables 约束不满足；task 1 真值诊断位置误差最小值约 10 mm。现有比较中视觉使用 6 DOF、真值使用 4 DOF，几何和障碍集也不同，不是严格同条件 A/B，不能把失败都归因于 RGB-D。

手工检测和丢弃未命名障碍均为隔离诊断条件，不构成自主感知通过或完整碰撞世界通过。自动 task 6 仍在绑定阶段失败。

## 当前判断与建议

1. 优先修复实例级语义：将同一可见区域的跨类别重复作为竞争假设，而不是独立物体；通过 RGB 外观、深度形状和关系共同核验，无法消歧时保留 unknown。
2. 在固定保存帧上建立小型可见实例标注集，检查漏检、重复类别、目标及参考物绑定正确率；逐类别/联合查询必须按正确绑定而非检测条数比较。
3. 用同一个已确认目标与相同抓取/优化配置建立可行的真值规划对照，再逐项替换视觉几何，隔离 origin/grasp frame、tool offset、碰撞表示及优化预算。
4. 验证时保留完整未命名障碍；手工修正和无体素版本只用于归因。取得可行轨迹后再继续稳定持物、放置及在线闭环验收。

目前没有新增 recovery 成功样本。本轮没有修改运行时代码、现有技能包或现有实验结果。
