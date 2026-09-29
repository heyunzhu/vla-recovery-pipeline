# RGB-D 分割提示词受控对照

记录日期：2026-09-29。固定模型、权重、512×512 输入、box/text 阈值 0.25/0.25、序列和人工参考点，只替换提示文字。此实验使用冻结的 Grounding DINO tiny + SAM 2.1 tiny；所有数据为保存帧的离线回放，没有 VLA 或 recovery 执行。

## 开发序列结果

任务：`libero_spatial` task 0、init 0、seed 7 的 4 帧 `agentview`。每帧有两个 bowl、一个 plate、一个 ramekin 的 4 个人工正样本点，另有左侧柜体上禁止 `plate` 的 1 个负样本点。这些点只用于评估，不参与模型输入、实例绑定和追踪。

| 提示词方案 | 正样本命中 | 柜体 plate 误检 | mask 冲突 / 场景拒绝 | 目标候选及 ID |
| --- | --- | --- | --- | --- |
| 任务语言原样：`black bowl / plate / ramekin` | 4 帧均 4/4 | 4/4 帧 | 3/4 帧 | 仅末帧候选，无法测多帧 ID。 |
| 加冠词：`a black bowl / a plate / a ramekin` | 前 3 帧 2/4、末帧 3/4 | 0/4 帧 | 0/4 帧 | 漏掉目标 bowl，不能替代原方案。 |
| **仅改 ramekin：`black bowl / plate / silver ramekin`** | **4 帧均 4/4** | **0/4 帧** | **0/4 帧** | **4 帧均有待属性核验候选，目标 ID 均为 `obj_002`。** |
| 再改 plate：`black bowl / white plate / silver ramekin` | 第 1 帧 3/4，其余 4/4 | 0/4 帧 | 0/4 帧 | 4 帧均有候选，但第 1 帧漏掉第二个 bowl。 |

上述结果来自每帧的 `perception_eval.json` 和同一个 tracker 的序列回放。变体序列评估保存在本地 `D:\大三上\科研\rgbd-spatial-task0-sequence-512-20260928\agentview_silver_ramekin_sequence_eval.json` 及相应 `white_plate` 文件，原始检测/mask 均在各帧的 `grounded_sam2_*` 目录，未提交 Git。`evaluate_rgbd_sequence.py --prompts-json` 现会核对每帧同一组冻结提示词及 detector ID；原有任务语言模式保持不变。

## 独立任务检查与边界

将开发序列上表现最好的 `silver ramekin` 方案**原样**用于 `libero_spatial` task 1、init 0、seed 7 reset 帧，得到 1 bowl、1 plate、1 ramekin，无遮罩冲突，任务语言绑定输出 `candidate_requires_attribute_check`。叠图目视可见左侧另一个 bowl 未检出；这项检查没有预先制作完整实例标注，因此不能报告跨任务召回率，更不能称为泛化通过。

另在服务器个人目录采集**未参与调词**的 `libero_spatial` task 0、init 1、seed 11 的双相机 4 帧短序列，服务器目录 `/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init1-sequence-512-20260929`，本地同名目录位于 `D:\大三上\科研`。八帧深度有效比例均为 1.0。运行检测前，先查看四帧原始 RGB，为每帧保存 4 个实例内点及 1 个柜体负样本点，并绑定 RGB SHA-256。随后仅重放原始任务语言方案与此前冻结的 `silver ramekin` 方案，没有再更改阈值或提示词。

| 新 init 1 序列 | 原始任务语言 | 冻结 `silver ramekin` |
| --- | --- | --- |
| 4 个正样本点 | 4 帧均 4/4 | step 0 为 3/4（漏后方 bowl），step 1–3 为 4/4 |
| 柜体负样本点 `plate` 误检 | 4/4 帧 | 0/4 帧 |
| mask 冲突及场景拒绝 | step 0 拒绝，step 1–3 接受 | 4 帧均无冲突、均接受 |
| 任务目标 ID 候选 | step 1–3 有候选且 ID 一致 | 4 帧有候选且 ID 一致 |

对应机器报告为新序列根目录的 `agentview_baseline_sequence_eval.json` 与 `agentview_silver_ramekin_sequence_eval.json`；每帧 `perception_eval.json` 保留点位检查。新初始状态说明该变体改善并非仅限原来的一帧，但也直接暴露了 bowl 召回风险。不能把 4/4 目标候选误写成 4/4 全实例检出，更不能换算为 recovery 成功率。

`silver` 并非 task 0 或 task 1 的任务语言所提供，而是开发画面中物体的目视描述；把它写入固定提示词很可能依赖 LIBERO 的外观规律。新 init 1 序列是冻结后的初步检验，规模仍小；task 1 已看过输出，也不能当作最终独立测试集。后续要在更多任务与不同外观的 ramekin 上按全实例标注报告误检、漏检、冲突、目标错误绑定和拒绝率。颜色 `black` 仍未独立核验，放置区域、抓取几何和视觉验收均未完成；4 帧 ID 一致不代表可以执行 recovery。
