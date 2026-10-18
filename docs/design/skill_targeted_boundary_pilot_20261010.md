# Skill 假设边界试跑：薄盒抓取与 wrong-intent 窗口

状态：2026-10-11 北京时间 08:32:50 完成冻结队列 180/180 个唯一样本，四路正常退出；最终身份、pack 与 entrypoint 哈希匹配。结果见 [完成报告](skill_targeted_boundary_pilot_20261010_results.md)。本轮 heartbeat 已暂停，保留实例和原 Windows 通知任务。

## 依据与边界

历史 object 单轴实验记录位于 Git commit `28eb6aee34f1d5f41ff15540ed4b33e2d7c18203` 的 `docs/libero_pro_object_batch_20261004_eval.md`：goal 换被操作对象、placement 沿 x 平移 −0.10 m、geometry 仅 yaw 旋转 90°。Pack 1317/1500；薄盒类有明显局部弱项。该记录属于开发证据。

本轮冻结 Core-60 的 C4 pack 和运行代码，不修改 skill，不进行 mining；每个扰动资产写入独立实验目录。新脚本、源 commit、pack 文件哈希、任务/初始化/种子与扰动后的状态哈希均保存。当前本地分支 `feature/rgbd-recovery` 不用作历史 oracle/cuTAMP 评测实现，避免混入 RGB-D 迁移变化。

这轮只测试路由与执行边界，不称为持续学习遗忘。正式部署前核验服务器的历史运行入口与依赖。

## A：薄盒抓取边界

对象：cream cheese、chocolate pudding、butter；逐一核对真实源 BDDL 与初始化，不能沿用文档中不同排序下的 task ID。

### A1 厚度轴

相对原碰撞几何厚度设置 0.75、1.00、1.25 倍，其他尺寸不变。运行前必须完成：

- 同步视觉和碰撞几何，重新编译模型；不能只改 planner 输入或碰撞半尺寸。
- 检查 planner 读到的厚度与实际模型一致。
- 调整支撑高度，排除初始穿模；记录质量/惯性处理方式，不混入未报告的物理参数变化。
- 保持源任务语义、goal 和对象身份不变。

若不能安全满足这些条件，先停留在几何验证，不计入有效 episode；不得以“厚度实验”名义运行只有 proxy 改动的实验。

### A2 抓取侧空间轴

不改目标模型，用现有非目标物体在目标抓取侧构造不同可用间隙。原布局、宽间隙、紧间隙三个档位；档位由夹指模型和对象边界计算，记录实际间隙，避免只报告物体中心距离。保留另一侧或其他方向的可能抓法。

目标与干扰物初始非穿模；settle 后重测间隙。无法证明可完成的状态单独记为“可行性未验证”，不能归为 skill 泛化失败。

### 比较

当前 `cream_cheese_flat_box_topdown_deep_v1` 与通用抓取配置，仅替换 grasp 配置，其他恢复参数不变。在扰动后的同一状态、同一接管 query 启动恢复，核验接管前完整状态哈希。不能把自然入口不同的两个结果当作 profile 因果比较。

先每单元 5 个配对初始化，确认流程与效应后扩大到 20；5 集只用于试跑，不用于稳定成功率结论。厚度轴与间隙轴分别运行，不先做交叉乘积。

记录：候选数量、IK/碰撞可行候选数、执行阶段是否到达、正确对象闭合、抬起、持物保持、最终任务结果、失败码、视频。仅得到 episode success 时标为阶段归因不足。

## B：wrong-intent 距离窗口

目标：cream cheese 与 tomato sauce；核心规则 `object_basket_cream_tomato_q5_wrong_intent_window` 的最近错误物体距离要求 0.20–0.24 m，同时受其他意图、历史、开度和持物条件约束。

移动实际干扰物，产生窗口下方、内部、上方及原布局四类状态。初始放置距离不是 query 时的距离；按轨迹实际观测分类，不能预先假定已越过规则边界。先每单元 5 集。

第一臂自然完整 C4 系统：记录全 trigger 诊断、winner、接管请求与实际 recovery 入口。必须保留其他 trigger，以检查补偿覆盖，不能仅凭目标规则不触发宣称系统漏检。

第二臂在核验过的同类 wrong-intent 状态，从保存的接管前状态强制恢复。仅对可复现的状态运行，不能随机选一个更早 query 作“恢复可以成功”的对照。

错误样本的分母必须有独立可复核的错误对象接近/操作行为证据。基线最终失败不是单个 query 的错误标签；规则距离条件本身也不能作为独立标签。

记录：正确目标/错误意图物体 ID、实际最近距离、margin、预测距离、历史长度、所有未满足谓词、首次满足时刻、winner、实际入口、物理错误发生时刻与阶段结果。分类为：无错误无需接管、目标规则漏但其他规则补偿、全系统未接管、接管较晚、恢复执行失败。

## 启动验收

1. 确认只使用用户指定的启智 `xinghanbo-eval`，核验没有其他评测/训练占用。
2. 原布局 canary 先跑通；完成扰动有效性与源资产不变哈希检查。
3. 两类扰动各完成一个有效 episode，再启动小批量。并行最多四路；cuTAMP 若采用原串行锁，沿用同一锁并报告实际执行并发。
4. 保存每个 job 的完整命令、运行实现身份、退出码与完成标记。无效场景和运行错误不算机器人任务失败。
5. 报告有效样本/计划样本、阶段失败分布和配对结果；不以“成功率下降”为预设目标。

## 本轮部署与运行口径

独立目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/skill_boundary_pilot_20261010`。

部署脚本：`targeted_boundary_entrypoint.py`（物理扰动 overlay）、`launch_targeted_boundary_pilot.py`（独立 supervisor）。源码保留在本仓库 `scripts/recovery/skill_pipeline/`；不改历史 runtime_repo 或 C4 pack。远端 manifest 保存冻结代码 commit、pack 哈希、overlay 哈希和全部 job。

初轮 A：object_task T01 cream cheese、T07 butter、T08 chocolate pudding；原布局、厚度 0.75/1.25 倍、侧向间隙 15/50 mm，分别配专用/通用 grasp。共 30 jobs×5 集=150 集。固定 query 0 强制恢复，最多一次恢复调用；用于抓取能力对照，不冒充自然路由成绩。

初轮 B：object_task T01 cream cheese、T09 tomato sauce；原布局，以及 milk 干扰物沿初始 EE→milk 的水平径向移动 ±40 mm，共 6 jobs×5 集=30 集。保留自然 trigger，最多两次恢复调用。按 query 中真实距离分类，±40 mm 不保证命中预期触发窗口。

合计计划 180 集，另有原布局/缩薄启动验证各一集。初始状态/每个 query 的仿真状态另存，供状态对齐与后续强制恢复对照；B 的强制恢复臂尚未启动。

三种薄盒各两种厚度已核验碰撞 AABB 缩放和质量不变。部署后还检查全部候选初始化的 settle、成功状态和移动干扰物穿模；未通过的不计有效实验，不能静默记为 skill 失败。

完整运行命令写入每个 job 的 `command.json`，配置为 `boundary_config.json`，初始化审计为 `init_audit.jsonl`，原始 runner 数据在 `run/`。监督进程只在 canary 完成后允许启动 lane，避免误把平台启动当成业务已跑通。

## 2026-10-10 启动记录

实时核验实例原为 `STOPPED`，仅启动 `xinghanbo-eval`；经 `PENDING`、`CREATING` 后进入 `RUNNING`。实际可见 GPU 显存 49,140 MiB。

100 个候选初始化（20 种配置×5 个初始化）通过加载、10 步静置、非提前成功和相关穿模检查。这只证明初始场景检查通过，不证明所有扰动任务可解。局部几何单元测试 5 项通过。

第一版 canary 的恢复进程因缺失 `ROOT` 环境变量而找错规划 Python 路径；两集均标为基础设施无效并保留日志，不能计入机器人失败率。补齐 `ROOT` 后在独立 `canary_v2/` 重跑：原布局一集成功，0.75 倍厚度一集未成功；两集均产生实际恢复调用。单集差异不是泛化结论，需结合规划/执行轨迹和后续配对样本判断。

两个修正后的 canary 完成后，启动门控放行四路小批量。已核验首四个 job 均完成策略加载并进入 episode 0（远端日志时间 13:11:26–27 UTC，即北京时间 21:11:26–27）：T01 原布局和 0.75 倍厚度，各自专用/通用 profile。GPU 显存使用约 36,469 MiB。四路为 episode worker 并行；cuTAMP 求解仍共用串行锁。计划 180 集尚未完成，B 的同状态强制恢复对照仍不在本轮队列内。

启动门控实现：`gate_targeted_boundary_pilot.py`；日志 `gate.log`，批量放行标记 `pilot.started`。每个 job 保存完整命令和运行身份，历史 runtime commit 为 `7128c1ea6280c227e48561e621fe9da8604c5a6d`；当前仓库分支不替代冻结 runtime 的身份。

## 2026-10-11 续跑记录

平台事件确认首次批量运行于北京时间 10 月 10 日 21:13:55 被抢占，首四个 job 尚未生成完整 `episode.json`；正式队列有效完成 0/180。此后实例多次重新调度，旧评测不会随实例自动重启。

按用户“重跑”要求，增加独立 `resume_targeted_boundary_pilot.py`，不替换物理扰动实现或旧 launcher。启动前核验冻结 runtime commit、pack 全部文件哈希与 manifest 中的 entrypoint 哈希均未变，确认无旧 worker。北京时间 10 月 11 日 00:30:04 启动新的 master PID 93487、四个 lane PID 93488–93491。所有旧日志原地保留，新尝试写入 `resume_v1/attempts/<job>/<session>_fromNN/`。

续跑入口检查已完成样本的 episode 编号、seed、init_state_idx、success 类型及恢复日志中的基础设施错误，保留完整机器人失败样本，只补缺失区间。使用冻结 runner 原有 `--episode_index_start`，不改变 `--episode_seed_start 1`、初始化顺序、扰动和 profile 条件。恢复日志中检测到基础设施错误时停止对应 lane，不作为有效机器人失败计数。5 项续跑单元测试通过，包括不连续缺失区间、身份错配、残缺 JSON 和基础设施错误。

再次需要续跑时，在确认无旧 worker 后运行以下完整命令（实例须为 RUNNING）：

```bash
/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/bin/python \
  /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/skill_boundary_pilot_20261010/resume_targeted_boundary_pilot.py start
```

此入口默认四路，使用内核锁避免同一时刻两个 resume master，cuTAMP 仍串行求解。入口可重复调用并跳过完整样本，但**没有安装实例启动后的自动执行钩子或平台监控自动化**；再次被抢占后仍需重新调用。每次 session 单独保存实现哈希、lane PID、日志和退出码；`resume_v1/completed_index.json` 与 `all.done` 仅在全部 180 个唯一样本完成后生成。

00:30:27 平台再次报告 `Pod is evicted, because of preempt`，上述 session 在启动约 23 秒后中断，实例进入 PENDING。该启动记录不代表实验持续运行。

## 2026-10-11 自动接管授权与配置

用户明确授权现有后台检测在实例启动时通知本对话，并在抢占后重启时操作续跑。这里的“训练”沿用本轮 180 集评测，不启动新的模型训练。仅允许操作指定 `xinghanbo-eval`，不改变资源、优先级、镜像或其他实例。

沿用 Windows 任务 `TaskAgent_check_inspire`，仍每 5 分钟执行 `E:/task-agent/scripts_lib/check_inspire.py`，保留原桌面/邮件通知及 30 分钟冷却。该脚本增加原子事件快照 `E:/task-agent/logs/inspire_codex_event.json`，只包含指定实例的状态、观察时间、恢复序号与本轮 run_key，不包含凭据；恢复事件独立于邮件冷却。原脚本备份 `check_inspire.pre_codex_20261011.py`。6 项事件写入测试通过；00:44:22 实际检测生成 PENDING 快照。

通过产品提供的 automation_update 创建本对话 heartbeat“启智 skill 扰动评测自动续跑”，ID `skill`，ACTIVE，每 5 分钟唤醒。这是按周期读取检测事件并实时复核，不是检测脚本直接即时推送到聊天。没有另建 Windows 检测任务，原有两项旧 mining 自动化仍 PAUSED、未修改。

每轮先读事件与检测日志，再查启智实时状态；PENDING/CREATING 等待，查询失败不得当作 STOPPED。STOPPED 且本轮未完成时可启动指定实例。RUNNING 时核验完整样本和所有相关进程：任一 master/lane/eval/cuTAMP 活跃则不再启动；无活跃进程、资产身份一致且无新的非抢占基础设施错误时，调用既有 `start_boundary_resume.py` 恢复四路。新失败、身份错配或异常退出须查证并报告，不无限重试。保持旧日志，按唯一样本去重，不将基础设施失败记作机器人失败。

无变化、待分配或正常推进时保持安静；仅续跑成功、全部完成或需处理的异常通知。180 个唯一样本完成后汇总结果并暂停本轮 heartbeat，保留用户的 Windows 通知任务，不停止或删除实例。本机需保持开机、Codex 应用运行，以便本地定时任务执行。

### 首次 heartbeat 自动恢复

北京时间 2026-10-11 00:57:51 轮次实时查到 RUNNING，节点 `qb-prod-4090-gpu057`；检测任务上一快照仍为 PENDING，故以实时查询为准。远端核验无活跃旧 master/lane/eval/cuTAMP、无新失败标记或 session 非零退出，正式完整样本仍 0/180。冻结代码、pack 和物理 entrypoint 哈希核验通过后，00:58:44 自动启动 session `20261010T165844Z_2fe921`，master PID 5359，四个 lane PID 5360–5363，四个 eval PID 5364–5367。所有中断日志保留。

01:01:13 的复核确认上述 9 个进程仍活跃；四路 driver 均在 00:59:09 记录 `policy setup start`。尚未出现 `policy setup done` 或完整 episode，不把此记录称作已完成 rollout。暂不重复启动，下一 heartbeat 继续核验加载是否推进。记录文件：本地 `tmp/inspire/heartbeat_preflight.txt`、`start_boundary_resume.txt`、`status_boundary_resume.txt`；远端 session/attempt 各自保留完整命令和日志。

随后 heartbeat 复核发现四路已在北京时间 01:02:05 进入 episode 0（seed 1、init_state_idx 0），各有首个 query 轨迹；实际 cuTAMP 规划进程活跃、其余请求沿用同一串行锁，显存约 38,060/49,140 MiB。完整样本仍 0/180，无新基础设施失败标记。保持现有四路，不重复启动、不杀进程。

### 第二次 heartbeat 自动恢复

北京时间 01:32:43 平台确认因 preempt 驱逐实例，随后 PENDING；没有执行 stop/start。01:37 轮次实时核验已在 `qb-prod-4090-gpu183` 恢复 RUNNING。远端无活跃 master/lane/eval/cuTAMP，无新失败标记或非零退出；续跑校验确认 9/180 个完整唯一样本（四个首批 job 分别完成 3、2、2、2 集），中断样本不计入失败。

冻结 runtime commit、pack 与物理 entrypoint 哈希匹配后，于 01:38:31 启动 session `20261010T173831Z_b58ac2`，master PID 15732，四个 lane PID 15733–15736，eval PID 15737–15740。各 lane 分别补 episode [3,4]、[2,3,4]、[2,3,4]、[2,3,4]，保留所有旧尝试。01:39:29 复核九个进程仍活跃，四份新 driver 均在 01:38:53 记录 `policy setup start`；此刻仅确认加载开始，尚未确认新 rollout。证据保存在本地 `tmp/inspire/heartbeat_preflight.txt`、`start_boundary_resume.txt`、`status_boundary_resume.txt` 及远端独立 session/attempt 日志。

01:43:35 后续复核确认四路均在 01:41:36 进入续跑 episode：专用原布局为 episode 3/seed 4，其余三路为 episode 2/seed 3，init_state_idx 与 episode 编号一致。九个进程仍活跃，显存 36,349/49,140 MiB；完整有效样本仍 9/180，未发现新的基础设施失败，保持现有进程。

### 第三次 heartbeat 自动恢复

北京时间 02:02 轮次实时查询 RUNNING 但 uptime 小于一分钟；平台事件确认 02:02:31 重新创建并启动容器。Windows 五分钟快照未捕获期间状态变化（恢复序号仍为 2），故不依赖事件序号判断进程存活。远端无相关活跃进程、无新失败标记或异常退出，正式完整样本 13/180；冻结代码、pack、entrypoint 哈希通过校验。

02:03:30 启动 session `20261010T180330Z_4c178c`，master 4417、lane 4451/4454/4456/4458、eval 4517/4518/4519/4521。原布局专用已完成全部五集，因此 lane 0 转到厚度 1.25 专用；其余分别补原布局通用 [2,3,4]、薄 0.75 专用 [3,4]、薄 0.75 通用 [3,4]。四个 driver 在 02:03:35 开始策略加载；02:04:44 复核全部九个进程存活，显存 36,333/49,140 MiB，02:04 后平台仍为 RUNNING。保留旧日志，不改变实验条件。

四路 driver 进一步确认在 02:04:27 进入本次各自的 episode（0、2、3、3），seed 和 init_state_idx 对应正确；已从策略加载推进到实际评测。

### 第四次 heartbeat 恢复尝试（启动核验期间再次抢占）

北京时间 03:32 轮次实时查询已恢复 RUNNING，节点 `qb-prod-4090-gpu197`。远端无 master/lane/eval/cuTAMP 活跃进程、无新失败标记或非零退出，status 校验确认 14/180 个完整唯一样本；冻结 runtime commit、pack 与物理 entrypoint 哈希核验通过。

03:34:03 启动 session `20261010T193403Z_803cda`，master PID 14574、四个 lane 14575–14578、四个 eval 14579–14582。分别续跑厚度 1.25 专用 [1,2,3,4]、原布局通用 [2,3,4]、薄 0.75 专用 [3,4]、薄 0.75 通用 [3,4]，所有旧日志保留。03:35:14、03:36:14 两次核验九个进程存活，四个 driver 于 03:34:24 记录 `policy setup start`，尚无新 episode 证据。

03:37 复核远端查询失败后，实时平台查询为 PENDING，故没有把旧加载日志报告为仍在运行，也没有执行 stop/start 或第二套续跑。此轮只确认发起四路与加载阶段，未确认进入 rollout；待下一轮恢复后重新核验完整样本和进程。

### 第五次 heartbeat 恢复尝试（再次短时抢占）

北京时间 04:07 轮次实时核验 RUNNING，节点 `qb-prod-4090-gpu197`。远端无活跃 master/lane/eval/cuTAMP，无新失败标记或非零退出；status 验证仍为 14/180 个完整唯一样本。冻结 runtime commit、pack、entrypoint 哈希校验通过后，04:08:24 启动 session `20261010T200824Z_0bc394`，master 3838、lane 3839–3842、eval 3843–3846。缺失编号沿用前轮，保留全部旧日志。

04:09:10 复核九个进程存活，显存 34,388/49,140 MiB，但尚未确认新 episode。04:09:35 平台事件确认再次 preempt/evicted，后续远端核验失败且实时状态为 PENDING。不将中断记作机器人失败，不重复启停；下轮恢复后重新核验并续跑。

### 第六次 heartbeat 自动恢复

北京时间 04:27 实时核验实例在 `qb-prod-4090-gpu097` 恢复 RUNNING。无活跃旧 master/lane/eval/cuTAMP，无失败标记或非零退出；status 校验 14/180 完整唯一样本，冻结 runtime commit、pack、entrypoint 哈希通过。

04:28:26 启动 session `20261010T202826Z_346c37`，master 18884、lane 18885–18888、eval 18889–18892。四路分别补厚度 1.25 专用 [1,2,3,4]、原布局通用 [2,3,4]、薄 0.75 专用 [3,4]、薄 0.75 通用 [3,4]。04:29:13 与 04:30:00 核验九个进程存活；四份新 driver 于 04:28:54 记录策略加载开始。尚未确认新 episode，不把加载阶段等同于 rollout；保留旧日志并由下一 heartbeat 继续检查。

04:33:21 后续核验确认四路已在 04:31:32 进入 episode 1、2、3、3，seed 分别 2、3、4、4，init_state_idx 与 episode 编号一致；九个进程仍活跃，显存 37,859/49,140 MiB，GPU 利用率 38%。status 仍验证 14/180 个完整样本，无新基础设施失败标记。保持此 session，不重复启动。

## 平台配置（稳定信息）

沿用前轮配置：项目“具身智能助行外骨骼关键技术研发”、空间“可上网GPU资源”、仅 `xinghanbo-eval`、hdd 根目录 `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`、镜像 `ngc-cuda:12.4.1-devel-ubuntu22.04`。

本地已补齐 `INSPIRE.md` 与账号隔离的 `.inspire/` 项目配置；账号配置不纳入 Git。该配置记录不替代平台实时检查。
