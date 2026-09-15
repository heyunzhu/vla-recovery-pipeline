# Mining agent 能力恢复与自动化验收

## 目标与分工

恢复成功轮次中的完整工作过程：agent 读关键帧、trace、约束和实现，提出并验证假设，
编写 skill/profile/pack-local 代码，修复检查错误，再交给 runner 做正式 validation。
daemon 不编写 skill，不替 agent 推断物理根因。

本轮使用 gpt-5.5、xhigh。通过独立 codex exec 运行，不向人工讨论窗口排队。
模型参数写进进程记录；标准输出实时落盘，保留 Codex 会话、最终结果和工作目录。

## 上下文

actor_context.py 从当前 lane、mine_state、evidence 和实际 episode 建立 context.json：

- suite、task、任务描述、原始 BDDL goal、seed、当前候选、pack 文件哈希与部署哈希；
- recovery 对应 query 的前后信号、关键帧、trace 和 problem/result/stderr 路径；
- 验证根目录共享 cutamp_debug 与 ep 私有 debug 明确区分，不把共享日志冒充某个 ep；
- 每轮实际成功数、改善与退化的 ep、无效验证；
- 前几轮 findings.md，保留假设、检查结果和未解决问题。

五类指南使用同一份目录生成逻辑；daemon 将全文文件复制到本轮 guidance 目录并给出
路径和哈希。prompt 不再内联十多万字符。agent 必须阅读本轮涉及类型的指南；文件存在
或 prompt 列出路径不等于已阅读，验收时须查看实际工具记录。

## 修改与三类检查

skill markdown 仍由 bundle.yaml 声明。需要改代码时，完整替换文件写在：

```text
drafts/patch/skill_packs/<当前 pack>/code/...
drafts/patch/skill_packs/<当前 pack>/profiles/...
drafts/patch/skill_packs/<当前 pack>/capabilities.yaml
```

code_patch_manifest.yaml 声明仓库相对路径。daemon 在当前 pack 内应用文件，再运行现有
静态检查、能力注册检查与全局离线扫描；失败回滚 pack，检查反馈交回同一轮介入。
检查前后的文件文本用于计算新增能力，避免将既有 profile 当成新能力要求重复登记。
skill index 与 pack 身份不允许由 patch/ 替换，markdown 入库由既有 ingest 完成。

agent 可在一次介入内做小 replay、测试、补注册和修改，不必为每个诊断动作消耗一个
skill 版本。正式有效 validation 后才评价效果；无效进程结果隔离并重试相同候选。
这仍是静态检查、离线扫描、rollout 验证三类检查，没有另设语义评分门禁。

## 自动接续

supervise_mining.py 只绑定一个 run_root 和 workdir，每 30 秒读取实时状态。
本地存活进程持有的锁不会因为超过十分钟被夺走；远端事件 claim 使用独占创建。
提交前复查 task/write/evidence/pack 哈希，过期结果不能覆盖新 pack。
validation 使用远端 flock 防止重复启动，保留 pid、日志和退出码。

进程阶段包括 prepared、agent_running、draft_ready、admitting、ingested、
validation_requested；监督器区分 validation_running、completed 和错误。
已完成的草稿在本地进程或 SSH 中断后尽量复用，活动 actor 不重复投递。
远端重复基础设施故障保留候选并报错，不捏造成功率或自动改引擎/环境。
本地监督器仍需电脑在线；它不能在电脑关机时调用本地 Codex。

## task07 验收

目标：libero_goal_swap task07，put the cream cheese in the bowl，seed51-65。
新 pack 从 32486bb 的空 scaffold 提取，不提供后来达到 11/15 的 skill 答案。
复用当时 skills-off baseline，单独保存 provenance。历史数据没有保存完整环境哈希，
不能把这轮称为原运行的逐字节复现；启动前核对当前官方 suite 的任务和资源路径。
当前代码单独打快照，部署文件哈希逐项校验。模型为 pi0_libero JAX；保留真实 cuTAMP、
cuRobo 和 real_cutamp_serialize_trajectories，正式验证每轮最多 15 ep，5 次 skill 写入。

验收看实际指南/图像/日志阅读、pack 代码是否生效、自动检查与续跑是否完成，最后查看
是否达到 9/15。启动成功、测试通过、agent 返回 drafted 都不等于已经恢复 mining 效果。

实际验收使用 r2 目录：

- run: /mnt/nas/gezuhao/xinghanbo/logs/libero_goal_swap_task07_actor_acceptance_20260912_r2
- snapshot: /mnt/nas/gezuhao/xinghanbo/code_snapshots/actor_acceptance_task07_20260912_r2
- pack: libero_goal_swap_task07_actor_acceptance_20260912_r2
- 本地工作记录: experiments/.pro/actor_acceptance_20260912_r2/work
- 本地输出: experiments/.pro/actor_acceptance_20260912_r2/supervisor.log
- 当前活动 actor 的进程与心跳: work/<event>/attemptN/actor_process.json
- 工具调用与输出: 同一目录下 codex_output.jsonl

旧 CodexMiningDaemon Windows 定时任务保持禁用。这轮使用独立、无窗口的 supervisor
进程，不恢复旧 run、不向讨论窗口投递。正式结果需从新 run 的 mine_state 读取。
全局离线扫描读取原工作区的 offline_trigger_corpus，当前轮新增素材写到新 run 的
mine/offline_trigger_corpus；历史素材只读。

运行中暴露的 Windows SSH 引号问题，通过 actor_remote.py 提供固定工具处理：
read/list/get 和将本地 Python 文件经 stdin 发给远端的 script。它不依赖 jq，也不需要
agent 拼接多层 shell 引号。脚本执行仍遵守当前 run 和 pack 的写入边界。

不带 r2 后缀的初次试运行已经停止：打包器排除了正式 skill 库，但遗漏 archive/，
agent 开始搜索归档内容，因此不能作为干净验收。它未入库、未运行 validation，writes=0。
保留其全部记录，不计为一版失败 skill。r2 排除 archive/，使用独立 run/pack/workdir。
从原始 Codex 会话 turn_context 已核实首次实际运行模型为 gpt-5.5、effort=xhigh，
并查到 12 次 view_image 及 repair 指南读取记录；这些仅验证介入能力，不代表最终成功率。

本地验证：136 项相关测试通过，包括已有 mining/code-admission 测试与新增上下文、
补丁回滚、入库中断、旧结果拒收、独占 claim、活进程不超时重投、模型参数检查。
