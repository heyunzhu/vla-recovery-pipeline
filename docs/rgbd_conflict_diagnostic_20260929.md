# RGB-D 重叠 mask 诊断（2026-09-29）

本记录针对 `libero_spatial` task 0、init 0、seed 7 的 4 帧固定相机 512×512 序列。输入是已保存的 RGB-D 和冻结 Grounding DINO tiny + SAM 2.1 tiny 检测结果；没有重新运行仿真、VLA 或 recovery。人工参考点仅用于离线误差分析，绑定和追踪都没有读取这些点。

## 固定提示词对照

原始任务语言提示词为 `black bowl`、`plate`、`ramekin`。四帧各有 4 个从原始 RGB 人工目视选取的实例内点（两个 bowl、一个 plate、一个 ramekin），另有 1 个左侧柜体上“不得检出 plate”的负样本点；它们分别与该帧 RGB SHA-256 绑定，保存在序列的 `stepNNN/agentview/visual_reference.json`。这不是完整分割真值，只能检查选定点上的漏检与误检。

| 提示词 | step 0–2 | step 3 | 结果 |
| --- | --- | --- | --- |
| 原始任务语言 | 每帧 bowl/plate/ramekin 为 2/2/2；正样本 4/4；负样本 plate 命中 1/1；各有一对 bowl/ramekin mask 完全重叠 | 2/2/1；正样本 4/4；负样本 plate 命中 1/1；无重叠 | 原始在线场景准入为前 3 帧拒绝、末帧接受；四帧均有同位置 plate 误检。 |
| 固定冠词变体 `a black bowl`、`a plate`、`a ramekin` | 每帧 0/1/1；正样本 2/4；负样本未命中；无重叠 | 1/1/1；正样本 3/4；负样本未命中；无重叠 | 消除冲突和此处误检的同时漏掉关键 bowl，不能代替原始提示词。 |

冠词变体在另一项 `libero_spatial` task 1 reset 帧上也没有通过：原始检测为 bowl/plate/ramekin 2/1/2 且有冲突；变体为 1/1/2，冲突消失但参照物仍无法唯一绑定。这组对照没有依据单帧结果修改阈值或选择线上提示词。

四帧中额外 `plate` mask 的像素框均约为 `(153, 211, 215, 256)`，面积为 2,222–2,223 像素，覆盖左侧柜体而非盘子。原来的正样本点 4/4 指标无法发现此错误。离线 `visual_perception_eval` 现支持可选的 `negative_points`，会报告禁用类别在指定点的命中；即使正样本全部匹配，只要负样本命中就不通过。该点只用于离线评估，不进入检测或在线绑定。

八组逐帧、逐提示词的机器可读点位评估保存在序列根目录 `agentview_reference_eval_20260929.json`（原始数据不提交 Git）。

## 冲突假设回放

新增 `scripts/recovery/skill_pipeline/evaluate_rgbd_conflict_hypotheses.py`，只离线检查每帧**恰好一对**冲突 mask 的两个“去掉其中一个”假设；若有多对冲突则不枚举。每个假设用 RGB-D 可见质心和任务语言运行现有绑定器，完整记录保留/去掉的检测及拒绝原因。只有恰好一个假设得到 ID 候选，诊断追踪器才用它推进下一帧。普通 `RGBDSceneProvider` 始终先对**原始检测**做准入，前 3 帧仍拒绝，假设场景绝不输出给在线执行器。

| 帧 | 去掉 bowl | 去掉重叠 ramekin | 原始准入 | 诊断追踪目标 ID |
| --- | --- | --- | --- | --- |
| 0 | `reference_ambiguous` | 待属性核验的目标候选 | 拒绝 | `obj_002` |
| 1 | `reference_ambiguous` | 待属性核验的目标候选 | 拒绝 | `obj_002` |
| 2 | `reference_ambiguous` | 待属性核验的目标候选 | 拒绝 | `obj_002` |
| 3 | 无冲突 | 无冲突 | 接受 | `obj_002` |

在这个**受任务语言筛选的假设链**里，目标 `obj_002`、plate `obj_003` 和两个参照物 ID 跨 4 帧保持一致。机器可读报告位于序列根目录的 `agentview_conflict_hypotheses.json`。这只是“若去掉重复 ramekin 检测，追踪可连续”的条件性结果；空间关系不能独立证明语义类别，`black` 颜色尚未核验，四帧 plate 误检仍在。不能报告原始感知的四帧 ID 稳定率，也不能把假设转为可执行场景。

## 下一步

优先解决独立的类别/属性证据及误检排查，例如在不以任务关系筛选结果为标签的情况下评估 bowl、ramekin、plate 的实例分类与颜色；随后再在新的初始状态和遮挡/移动序列上复核。场景准入只有在检测本身无实例冲突、目标与参照物唯一、属性和放置区域核验完成时才进入在线 runner/planner/executor。当前还没有 RGB-D recovery 闭环或成功率。
