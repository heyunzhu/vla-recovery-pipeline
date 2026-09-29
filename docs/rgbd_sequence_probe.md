# RGB-D 连续帧探针

这一步验证真实连续帧上的视觉场景与实例 ID，不运行 VLA、recovery 或 cuTAMP，也不读取 MuJoCo 物体真值作为感知输入。它与四组 reset 帧准入报告互补：后者检查跨任务错误类型，本探针检查相邻帧是否持续可观察、发生拒绝后能否恢复跟踪。

## 采集与处理

1. 在已安装 LIBERO / robosuite 1.4.1 的环境中运行 `scripts/recovery/skill_pipeline/collect_rgbd_sequence.py`。首个 canary 固定为 `libero_spatial` task 0、init 0、seed 7、512 像素、`agentview` 与腕部相机、3 个小幅 wrist-lift 步。输出放在服务器个人目录 `/mnt/sdb/24_yyx/demo/` 的新目录，不覆盖现有快照。
2. 将整个序列复制到本地 `D:\大三上\科研`。每个 `stepNNN/<camera>/` 都有独立的 RGB-D、标定和本体状态；`summary.json` 记录顺序、时间和采集设置。
3. 在本地对每个 `stepNNN/agentview` 调用冻结的 `run_grounded_sam2_snapshot.py`，均使用序列根目录的 `summary.json` 作为 `--language-summary`。模型权重、阈值和任务语言保持相同；即使某帧因 mask 冲突拒绝，检测 artifact 仍保留。
4. 用 `scripts/recovery/skill_pipeline/evaluate_rgbd_sequence.py` 重放每帧检测，经同一个 `RGBDSceneProvider` 跟踪，保存逐帧场景状态、拒绝原因、目标候选 ID 和跨候选帧的 ID 一致性。

采集命令示例（从远端仓库根目录运行，输出目录须预先确认不存在）：

```bash
python scripts/recovery/skill_pipeline/collect_rgbd_sequence.py \
  --task-suite-name libero_spatial --task-id 0 --init-index 0 --seed 7 \
  --resolution 512 --cameras agentview robot0_eye_in_hand \
  --steps 3 --motion wrist_lift \
  --out-dir /mnt/sdb/24_yyx/demo/rgbd-spatial-task0-sequence-512-20260928
```

`same_target_id_across_candidate_frames` 只有至少两帧产生目标候选时才有布尔值；`null` 表示证据不足。即使它是 `true`，也只说明现有检测器和跟踪器在这些帧上给出了相同 ID，不能证明颜色属性正确、抓取成功或任务完成。真正的感知稳定性还需不同初始状态、遮挡和物体移动的序列。

## 当前状态

2026-09-28 已通过 VPN 和 SSH 在个人目录实际采集，服务器路径为 `/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-sequence-512-20260928`，本地副本为 `D:\大三上\科研\rgbd-spatial-task0-sequence-512-20260928`。远端运行的是个人快照仓库中新增的 `collect_rgbd_sequence.py`；上传前确认目标脚本不存在，上传后 SHA-256 与本地一致。4 个时间点（0、0.05、0.10、0.15 秒）各有 `agentview` 和腕部相机，共 8 帧 512×512 RGB-D；八帧深度有效比例均为 1.0。固定相机位姿未变，腕部相机从首帧到末帧位移约 5.9 mm，画面像素也发生变化。这是小幅 wrist-lift 传感器探针，`policy_rollout_steps=0`。

固定相机的四帧使用同一组任务语言提示词、固定模型权重与 0.25/0.25 阈值离线检测。前 3 帧各有 6 个 mask，同一可见物体被同时标为 `bowl` 和 `ramekin`，较小 mask 的重叠比例均为 1.0，场景全部拒绝。末帧有 5 个 mask、无重叠冲突，但出现两个 `plate` 候选。复核四帧叠图与人工负样本点后，发现每帧都有一个相同位置的 `plate` 误检，落在左侧柜体上。改进后的语言绑定器同时检查目标、参照物与目标区域的 `between` 几何关系，唯一选出 `obj_002` bowl 和 `obj_003` plate；结果仍是 `candidate_requires_attribute_check`，颜色 `black` 尚未独立核验。机器可读结果为本地序列根目录下的 `agentview_sequence_eval.json`。

腕部相机的首帧与末帧也运行了相同冻结模型，两帧均因 `bowl`/`ramekin` 或 `plate`/`ramekin` mask 完全重叠而拒绝。这两帧没有提供可接入的替代视觉场景；中间两帧的腕部检测尚未运行。固定相机只有末帧产生目标候选，所以 `same_target_id_across_candidate_frames=null`，**不能报告真实多帧 ID 稳定性或切换率**。本轮明确暴露的是持续的跨类别分割冲突；不能据此报告 RGB-D recovery 成功率。

新增联合空间关系绑定测试后，本地完整 skill-pipeline 测试 **556 项通过**（`TEMP`/`TMP` 指向 D 盘长路径）。

2026-09-29 补充了固定冠词提示词对照及只读冲突假设回放。冠词变体虽无 mask 冲突，却漏掉了前三帧全部 bowl；任务关系筛选后的诊断假设能保持四帧目标 ID 一致，但原始准入仍有三帧拒绝，不能把该假设用于执行。详见[重叠 mask 诊断](rgbd_conflict_diagnostic_20260929.md)。
