# 2026-10-04：替代视觉描述的离线验证

## 结论

固定模型、阈值和联合查询方式，将提示词从 `black bowl / plate / silver ramekin` 改为 `black bowl / white plate / silver cup`，类别键仍为 bowl、plate、ramekin。新描述恢复第 30 步的绑定候选，但其他类别误覆盖增加，后期冲突仍存在，**未替换默认方案或部署服务器实验**。

| 同一轨迹 12 帧、44 个草稿可见点 | 原描述 | 新描述 |
| --- | ---: | ---: |
| 视觉绑定候选帧 | 5 | 6 |
| 绑定拒绝帧 | 4 | 3 |
| 场景冲突拒绝帧 | 3 | 3 |
| 恰好一个正确类别 mask 覆盖的点 | 35 | 37 |
| 仅有一个正确类别 mask 覆盖的点 | 32 | 34 |
| 被错误类别 mask 覆盖的点 | 3 | 6 |
| 整帧通过可见点、负点及全局冲突检查 | 5 | 6 |

这些数值基于助手目视检查草稿，未人工复核且不是盲标；只描述这批像素点的覆盖情况，不代表分割精度、任务成功率或泛化能力。正确类别点覆盖和独占覆盖均略有改善，但不能忽略增加的错误类别覆盖。

## 实验过程

使用已经保存的真实 Pi0 48 步轨迹观测，逐帧重新运行固定 Grounding DINO + SAM2，并在独立 provider 中回放绑定和时序诊断。原方案从其冻结缓存回放，逐帧状态与绑定核对一致。新配置有独立 detector ID `grounded-sam2-131f874bb541`，提示词源文件及全部产物哈希已保存。

视觉描述根据可见外观提出，是本轨迹的探索性调参。`silver cup` 被配置为 ramekin 的视觉别名，不是确认物体语义或颜色的独立证据。没有将标注点或仿真对象身份提供给模型。

第 10–30 步新描述给出候选；第 34/38/42 步为 `target_not_between`，说明目标碗仍缺少有效当前检测或绑定证据。第 46/50/54 步出现 bowl/ramekin 和同类别 ramekin 的重复重叠，继续拒绝场景。没有裁剪重叠 mask、按最高分消歧或降低门槛。

另对已有的 init0 第 1 步静态观测检查新描述，原、新两种配置均通过该帧 4 个旧参考点及负点检查。它是另一种布局的保存帧检查，参考同样为历史助手目视标注；没有运动序列、盲测或新的策略 rollout，不能外推到其他任务。

本轮没有启动仿真或策略，没有环境动作。指定三个 oracle 模块的导入尝试为 0；这一 guard 范围不等于全进程内存审计。恢复执行、持物和目标完成核验仍未通过。

## 实现与验证

离线比较脚本新增显式 `--candidate-prompts-json` 和 `--candidate-mode`，要求保持基线类别键，继续校验固定模型权重、库版本、配置与输入尺寸。原参数仍默认运行此前的 per_category 对照。

可见点评估脚本新增候选名称及模式参数，可以比较不同提示词的 joint 检测；原 per_category 默认参数保留。两条新参数路径已由完整 12 帧模型对照及缓存点评估实际运行验证，额外静态帧单独运行单帧检测和参考评估。未新增镜像参数的单元测试，也未重复运行未改动核心模块的完整测试。

## 证据与复现

- [12 帧视觉绑定和时序对照](rgbd_prompt_candidate_comparison_20261004.json)
- [44 个草稿可见点的配对评估](rgbd_prompt_candidate_points_20261004.json)
- [汇总、额外布局检查及产物源码哈希](rgbd_prompt_candidate_audit_20261004.json)
- [实验提示词配置](../experiments/robot/libero/skill_pipeline/fixtures/rgbd_motion_prompt_candidate_20261004.json)

完整数据：`D:\大三上\科研\rgbd-prompt-candidate-20261004`。
额外静态帧：`D:\大三上\科研\rgbd-prompt-candidate-init0-step1-20261004`。

在仓库根目录沿用 [前轮比较命令](rgbd_grounding_motion_diagnosis_20261004.md)，使用新的未存在输出目录，加上：

```powershell
--candidate-prompts-json experiments/robot/libero/skill_pipeline/fixtures/rgbd_motion_prompt_candidate_20261004.json --candidate-mode joint
```

运行 [点评估命令](rgbd_motion_point_references_20261004.md) 时，将 candidate-root 指向新产物目录，并加 `--candidate-name prompt_candidate --candidate-mode joint`。

## 后续推进

继续保留原默认方案。下一步优先研究混合标签的类别证据与可见对象身份连续性，使用已有像素点检查漏检和错误覆盖是否同时改善；针对遮挡明确返回未知状态。更长在线轨迹应在感知改进有离线证据之后运行，持物、支撑和目标完成不能由绑定候选直接推断。
