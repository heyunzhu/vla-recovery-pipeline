# 逐帧 RGB-D：其他八个 task 后台并行回放

2026-10-16。分支 `feature/rgbd-recovery`；基线 HEAD `62e4bc8410bcf1211c8b86dc8263746f2c8a6795`，新增启动器尚未提交。

## 已提交运行

授权实例：启智平台「可上网GPU资源」的 `xinghanbo-eval`。启动前 GPU 空闲，可用显存 48,495 MiB。采用 4 个并发案例，初始视觉感知和仿真并行，规划求解通过同一 `shared_planner.lock` 串行。每案例超时 1,800 秒，线程数通过子进程环境限制，不修改全局环境。

服务器根目录（下文 ROOT）：

```text
/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
```

本次输出：`ROOT/logs/rgbd_framewise_expansion_20261016`。后台主进程启动 PID：284554，时间戳 1792140368.965508。启动核验时前四项状态均为 `running`，后四项自动排队；未等待最终结果。

| 标签 | 任务 | 原检查点 |
|---|---|---|
| 03_goal_cheese_rack | 奶油奶酪放到架子上 | goal_task 8 / ep0 |
| 04_swap_bowl_plate | 碗放到盘子上 | goal_swap 4 / ep0 |
| 05_swap_cheese_bowl | 奶油奶酪放到碗上 | goal_swap 7 / ep0 |
| 06_object_cheese_basket | 奶油奶酪放进篮子 | object_task 1 / ep0 |
| 07_object_juice_basket | 橙汁放进篮子 | object_task 3 / ep0 |
| 08_object_milk_basket | 牛奶放进篮子 | object_task 6 / ep0 |
| 09_spatial_bowl_next_plate | 盘子旁的黑碗放到盘子上 | spatial_task 2 / ep4 |
| 10_spatial_bowl_cabinet | 柜子上的黑碗放到盘子上 | spatial_task 3 / ep0 |

任务语言及 BDDL 路径严格复用上一轮 `rgbd_ten_tasks_20261015/batch_manifest.json`。LIBERO-PRO 的语言/物体替换使 BDDL 文件名可能与实际任务语言不相同，不以文件名重新推断任务。

## 方法和已知边界

复用上一轮十任务收集的 recovery 检查点，不重跑策略。感知/执行源码复制自成功的 `rgbd_framewise_20261016_replay03/code`，只新增并行批处理启动器，保留逐步 DINO+SAM、SE(3) 跟踪、有标签障碍物、实测碰撞单元尺寸和视觉验收配置。

初始几何模块仍要求目标是瓶子，支撑面是盘子或碗。因此本批用于测量当前实现的跨任务卡点，可能在语言、绑定或初始形状环节结束，不能事先声称八个任务均支持完整执行。失败时不切换真值几何，不把“不支持形状”归为检测失败。自动失败分类是启发式标签，最终分析以原始日志和图像为准。

初始检查点来源包含原历史真值运行，但新回放隐藏 reward/done 于恢复器，仿真成功仅用于独立最终评估。该样本来自历史成功案例，不是随机 benchmark 成功率。

## 复现与后续读取

启动器：`scripts/recovery/skill_pipeline/run_parallel_framewise_expansion.py`，服务器冻结副本 SHA256：`af9029bb7bb67e22a38195c0f389e60bf3533ee7bf6dc2c7bf673b3b26961134`。

在已完成源码复制的本次目录中，原始启动参数为（该命令已经启动，不应在同一输出目录重复执行）：

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
"$ROOT/envs/rlinf-openpi/bin/python" \
  "$ROOT/logs/rgbd_framewise_expansion_20261016/code/scripts/recovery/skill_pipeline/run_parallel_framewise_expansion.py" \
  --root "$ROOT" \
  --batch "$ROOT/logs/rgbd_framewise_expansion_20261016" \
  --workers 4 --timeout 1800
```

实际启动采用独立 session、关闭输入、输出写文件，断开本地连接后继续运行。完整原始参数在 `launch.json`。

- `batch_driver.log`：后台主进程日志。
- `batch_manifest.json`：八项任务和并发设置。
- `source_sha256.json`：服务器源码快照哈希。
- `batch_results.json`、`summary.csv`：每完成一项自动更新。
- `batch_finished.json`：全部任务结束后生成。
- 每任务目录：`command.json`、`input_manifest.json`、`driver.log`、`status.json`、`finished.json`，以及已有传感器帧、提名日志、规划/跟踪记录。
- 每任务结束自动从可用 RGB 帧导出 `final_rgb.png` 和 `recovery.mp4`。失败前没有传感器帧则明确记录 `no_sensor_frames`。视频按仿真 20Hz 播放，稀疏区间保持上一帧，省略推理等待。

启动前核验原冻结 runtime commit `7128c1ea6280c227e48561e621fe9da8604c5a6d` 和 backend SHA256 `2ee311fc60f0e0209c42efe4cc051acf4a16e78eed92a3e3a001a313581e87a4` 均符合记录。规划继续使用已验证的 `rgbd_static_box_fix_20261016/runtime_overlay`；没有覆盖原运行包、模型、任务或历史证据。

## 完成结果（服务器实测回收）

本批已全部结束，启动至完成约 94 秒，8/8 失败，0/8 进入逐帧目标跟踪。各任务在 11–53 秒内退出；没有超时或显存不足记录。不能把这批解释为八次完整抓取/放置执行失败。

| 失败环节 | 数量 | 任务 | 已核对的实际证据 |
|---|---:|---|---|
| 初始目标几何写死瓶子 | 6 | 03、04、06、07、08、09 | 各视觉提名日志均报 `bottle fitting requires a visually nominated bottle`。已有视觉目标候选，但其类别不是 bottle，进入拟合即拒绝；不代表这些候选都经过人工核验 |
| 目标候选缺失 | 1 | 05 奶油奶酪→碗 | `binding.json` 为 `refused / target_not_observed`，目标候选为空，碗候选为 `obj_001`；随后代码未处理拒绝状态，查找空 target_id 报 `StopIteration` |
| 语言解析不支持 | 1 | 10 柜子上的黑碗→盘子 | `unsupported object phrase: 'akita black bowl on the top of the wooden cabinet'`，在生成检测提示前拒绝 |

原始自动汇总把 05 标为 `nomination_or_setup`，人工检查 binding 后在本文细化为“目标候选缺失”；原始结果保持不改。不能仅凭此断定是 DINO 漏检、遮挡还是后处理筛掉了目标。

所有案例导出了末帧和视频，但 5 个案例只有一个不同环境步的图像，另外 3 个为 3–4 帧入场动作；这些文件不是完整 recovery 动作视频。

汇总和各任务异常日志已拉回本地 `analysis_outputs/rgbd_parallel_20261016/remote/`。主问题是当前实现仍有瓶子专用入口和有限语言解析，尚未真正评测到新跟踪器在其他形状上的能力。下一步应先支持通用目标几何、显式处理绑定拒绝，再对相同检查点重跑。
