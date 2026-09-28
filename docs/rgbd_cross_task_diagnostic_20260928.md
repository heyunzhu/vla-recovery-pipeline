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

## 四组快照的统一离线准入基线

`scripts/recovery/skill_pipeline/evaluate_rgbd_admission.py` 从保存的 RGB-D、任务语言和冻结 mask 重新构造视觉场景与 ID 绑定。它核对提示词确实由任务语言生成，并检查 mask 冲突；报告只表示 reset 帧的 ID 准入情况，不表示抓取、放置或任务成功。将原先的 spatial task 0 与上述三组新任务一同重放，结果为 **4 组中 3 组拒绝、1 组仅有待属性核验的 ID 候选**。原因依次是 `candidate_requires_attribute_check`、`target_ambiguous`、`target_not_observed`、`overlapping_instance_masks`。机器可读结果保存在 `D:\大三上\科研\rgbd_admission_report_20260928.json`，位于 Git 之外。

共享场景 provider 现在也提供 `get_admission(frame)`：同一帧只运行一次检测，正常时返回场景，冲突时返回 `overlapping_instance_masks` 和冲突像素证据。拒绝不会推进实例跟踪；原有 `get_scene(frame)` 在冲突时仍抛错，兼容已有调用方。离线准入脚本使用的是这个接口，因此其拒绝语义可直接供后续在线入口使用。当前 runner、cuTAMP 和 executor 尚未调用该接口。

这组结果可作为后续更换提示词、检测器或准入规则时的回归基线；四个 reset 帧规模太小，不能据此估计跨任务准确率或在线 recovery 成功率。比较新方法时应冻结任务、画面与准入定义，并另采未参与调参的画面验证。

新增 provider 拒绝缓存测试后，完整本地 skill-pipeline 测试为 **554 项通过**（`TEMP`/`TMP` 指向 D 盘长路径）。

## 结论和下一步

此前 `libero_spatial` task 0 单帧的 4/4 参考点结果没有跨任务保持。当前规则在这三张新画面上均未形成可用于后续规划的目标绑定；这只是小样本离线准入结果，不能换算为 recovery 成功率。

下一步先冻结一套由语言到视觉物体描述的通用词表或候选生成规则，在未参与调词的任务上检验目标/参照物的检出与误检；同时保留跨类别重叠时的明确拒绝，不用未经校准的原始分数随意挑一个标签。之后再测试多帧 ID 稳定、颜色等属性核验和放置区域。只有这些检查可靠后，才接入在线 runner、planner 和 executor。

为使失败可复现，离线 runner 现在会把重叠 mask 的类别、索引、像素数和重叠比例写入 `scene_refusal.json` 后退出；点位评估即使匹配到正确类别，也会在存在冲突 mask 时判为失败。完整本地测试为 **553 项通过**（Windows `TEMP`/`TMP` 指向 D 盘长路径）。
