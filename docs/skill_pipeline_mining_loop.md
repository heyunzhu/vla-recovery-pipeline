# Skill 挖库外环（task 级同 init 验证）

本文是离线挖库的操作说明。规格仍以 `docs/agentic_skill_recovery_pipeline.md` 为准。在线控制环不调用 Codex；`--enable_skills` 只加载当前 skill pack 的 `_index.yaml` 里 `online:` 列表。`fail_only` 草稿只在挖库验证里用 `--enable_mining_skills` 加载。

当前所有 mining / eval / admission 命令都必须用 `--skill_pack`（或底层 `--skill_index`）显式选择隔离库。`libero90_legacy` 用于复现 LIBERO-90 旧库；`generated_v1` 用于新生成任务挖库。本仓库不再提供根目录 `skills/` 或 `skills_scratch/` 兼容入口。

Codex actor 实际读取的上下文由
`scripts/recovery/skill_pipeline/run_codex_actor.py` 组装，包含：

- active skill pack 的 `_index.yaml`、`capabilities.yaml`、profiles、pair / fail_only skill；
- `docs/repair_skill_authoring_guidelines.md`
- `docs/grasp_skill_authoring_guidelines.md`
- `docs/grounding_skill_authoring_guidelines.md`
- `docs/geometry_skill_authoring_guidelines.md`
- `docs/place_skill_authoring_guidelines.md`
- `docs/offline_skill_trigger_scan.md`
- `docs/skill_pack_isolation_2026-09-09.md`
- `docs/diagnostic_signal_pipeline.md`
- `docs/skill_capability_registry.md`
- rollout evidence JSON：`pair.json` 或 `fail_set.json`，在 actor prompt 中标为
  `Rollout evidence JSON`。这是写 skill 的轨迹/诊断证据，不是 active skill pack 的
  `pack.yaml`。

因此修改 agent 行为时，要优先改这些文件，而不是只改总览文档。

## 过关条件

对当前 task 做 **同 init 5 条**（与 skills-off 基线相同的 `task_id + episode_idx + seed`），开挖掘库后：

1. **成功率 ≥ 3/5（60%）**
2. **不比基线差**（成功条数不得低于关 skill 的那 5 条）
3. **失败要分诊**：开库后仍失败的 episode 会按 `trigger/grasp`、规则绑定、cuTAMP 约束、executor guard 等证据分类

前两条成立就算这个 task **passed**，可以进入下一 task；残余失败如果没有 `hook_fired` / `skill_id` 会作为 warning 和 triage evidence 保留。
打中 trigger ≠ 任务成功。没有成功率门槛时不得把 task 标成已覆盖。

如果前两条不成立，`score` 会先写出 `taskXX/triage_wN/triage_report.{json,md}`：

- `skill_repairable`：未触发、触发太晚、grasp 候选/close/lift 这类 skill 可控问题；继续打包失败并调用 Codex 写 `fail_only` 草稿。
- `needs_capability`：规则表绑定、cuTAMP 零可行粒子/碰撞约束、executor release/lift guard、轨迹跟踪等问题；这些不再终止写作，而是要求 Codex 优先尝试 pack-local grounding / geometry / grasp / place / diagnostic-signal / adapter 能力。
- `needs_diagnostics`：证据不足；也会进入 Codex 写作，但本轮必须产出可执行诊断信号或保守 skill/profile/code，不能只写说明。

当 triage 进入 `repair` 写作时，Codex actor 必须按 `docs/repair_skill_authoring_guidelines.md`
编写；ingest / 晋升前必须按 `docs/repair_skill_static_test_standard.md` 通过静态检查和
global trace replay。当前入库门禁入口是 `scripts/recovery/skill_pipeline/run_skill_admission.py`；
它会把当前 task run、显式 canary/root 和 rolling corpus 最近若干 run 合成一套全局 scan
set，再用当前 matcher 在旧 `query_trace.jsonl` 上离线扫描触发。报告拆成
`current_task_effectiveness` 和 `global_safety`：前者确认草稿确实覆盖当前失败，后者拦截
在其它 task / 成功 episode 上过宽触发或成为 winner 的 repair 草稿。同 task 内的 overlap
不自动算 fatal：只要 validation 成功率不下降、首次触发不早于合法窗口，允许新 repair 覆盖
同 task 过去的成功 episode，以免同一 failure mode 被拆成一堆重复 skill。非当前 task 则按
priority / winner 判断：只 would-fire 但被更高优先级稳定 skill 盖住，不算实际误触；如果新
skill 成为非当前成功 episode 的 winner，则 admission 失败。缺少必要谓词或 runner 诊断字段时，
只能在 findings 中提出补充需求，不得把未登记谓词直接写入 trigger。`findings.md`
不能作为唯一产物；diagnostics-only / blocker-only bundle 会被 admission 拒绝，且不应消耗一次有效写作预算。

当 triage 判定问题属于 `grasp`，Codex actor 必须按
`docs/grasp_skill_authoring_guidelines.md` 编写；ingest / 晋升前必须跑
`scripts/recovery/skill_pipeline/check_grasp_skills.py`，并满足
`docs/grasp_skill_static_test_standard.md` 的 catalog、scope、profile、canary 和
executor 参数检查。
新增 benchmark-specific grasp profile 时，代码写入 active skill pack 的
`code/grasp_profiles.py`，并由该 pack 的 `_index.yaml` / `pack.yaml` 暴露 adapter；不要再把
LIBERO-90 特化采样写进主流程文件。

当 triage 判定问题属于 `grounding`，Codex actor 必须按
`docs/grounding_skill_authoring_guidelines.md` 编写；ingest / 晋升前必须满足
`docs/grounding_skill_static_test_standard.md` 的 catalog、scope、intent、BDDL/region
锚点、配套 geometry 和 canary 检查。grounding 草稿只能修改目标语义绑定，不得混入
grasp、geometry、place 或 executor 逻辑。新增 benchmark-specific grounding 逻辑应写在
active pack 的 `profiles/grounding.yaml` 与 `code/grounding_profiles.py` 中，并映射到
主引擎已支持的通用 grounding primitive；如果确实缺少新的通用 primitive，应先写
`findings.md` 中说明缺失的共享 primitive，不要把任务特化分支塞进
`real_cutamp_adapter.py`。如果已有通用 primitive 能表达，则应写 pack-local profile /
adapter，而不是只写 blocker。

当 triage 判定问题属于 `geometry`，Codex actor 必须按
`docs/geometry_skill_authoring_guidelines.md` 编写；ingest / 晋升前必须满足
`docs/geometry_skill_static_test_standard.md` 的 catalog、scope、intent、数值范围、
region 来源、grounding 配套、collision / release 边界和 canary 检查。geometry 草稿只能
修改 planner 几何表示。新增 benchmark-specific region 测量、裁剪或 fallback 应写在
active pack 的 `profiles/geometry.yaml` 与 `code/geometry_profiles.py` 中，并输出主引擎
已支持的通用 geometry primitive 或 registered descriptor shape。若需要斜面、圆环、漏斗等
新通用 primitive，应作为共享引擎能力单独提出；不得把未被运行链路消费的字段直接写进 skill。

当 triage 判定问题属于 `place`，Codex actor 必须按
`docs/place_skill_authoring_guidelines.md` 编写；ingest / 晋升前必须满足
`docs/place_skill_static_test_standard.md` 的 catalog、scope、executor allowlist、数值范围、
适用范围、place 阶段证据和 canary 检查。place 草稿只能修改已经 holding 目标后的
executor-side 局部动作，不得混入 trigger、grounding、geometry 或 grasp 逻辑。正式入库的
place skill 应引用 `params.place_profile`；profile 在 `profiles/place.yaml` 中声明
`hooks.hover` / `hooks.align` / `hooks.release`，再由 active pack 的 `code/place_policies.py`
展开到受限 executor 参数。新增未支持的 executor 动作属于共享引擎改动，不能伪装成
task-specific place profile。

如果确实需要新增 runner 诊断信号，进入单独的 diagnostic-signal 节点，按
`docs/diagnostic_signal_pipeline.md` 写 draft / shadow provider。新信号默认只记录在
`diagnostic_signals` 字段中，不得直接影响 online repair matcher。

如果 skill 需要配套修改 Python 能力代码或 profile registry，必须同时写
`code_patch_manifest.yaml` 并打开 code admission。code admission 只检查两件事：改动是否留在
声明的扩展边界内，以及新增/使用的 capability 是否已在当前 skill pack 的 `capabilities.yaml`
注册。它不是人工 review，也不会替代 same-init rollout validation。

当前 code admission 的意图是：普通 mining draft 可以新增 pack-local skill、profile、
adapter、capability registry 和测试；不能为了一个 task 直接修改 runner、planner、executor
主引擎。只有当 `findings.md` 明确指出“缺的是跨 benchmark 可复用的通用 primitive / executor
行为”时，才应把主引擎修改作为 engineering action 单独处理。

## 保底

每个 task 默认最多让 Codex **写 5 次**（`ingest` 成功一次算一次，可用
`--max_writes_per_task` 覆盖）。第五次同 init 仍不到 3/5：

- 留下五次里成功率最高的 `fail_only` 草稿和诊断报告
- 状态为 `write_budget_exhausted`，`sr_passed: false`
- **流水线继续下一个 task**，不卡住
- 弱草稿 **不能**让后面的 task 跳过验证：下一 task 仍必须先带着当前库跑 5 条

`write_budget_exhausted` 和未达标草稿都不得写入 `online:`。晋升 pair 仍走规格第 8.2 / 8.3。

## Task1 → Task5 示例

```text
task1  库空 → Codex 写 #1 → ingest（code admission / global offline scan 通过才收）
     → --enable_mining_skills 跑 5 条
     → ≥3/5 且不回退且失败条有命中 → passed → task2
     → 否则再写，最多 5 次；五次都不够 → write_budget_exhausted → task2

task2  先带着库跑 5 条（不先叫 Codex）
     → 已 ≥3/5 且不回退 → 不必 Codex，进 task3
     → 否则先 triage；skill_repairable / needs_capability / needs_diagnostics 都会调用 Codex 写，同样最多 5 次，不够则 write_budget_exhausted
     → write_budget_exhausted 记录原因，进 task3
```

## 命令

基线 skills-off 目录记为 `$BASE`（例如 `.../20260820--jax_t1_20_n5_baseline`）。

```bash
# 推进到下一步：need_draft 或 need_validation
python scripts/recovery/skill_pipeline/run_skill_mine.py step \
  --run_dir "$BASE" \
  --out_dir "$MINE" \
  --task_ids 1-5 \
  --skill_pack generated_v1

# Codex 只读 actor_prompt.md，写出 draft.md 后
python scripts/recovery/skill_pipeline/run_skill_mine.py ingest \
  --run_dir "$BASE" --out_dir "$MINE" --draft_md /path/to/draft.md \
  --skill_pack generated_v1

# 真实 mining 推荐打开入库门禁；纯 Markdown skill 用这一组
python scripts/recovery/skill_pipeline/run_skill_mine.py ingest \
  --run_dir "$BASE" \
  --out_dir "$MINE" \
  --draft_md /path/to/draft.md \
  --enable_admission_gate \
  --skill_pack generated_v1 \
  --generated_benchmark_dir "$REPO/benchmarks/libero90_generated_v1_envfiltered_304"

# 如果草稿还包含 Python / profile / capability registry 变更，再追加 code admission
python scripts/recovery/skill_pipeline/run_skill_mine.py ingest \
  --run_dir "$BASE" \
  --out_dir "$MINE" \
  --draft_md /path/to/draft.md \
  --enable_admission_gate \
  --enable_code_admission_gate \
  --code_manifest /path/to/code_patch_manifest.yaml \
  --skill_pack generated_v1 \
  --generated_benchmark_dir "$REPO/benchmarks/libero90_generated_v1_envfiltered_304"

# ingest / step 给出的 validation.command：用 JAX 环境跑同 init 5 条
# 必须带 --enable_mining_skills，不要用生产 --enable_skills
# 命令会自带主线 cuTAMP/cuRobo 开关（--use_real_cutamp_backend 等），不要再手工删掉
# 规划器默认为 scripts/recovery/skill_pipeline/cutamp_runner_py310.sh
# 可用 CUTAMP_RUNNER_PYTHON 覆盖
# 验证命令带 --require_real_cutamp_executable_plan：cuRobo 没给出关节轨迹时不要走 optimized 插值
# run_mining_lane.py 默认 --max_recovery_calls 2、--max_recovery_steps 200；
# LIBERO-90 book-caddy 已知稳定 profile 使用 280 step budget，见 known-good harness spec。
# 每次验证都应先检查 resolved_spec.json 和 validation.command，确认没有回到旧参数。

# 跑完后打分
python scripts/recovery/skill_pipeline/run_skill_mine.py score \
  --run_dir "$BASE" --out_dir "$MINE" \
  --on_dir "$MINE/validation/<exp_name>"
```

## 远端 Codex 介入 Watchdog

`run_mining_lane.py` 在每个 lane 启动时会写：

```text
$MINE/lane_command.json
```

其中包含原始启动参数、工作目录和可直接复用的 `command_preview`。当 lane 到达
`need_draft` / `awaiting_draft` 时，它会写：

```text
$MINE/WAIT_CODEX.json
```

并以 exit code 20 退出。远端应同时启动一个轻量 watcher：

```bash
python scripts/recovery/skill_pipeline/watch_mining_interventions.py \
  --run-root "$RUN_ROOT" \
  --poll-sec 15 \
  --quiet
```

watcher 不调用 Codex、不占 GPU。它只扫描 `$RUN_ROOT/*/mine/WAIT_CODEX.json`，并生成：

```text
$RUN_ROOT/codex_interventions/
  LATEST_CODEX_EVENT.json
  PENDING_CODEX_EVENTS.json
  watchdog_status.json
  events/<event_id>/
    event.json
```

`event.json` 会包含 `task_id`、`writes_used`、`evidence_json`、`actor_prompt`、`mine_dir`、
`lane_command_json`、`wait_sha256` 和 missing-file 检查结果。同一个 WAIT 会生成稳定
`event_id`，重复扫描不会重复创建事件。

本地 heartbeat 不再直接猜 lane 状态，只做 live status check 后读取：

```text
$RUN_ROOT/codex_interventions/PENDING_CODEX_EVENTS.json
$RUN_ROOT/codex_interventions/LATEST_CODEX_EVENT.json
```

如果 `PENDING_CODEX_EVENTS.json` 里有新的 `status: codex_required`，本地 Codex 应先 claim：

```bash
python scripts/recovery/skill_pipeline/mark_mining_intervention.py claim \
  --event-root "$RUN_ROOT/codex_interventions" \
  --event-id "<event_id>" \
  --actor codex
```

然后读取 `actor_prompt`，写 `draft.md` 或 `bundle.yaml`，执行 `run_skill_mine.py ingest`。
ingest 完成后写 resolved：

```bash
python scripts/recovery/skill_pipeline/mark_mining_intervention.py resolve \
  --event-root "$RUN_ROOT/codex_interventions" \
  --event-id "<event_id>" \
  --draft-md /path/to/draft.md \
  --ingest-result-json /path/to/ingest_result.json \
  --resume-command "<lane_command.json 里的 command_preview>"
```

最后用 `lane_command.json` 里的 `argv` 或 `command_preview` 重启该 lane。这样 Codex
介入、入库、恢复 validation / score 都有可审计记录；即使本地断线，远端事件仍然保留。

`--enable_admission_gate` 的默认扫描策略：

1. 当前写作包对应的 run root 一定进入 scan set；
2. 显式传入的 `--admission_scan_root` 作为额外 canary/root 加入 scan set；
3. `--admission_corpus_root` 下最近 `--admission_max_corpus_runs` 个 archived run 也加入 scan set；
4. 如果 scan 只有当前 task、没有 non-current episode，默认 admission 失败，防止 current-only
   检查被误读成全局安全。

`--enable_code_admission_gate` 只在草稿包含 Python / profile registry / capability registry
改动时需要；纯 Markdown skill 可以只跑 schema / static / offline scan admission。带代码改动的
草稿必须提供 `code_patch_manifest.yaml`，并列出 `change_type`、`touched_files` 和新增或依赖的
capability。

repair admission 的判定口径：

- 当前 task：看是否覆盖失败、是否过早触发（默认首次触发必须 `query_idx >= 5`）、以及后续
  same-init validation 是否不低于基线。
- 非当前 task：只要新 repair 成为成功 episode 的 winner 就失败；如果它只是 would-fire，
  但实际会被更高优先级 skill shadow，不算 fatal，会写入 report。
- recovery hint：离线扫描主要检查匹配范围、hint 合并和是否误盖历史成功 episode；最终是否
  有效仍看真实 validation。

如果 `ingest --enable_admission_gate` 返回 `status: admission_failed`，不要跑 validation：
草稿没有进入 `skills/fail_only/`，`_index.yaml` 也不会被改。报告在
`$MINE/taskXX/admission_wN/skill_admission_report.md`，修草稿后重新执行 `ingest`。

`status` 查看 `mine_state.json`（`writes`、`attempts`、`best`、`awaiting_kind`、`last_triage`）。每次 `score` 让一个 task 终止时还会更新 `mine_summary.{json,md}`，用于快速查看 passed / write_budget_exhausted / needs_capability / needs_diagnostics。

## 实现位置

- `experiments/robot/libero/skill_pipeline/mine.py`：过关、五次上限、保底；`mining_validation_command` 自带真 cuTAMP/cuRobo 开关
- `experiments/robot/libero/skill_pipeline/triage.py`：验证失败后的 skill/system 分诊和 report 导出
- `experiments/robot/libero/skill_pipeline/runner.py`：`--enable_mining_skills`
- `experiments/robot/libero/skill_pipeline/trace_corpus.py`：评测 run 结束后归档离线扫描素材
- `experiments/robot/libero/skill_pipeline/trigger_scan.py`：用当前 matcher replay 历史 query trace
- `experiments/robot/libero/skill_pipeline/admission.py`：把 schema / static / offline scan / generated smoke 合成入库门禁
- `scripts/recovery/skill_pipeline/run_skill_mine.py`：`step` / `ingest` / `score`
- `scripts/recovery/skill_pipeline/run_skill_admission.py`：候选 skill 入库门禁统一入口
- `scripts/recovery/skill_pipeline/run_code_admission.py`：候选 code/profile 变更的边界和能力注册检查
- `scripts/recovery/skill_pipeline/run_skill_quality_gate.py`：低层质量检查入口，保留给单项调试使用
- `scripts/recovery/skill_pipeline/run_mining_lane.py`：自动跑 validation，并把 baseline / validation 轻量 trace 持续归档到 rolling corpus

阈值：`TASK_SUCCESS_MIN = 0.60`，`DEFAULT_MAX_WRITES_PER_TASK = 5`。改阈值必须改测试。
