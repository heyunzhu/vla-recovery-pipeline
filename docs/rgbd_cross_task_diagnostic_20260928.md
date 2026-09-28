# RGB-D 跨任务离线诊断：首批新快照

记录日期：2026-09-28。此实验只采集 LIBERO reset 帧并在本地离线运行冻结模型；没有 VLA、cuTAMP 或 recovery episode。

## 输入与方法

- 在 5880 服务器个人目录 `/mnt/sdb/24_yyx/demo` 中，用现有 Python 3.8 / robosuite 1.4.1 环境采集 3 个 `agentview` 512×512 RGB-D 快照；采集脚本与本地版本 SHA-256 一致。每帧 262,144 个深度像素全部有效。
- 快照复制到本机 `D:\大三上\科研` 下同名目录；原始数据、mask 和模型权重均不提交 Git。
- 固定使用 [感知基线](rgbd_perception_baseline.md)中的 Grounding DINO tiny、SAM 2.1 tiny、模型版本与 0.25/0.25 阈值。检测提示只由任务语言生成，不按新图像手选。
- 检查原始检测框、mask 叠图、视觉场景准入与任务 ID 绑定。以下是诊断性失败分类，没有完整人工 mask 标注或在线成功率。

| 快照与任务语言 | 模型输出及可见问题 | 场景/绑定结果 |
| --- | --- | --- |
| `libero_object` task 0：`pick up the alphabet soup and place it in the basket` | 1 个 basket mask，4 个标为 soup 的 mask；图上多个不同物品都被该提示匹配。 | 视觉场景可生成，但目标类别有 4 个候选；绑定拒绝 `target_ambiguous`。 |
| `libero_object` task 1：`pick up the cream cheese and place it in the basket` | 只得到 1 个 basket mask；没有 cream cheese mask。 | 绑定拒绝 `target_not_observed`。 |
| `libero_spatial` task 1：`pick up the black bowl next to the ramekin and place it on the plate` | 得到 5 个 mask；前景同一碗同时被标成 bowl 和 ramekin。两 mask 重叠 5,022 像素，占较小 mask 的 100%。 | 场景构造拒绝 `overlapping_instance_masks`，未生成可用场景或任务绑定。 |

每个快照的本地路径分别是：

- `D:\大三上\科研\rgbd-object-task0-init0-512-20260928`
- `D:\大三上\科研\rgbd-object-task1-init0-512-20260928`
- `D:\大三上\科研\rgbd-spatial-task1-init0-512-20260928`

对应服务器目录为 `/mnt/sdb/24_yyx/demo/rgbd-object-task0-init0-512-20260928`、`rgbd-object-task1-init0-512-20260928` 和 `rgbd-spatial-task1-init0-512-20260928`。每个本地目录有 `summary.json`、`agentview/rgbd.npz`、`agentview/preview.png` 与 `agentview/grounded_sam2_language_v1/` 下的模型产物。前两项还存有 `visual_task_binding.json`；第三项存有 `scene_refusal.json`。

## 结论和下一步

此前 `libero_spatial` task 0 单帧的 4/4 参考点结果没有跨任务保持。当前规则在这三张新画面上均未形成可用于后续规划的目标绑定；这只是小样本离线准入结果，不能换算为 recovery 成功率。

下一步先冻结一套由语言到视觉物体描述的通用词表或候选生成规则，在未参与调词的任务上检验目标/参照物的检出与误检；同时保留跨类别重叠时的明确拒绝，不用未经校准的原始分数随意挑一个标签。之后再测试多帧 ID 稳定、颜色等属性核验和放置区域。只有这些检查可靠后，才接入在线 runner、planner 和 executor。

为使失败可复现，离线 runner 现在会把重叠 mask 的类别、索引、像素数和重叠比例写入 `scene_refusal.json` 后退出；点位评估即使匹配到正确类别，也会在存在冲突 mask 时判为失败。完整本地测试为 **553 项通过**（Windows `TEMP`/`TMP` 指向 D 盘长路径）。
