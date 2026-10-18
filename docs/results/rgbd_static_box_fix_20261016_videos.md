# 执行视频与仿真成功判定说明

本页补充本轮实际回放的视频，不重新运行仿真。源数据为已校验的 `rgbd_static_box_fix_20261016/recovery_evidence.zip` 内双相机 RGB-D 快照。

- [Plate 成功回放，双相机 MP4](assets/rgbd_static_box_fix_20261016/plate_recovery.mp4)，7.95 秒。
- [Bowl 跟踪中断回放，双相机 MP4](assets/rgbd_static_box_fix_20261016/bowl_recovery.mp4)，5 秒。
- [Plate 单相机动图](assets/rgbd_static_box_fix_20261016/plate_recovery.gif)。

原记录每 5 个环境步采样一次，约每 0.25 秒一帧。MP4 按原步号间隔保持每幅观测，最后一帧停留 1 秒；编码为 20 fps 不表示具有 20 fps 的独立观测。这是当次实际执行的采样帧合成，包含外部相机与腕部相机，不是重新仿真或生成的动作。帧数、原步号和视频哈希见 `rgbd_static_box_fix_20261016_video_manifest.json`。

“仿真判定成功”指回放结束后调用环境的 `check_success()`，根据任务定义和仿真内部状态返回成功。Plate 的实际 BDDL 语言是 `Put the wine bottle on the plate`，目标为 `(On wine_bottle_1 plate_1)`。保留的 BDDL 文件名含 bowl，但文件内容已是该 bottle→plate 受控任务。

Plate 最终该检查返回 true；Bowl 返回 false。这与恢复器的 `recovery_success`、规划器的 `feasible` 分别记录。Plate 末帧环境步为 174，夹爪两指关节为 `[0.0389443, -0.0389603]` m，达到现有 Panda 张开阈值。BDDL 目标没有额外要求张开夹爪或持续稳定一段时间，因此任务成功信号本身不能证明所有这些额外条件。

原实验报告及证据包保持不变，本页和视频是后续补充产物。视频已经过解码与末帧目视核验。
