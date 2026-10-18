# Skill 定向扰动评测完成报告（2026-10-11）

北京时间 08:32:50 完成；08:33–08:34 实时复核。36 jobs × 5 集 = 180/180 个完整唯一样本；41 集成功（22.8%）。A 强制恢复与 B 自然触发的设置不同，合计成功率仅作队列完成描述，不作为统一基准性能。

## 完成与身份验收

`resume_v1/all.done`、`completed_index.json` 均存在；重新执行 `resume_targeted_boundary_pilot.py status` 与 completed_index 完全一致，每 job 的 episode 0–4、seed 1–5、init_state_idx 0–4 校验通过。冻结 runtime commit `7128c1ea6280c227e48561e621fe9da8604c5a6d`、C4 pack 全文件哈希和物理 entrypoint 哈希匹配。最终 session `20261010T202826Z_346c37` 四路退出码 `[0,0,0,0]`；无活跃 master/lane/eval/cuTAMP。平台仍为指定实例 RUNNING，不停止或删除。

## A：固定 query 0 的 profile 对照

有效样本 150/150，专用 29/75（38.7%），通用 0/75（0%）；两臂均各调用恢复 75 次。每行每臂 5 集。

| 对象 | 条件 | 专用成功 | 通用成功 | 仅专用成功 / 双失败 |
| --- | --- | ---: | ---: | --- |
| cream cheese | original | 4/5 | 0/5 | 4 / 1 |
| cream cheese | thin075 | 1/5 | 0/5 | 1 / 4 |
| cream cheese | thick125 | 5/5 | 0/5 | 5 / 0 |
| cream cheese | gap015 | 0/5 | 0/5 | 0 / 5 |
| cream cheese | gap050 | 0/5 | 0/5 | 0 / 5 |
| butter | original | 3/5 | 0/5 | 3 / 2 |
| butter | thin075 | 0/5 | 0/5 | 0 / 5 |
| butter | thick125 | 4/5 | 0/5 | 4 / 1 |
| butter | gap015 | 0/5 | 0/5 | 0 / 5 |
| butter | gap050 | 0/5 | 0/5 | 0 / 5 |
| chocolate pudding | original | 4/5 | 0/5 | 4 / 1 |
| chocolate pudding | thin075 | 4/5 | 0/5 | 4 / 1 |
| chocolate pudding | thick125 | 4/5 | 0/5 | 4 / 1 |
| chocolate pudding | gap015 | 0/5 | 0/5 | 0 / 5 |
| chocolate pudding | gap050 | 0/5 | 0/5 | 0 / 5 |

75 组同 episode/seed/初始化的配对：仅专用成功 29，仅通用成功 0，双成功 0，双失败 46。原布局专用 11/15，薄 0.75 专用 5/15，厚 1.25 专用 13/15；两档侧间隙、两种 profile 合计均 0/60。

这只是每单元 5 集的试跑观察。配对按初始化身份建立；本报告尚未逐对比较接管前完整 controller/policy 状态哈希，因此不把它升级为完全同状态的因果证明。场景静置、无提前成功和穿模验证通过，不等于所有间隙布局可解。

## B：自然触发（没有强制同状态恢复臂）

有效样本 30/30，成功 12/30（40%），实际恢复调用 14 次。

| 对象 | milk 径向偏移 | 成功 | 恢复调用次数 |
| --- | --- | ---: | ---: |
| cream cheese | -0.04 m | 1/5 | 1 |
| cream cheese | +0.00 m | 4/5 | 4 |
| cream cheese | +0.04 m | 0/5 | 0 |
| tomato sauce | -0.04 m | 0/5 | 0 |
| tomato sauce | +0.00 m | 4/5 | 5 |
| tomato sauce | +0.04 m | 3/5 | 4 |

按同初始化对照原布局，偏移 −40 mm：cream cheese 仅原布局成功 3、双成功 1、双失败 1；tomato sauce 仅原布局成功 4、双失败 1。偏移 +40 mm：cream cheese 仅原布局成功 4、双失败 1；tomato sauce 双成功 2、仅原布局成功 2、仅偏移成功 1。

初始 ±40 mm 不等于 query 时跨越 0.20–0.24 m 路由边界。零恢复调用且最终失败，不能直接标为目标规则漏检：还须独立物理 wrong-intent 标签、所有 trigger 的补偿情况和 query 距离轨迹。B 的同状态强制恢复对照未在冻结队列中实现，本轮未补建。

## 基础设施与阶段归因

正式 180 集中未发现 runner_failed、文件缺失、ModuleNotFoundError、Traceback 类基础设施错误；实验树无 `.failed` / `.infrastructure_invalid` 标记。最终 session 正常退出。历史多次抢占中断尝试仍全部保留，残缺样本不计入机器人失败分母。第一版 canary 的 2 集 ROOT 路径异常另行排除；修正 canary 的 2 集也不计入正式 180 集。

恢复 trace 中出现 motion planning 无可行粒子、tracking stalled/budget exhausted、闭爪但未持物、lift probe 未确认等执行诊断；`goal_atoms_not_yet_satisfied` 和 `env_done_during_trajectory` 也可能出现在最终成功样本中。这些是多阶段记录，不能把记录条数当作失败 episode 数。本报告给出最终任务成功和配对结果，完整抓取/抬升/保持/放置阶段归因尚不足，需结合视频与轨迹后续审阅。

## 证据与收尾

远端根目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/skill_boundary_pilot_20261010`。规范样本路径由 `resume_v1/completed_index.json` 定义；所有旧日志保留。

本地：`tmp/inspire/boundary_final_evidence.json` 保存原始远端返回（含终端控制字符，读取时取首个 `{` 至最后 `}`）；`tmp/inspire/boundary_final_summary.json` 保存清洁汇总；`heartbeat_preflight.txt` 和 `status_boundary_resume.txt` 保存最终检查。

本轮只执行冻结评测，没有训练、mining 或修改实验条件。完成后暂停 heartbeat `skill`，保留 `TaskAgent_check_inspire` 和 `xinghanbo-eval`。
