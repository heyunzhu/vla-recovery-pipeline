# C3/C4 spatial-task 50-seed 配对复测

用户于 2026-10-11 授权启动。研究目的为扩大持续 skill benchmark 的配对样本，检验旧 spatial-task 成绩差异；不是优化 skill、mining 或训练新模型。

## 冻结协议

- 两份条件：历史 C3 与 C4 pack；不做 append-only 消融，不改 trigger/profile。
- `libero_spatial_task` 全部 10 个任务，每任务 seed 1–50，两份 pack 各 500 集，共 1000 集。
- episode 0–49 对应 seed 1–50、原预存 init_state_idx 0–49；每个任务现有初始化文件恰好 50 个状态。C3/C4 使用相同 task/seed/init-state 配对。
- 这是初始状态与环境 seed 共同变化的扩展评测，**不是固定状态的重复执行方差实验**。不得把两个概念混用。
- 沿用历史 policy seed 90。runner 的 episode seed 作用于环境；不能声称全部规划器、策略随机源均被每集重新播种。
- 固定运行代码 commit `7128c1ea6280c227e48561e621fe9da8604c5a6d`，同一 Pi0/OpenPI 模型、原 BDDL、初始化 overlay 和环境配置。
- 自然 mining trigger；max_recovery_calls=2、max_recovery_steps=200、max_replans=1。保存视频、query/recovery trace 和完整命令。
- 四路沿用已验证环境；cuTAMP 使用本实验独立 flock 串行锁。

## 资产与输出

只使用启智项目「具身智能助行外骨骼关键技术研发」、空间「可上网GPU资源」的 `xinghanbo-eval`。不改变实例规格、镜像或优先级，不操作其他实例。

历史资产根目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_core60_pilot_20261006`。

新输出根目录：`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/continual_skill_spatial50_20261011`。

manifest 固定两份 pack 全部文件哈希、运行代码 Python 文件哈希、入口/配置/初始化/BDDL 哈希及 1000 个样本的配对规则。启动前核验历史 pack 94 个文件哈希匹配。新结果不与旧 5-seed 结果拼接；seed 1–5 是新尝试。

每次执行写独立 session/attempt，保留中断和错误日志；完整样本按 task/pack/episode/seed/init_state_idx 校验后跳过。基础设施错误不计为机器人失败；非零退出停止该 lane，不无限重试。

## 汇总口径

报告每任务与总体成功率、C4−C3 配对差值、旧成功丢失/新增成功、自然触发比例与首次触发时刻、执行阶段诊断、基础设施无效样本。以 task 为 cluster 计算不确定性；同时给出 seed 1–5 与 6–50 子集，但不挑选结果翻转样本作为总体证据。该实验不能单独估计同状态、同 pack 的重复执行方差。

## 状态

启动前实时核验实例 RUNNING，GPU 空闲，无旧评测进程；冻结两份 pack 与 runtime commit 匹配。

北京时间 2026-10-11 11:14:15 启动 session `20261011T031415Z_df4dd8`，master PID 481983，四个 lane PID 482119/482121/482127/482130，四个 eval PID 482167–482170。首批为 C3/C4 的 task01、task02，每 job episode 0–49。四份 driver 在 UTC 03:14:17 记录 `policy setup start`；后续独立查询确认全部九个进程存活，此时完整样本仍 0/1000，尚未确认实际 rollout，不能将模型加载写作样本推进。

本地启动协议测试 4/4 通过，覆盖自然触发参数、完整失败样本有效性、seed 身份错配拒绝、基础设施错误不计机器人失败。证据：`tmp/inspire/spatial50_preflight.txt`、`spatial50_start.txt`、`spatial50_status.txt`、`spatial50_process_check.txt`。

后续核验四份 driver 均在 UTC 03:16:41 记录 `policy setup done`，03:16:54 进入 episode 0、seed 1、init_state_idx 0；九个进程仍活跃，已确认实际 rollout 开始，完整样本此时为 0/1000，无 `.failed` 或 session 非零退出证据。

任务身份核验通过：benchmark task ID 与 manifest 的词典序资产清单一致；实际任务语言沿用 BDDL，可能与文件名文字不一致（例如 task01 文件名写 between，BDDL 指令为 not between），不能按文件名解释任务。`task_identity_audit.json` 保存冻结 runner 经 `apply_language_sources` 后的实际语言与资产哈希，取代两份初步侧文件的说明/语言字段；评测配置与资产没有改变。

## 2026-10-11 续跑

用户明确授权续跑后，实时核验实例 RUNNING，旧评测进程均已消失。冻结资产及 launcher/config 哈希匹配，419/1000 个唯一样本通过原校验（C3/C4 task01、02、04 各50；task03分别43/49；task06分别15/12），剩余581集。未发现 `.failed`、`.infrastructure_invalid` 或记录的非零 session/attempt 退出码。

启动前宽泛日志扫描拦截了20条 `No such file or directory` 提示；逐条核验均为 JAX 探测可选 TPU 后端缺少 `libtpu.so`，且对应 driver 后续已完成 policy setup、执行 GPU 评测。这些不是 cuTAMP/评测基础设施故障，只有这一精确消息在本地续跑前检查中豁免；未修改冻结 launcher、评测实现或 manifest。

北京时间20:06:36（UTC12:06:36）提交独立续跑 session `20261011T120636Z_813144`，master PID395899，lane PID395901–395904。UTC12:07:07 独立核验 master 与四lane存活、开始跳过完整 job；lane0从 C3_t03 episode43 继续。此时419集，尚处初始化，后续需核验四路实际 rollout。所有旧尝试与中断日志保留。证据：`tmp/inspire/spatial50_resume_start.txt`、`spatial50_marker_inspection.txt`、`spatial50_resume_check.txt`。

UTC12:10:16再次核验：主进程、四lane与四eval均存活；四份新 driver 已在12:08:12–13完成 policy setup，并于12:08:20进入实际 episode。断点分别是 C3_t03 ep43/seed44/init43、C4_t03 ep49/seed50/init49、C3_t06 ep15/seed16/init15、C4_t06 ep12/seed13/init12，身份符合冻结配对规则，确认四路已从断点实际续跑。完整样本仍419/1000（续跑首集尚未完成），无 `.failed`。不将启动或进入 episode 误报为新增完成样本。

## 2026-10-11 第二次续跑

用户再次授权续跑。实时实例 RUNNING，落点 qb-prod-4090-gpu096，规格、镜像和优先级未变。旧评测进程已消失，冻结资产及样本身份校验通过；完整样本422/1000，剩余578集。C3_t03已44集，C3_t06已17集，其余相对419集检查不变。无 `.failed`、`.infrastructure_invalid`、记录的非零退出或新的基础设施错误；28条可选 TPU 探测提示按前次精确审查口径处理。

北京时间21:24:27（UTC13:24:27）启动独立 session `20261011T132427Z_8b98a0`，master PID249331，lane PID249333–249336。保留前两次全部日志及完整样本，不改冻结 launcher/manifest/pack。UTC13:25:09确认主进程与四lane存活，已开始按各job跳过完整样本，尚在初始化阶段。证据：`tmp/inspire/spatial50_resume2_start.txt`、`spatial50_resume2_check.txt`。

四路于UTC13:27:41完成 policy setup，13:27:54进入断点 episode：C3_t03 ep44/seed45/init44，C4_t03 ep49/seed50/init49，C3_t06 ep17/seed18/init17，C4_t06 ep12/seed13/init12。一次较长诊断传输返回非零，但已输出上述日志与422集校验结果；未将此传输退出码视为评测session退出，也未重复启动。UTC13:31:33短诊断成功返回0，确认5个master/lane进程、4个eval及cuTAMP相关进程活跃，新driver日志继续增长；无 `.failed`，session未退出。四路实际续跑核验通过，尚未把当前进行中的episode计为完成。独立证据：`tmp/inspire/spatial50_resume2_live.txt`。

## 2026-10-12 完成核验

用户授权启动原实例并核验；启动一次后实时确认 RUNNING（qb-prod-4090-gpu097），规格、镜像和优先级未改，没有再次启动评测。北京时间10:16:45（UTC02:16:45）冻结资产校验通过，原 launcher 逐样本校验1000/1000（20jobs各50集），`all.done`存在，`completed_index.json`与重新扫描的canonical索引完全一致。最终session `20261011T132427Z_8b98a0`四lane退出码 `[0,0,0,0]`；无 `.failed` 或 `.infrastructure_invalid`，无残留master/lane/eval/cuTAMP进程。

完整样本初步汇总：C3成功380/500（76.0%），C4成功374/500（74.8%），C4−C3为−1.2个百分点。这只是总体描述性结果，尚未计算配对翻转和按task聚类的不确定性，不据此宣称显著退化或证明无遗忘。完整核验证据保存于 `tmp/inspire/spatial50_completion_verified.txt`；原评测日志保留，实例未停止或删除。
