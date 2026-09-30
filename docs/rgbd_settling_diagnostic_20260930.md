# RGB-D 采集静置修正与复测（2026-09-30）

## 发现与修正

在为 plate 提取可见支撑面时，发现此前 init 1 连续帧的 plate mask 世界 Z 中位数在 0.15 秒内由 0.976822 m 下降至 0.906843 m，变化约 69.979 mm。固定相机位姿未变，主要水平面候选高度约 0.9005 m；结合原始 RGB，证据支持物体在 reset 后尚未静置。此前采集脚本在 `set_init_state` 后立即记录，正式 `runner.py` 则默认先执行 10 次 dummy action。

修正 `collect_rgbd_snapshot.py` 和 `collect_rgbd_sequence.py`：新增 `--settle-steps`，默认 10，范围 0–100；先执行空动作，再记录 RGB-D。序列目录 `step000` 是采集相对索引，帧内 `env_step` 保留实际环境步数。`summary.json` 新增 `settle_env_steps`、`capture_start_env_step`，逐帧记录 `probe_step` 和真实步号。普通序列回放和冲突假设回放均读取起始偏移；旧数据缺省偏移为 0。新增回归测试验证 10/11 实际步号及错误偏移拒绝。

**更正此前实验解释：9 月 28 日 init 0 与 9 月 29 日 init 1 的连续帧、此前直接 reset 快照，都属于未静置初始化观测。** 逐图误检、漏检和 mask 冲突记录仍成立，但不能视为在线等待完成后的感知表现，也不能将序列变化全部归因于 wrist-lift。它们保留为初始化瞬态诊断样本。

## 新采集与受控复测

服务器个人目录：`/mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init1-settled10-sequence-512-20260930`；本地同名目录在 `D:\大三上\科研`。task 0、init 1、seed 11，512×512，双相机。10 次空动作后再记录 3 次空动作，实际步号 10–13、时间 0.50–0.65 秒，共 8 帧，深度有效比例均为 1.0。无 VLA 或 recovery rollout。远端使用个人快照仓库中新文件 `collect_rgbd_sequence_settled_20260930.py`，上传后 SHA-256 与本地一致：`0f9f6c15b50c38f0234d6a8fb9559da9fc8ab392ed697e26119f3a338e922b2a`。

```bash
python scripts/recovery/skill_pipeline/collect_rgbd_sequence.py \
  --task-suite-name libero_spatial --task-id 0 --init-index 1 --seed 11 \
  --resolution 512 --cameras agentview robot0_eye_in_hand \
  --settle-steps 10 --steps 3 --motion no_op \
  --out-dir /mnt/sdb/24_yyx/demo/rgbd-spatial-task0-init1-settled10-sequence-512-20260930
```

检测前查看四帧原始 agentview RGB，为各帧标注两个 bowl、plate、ramekin 的实例内点，以及柜体上的一个禁止 plate 点，绑定各帧 RGB SHA-256。这些点只用于离线评估。模型、权重、阈值及两组提示词均沿用此前配置。

| 4 帧 agentview 检查 | 原始任务语言 | 冻结 silver ramekin |
| --- | --- | --- |
| 实例内点命中 | 每帧 4/4 | 每帧 4/4 |
| 柜体负样本点误检为 plate | 4/4 帧 | 0/4 帧 |
| mask 冲突 / 场景拒绝 | 0/4 帧 | 0/4 帧 |
| 待属性核验的目标候选 | 4/4 帧、ID 一致 | 4/4 帧、ID 一致 |

原始配置四帧的点位评估均失败，但场景准入均接受：当前准入规则检查 mask 冲突，不能自动识别独立的语义误检。人工负样本评估与在线准入是不同检查，参考点不会进入在线决策。检测 CLI 的退出码 1 表示评估未通过，检测 artifact 仍正常保存。

`silver ramekin` 下 plate mask 的世界 Z 中位数约 0.909342 m，四帧极差 0.000000363 m（约 0.000363 mm）。这是可见深度与 mask 的重复性诊断，不能解释为真实硬件测量精度或整个物体位姿误差。水平面候选由显式范围 x/y ∈ [-1,1] m、z ∈ [0.85,1.0] m 内 RGB-D 拟合，原点高度约 0.900621 m、RMS 约 1.248 mm；该候选可能混入其他低矮表面，不能自动认作可放置桌面。详细数值见 [深度诊断 JSON](rgbd_settling_depth_20260930.json)。

未静置旧序列用了 wrist-lift，新序列用了 no-op，因此不能把二者量化差异当作仅改变静置步数的严格因果对照。新序列验证了与 runner 等待步骤一致的采集方式及该场景的短时稳定性。四帧近乎静止、只有 0.15 秒，也不能据此报告物体移动或遮挡下的 ID 稳定性。

## 交付、证据与下一步

本地数据根目录保存 `agentview_baseline_sequence_eval.json`、`agentview_silver_ramekin_sequence_eval.json`、`settling_depth_diagnostic.json`；逐帧 `grounded_sam2_*_v1` 保存配置、mask、点位评估与 RGB 哈希。原始 RGB-D 和模型输出未提交 Git。`silver` 是开发时目视选定的外观提示，不能当作跨外观泛化已成立。

完整 skill-pipeline 单元测试 562 项通过（TEMP/TMP 指向 D 盘长路径）。下一步从静置后、语言绑定明确的 plate mask 提取可见支撑面候选，报告高度、拟合误差和可见边界；之后才核验容纳范围、碰撞/净空和抓取几何。当前视觉 handoff 的 `planning_allowed=false`，尚未打通 RGB-D recovery 在线执行，不能报告 recovery 成功率。
