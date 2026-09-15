# Offline Skill Trigger Scan

更新日期：2026-09-09

本文说明 skill pipeline 里的离线触发扫描环节：

1. 评测 run 结束后，把足够做离线 trigger replay 的 trace 归档到仓库下；
2. 新 skill 写完后，一键跑静态 gate 和全局离线触发扫描。

它的目的不是重新仿真，而是在历史 rollout 素材上用当前 matcher 重新计算：

- 哪些 `repair` skill 会触发；
- 哪个 `repair` 会成为 winner；
- recovery 触发时会合并哪些 `grasp` / `grounding` / `geometry` / `place` hint；
- 新 skill 是否在旧成功 episode 上出现明显误触发；
- 新 skill 是否抢占已有稳定 skill。

## 1. 评测结束后的持续归档

harness 现在默认在所有 GPU lane 结束后执行：

```bash
python scripts/recovery/skill_pipeline/archive_offline_scan_corpus.py \
  --run-dir "$RUN_DIR" \
  --repo "$REPO" \
  --corpus-root "$REPO/analysis_outputs/offline_trigger_corpus" \
  --name "$(basename "$RUN_DIR")"
```

归档只复制每个 episode 的轻量 trace：

```text
episode.json
query_trace.jsonl
recovery_trace.jsonl
```

同时复制 run 级元数据：

```text
resolved_spec.json
paths.json
git_head.txt
git_status.txt
lanes.json
harness_summary.json
harness_gates.json
harness_report.md
all_done.txt
```

不复制 `video.mp4`、annotated video、frames、cuTAMP debug 目录或其它大文件。

默认 corpus 位置：

```text
analysis_outputs/offline_trigger_corpus/<run_name>/
```

每个 corpus 会写 `manifest.json`，记录来源 run、episode 数、task 成功率、query 行数和已复制文件。

mining lane 也会持续沉淀 trace：`scripts/recovery/skill_pipeline/run_mining_lane.py`
默认会把 skills-off baseline 和每个 same-init validation run 归档到同一个 rolling corpus。
这意味着不需要先手工整理一份“大离线素材库”；素材随着 baseline、validation、regression
自然积累。

## 2. 评测结束后的即时扫描

harness 现在默认还会执行：

```bash
python scripts/recovery/skill_pipeline/scan_skill_triggers.py \
  --run-dir "$RUN_DIR" \
  --skill_pack <pack> \
  --out-dir "$RUN_DIR/offline_skill_scan"
```

输出：

```text
offline_skill_scan.json
episode_skill_scan.csv
skill_scan_summary.csv
query_skill_matches.csv
offline_skill_scan.md
```

`scan_skill_triggers.py` 不读取旧的 `skill_match_diagnostics` 作为结论，而是用当前仓库的
`SkillRuntime` / `matcher.py` 重新 replay `query_trace.jsonl`。因此它可以用于比较：

- 当时 rollout 里实际发生了什么；
- 当前 skill 库如果放到同一批 qstate 上，会怎样触发。

扫描使用 active skill pack 的同一套 runtime：repair 命中后会合并 recovery-hint skill，并展开
`grounding_profile`、`geometry_profile`、`repair_profile`、`place_profile`。因此报告中的
`executor_overrides`、`place_policy`、`grounding_hints` 和 `geometry_hints` 是经过当前
profile registry / pack-local adapter 处理后的结果，不只是 Markdown frontmatter 原文。

## 3. Harness 开关

`HarnessSpec` 新增四个字段：

```yaml
archive_offline_scan_corpus: true
offline_scan_corpus_root: analysis_outputs/offline_trigger_corpus
offline_skill_scan: true
offline_scan_include_hints: true
```

含义：

| 字段 | 含义 |
| --- | --- |
| `archive_offline_scan_corpus` | 是否在 run 结束后复制轻量 trace 到仓库 corpus。 |
| `offline_scan_corpus_root` | corpus 根目录。相对路径按 repo 根目录解释。 |
| `offline_skill_scan` | 是否在 run 结束后对本次 run 立即跑离线 trigger scan。 |
| `offline_scan_include_hints` | scan 是否同时统计 recovery hint 匹配；关闭后只看 repair trigger。 |

如果 postprocess 失败，`all_done.txt` 会记录 `postprocess_exit_code`，harness 退出码也会变为失败。

## 4. 写完 skill 后的 admission gate

对单个候选 skill 使用：

```bash
python scripts/recovery/skill_pipeline/run_skill_admission.py \
  --skill-pack <pack> \
  --skill-file skill_packs/<pack>/skills/pair/recovery_hint/grasp/example.md \
  --fallback-scan-root "$CURRENT_TASK_RUN" \
  --scan-root analysis_outputs/offline_trigger_corpus/<run_name> \
  --out-dir /tmp/skill_gate_example
```

它会做五件事：

1. 用 `schema.py` 解析候选 skill；
2. 对已实现静态 gate 的类别运行类型检查；
3. 把当前 task run、显式 canary/root、rolling corpus 最近若干 run 合成一套全局 scan set；
4. 把候选 skill 加进当前 skill 库并用同一个 matcher 离线 replay；
5. 对 `repair` / `trigger` 草稿同时检查当前失败命中率和全局成功 episode 误触发 / winner 抢占。

如果还要把 generated benchmark smoke 纳入门禁，把冻结目录和已完成的 smoke run 一起传入：

```bash
python scripts/recovery/skill_pipeline/run_skill_admission.py \
  --skill-pack <pack> \
  --skill-file skill_packs/<pack>/skills/pair/recovery_hint/grasp/example.md \
  --fallback-scan-root "$CURRENT_TASK_RUN" \
  --scan-root analysis_outputs/offline_trigger_corpus/<run_name> \
  --generated-benchmark-dir benchmarks/libero90_generated_v1_envfiltered_304 \
  --generated-split smoke \
  --generated-smoke-run-dir remote_outputs/generated_benchmark_smoke_v1_304_20260904_r1/smoke_vla_only_3ep \
  --require-generated-smoke \
  --out-dir /tmp/skill_gate_example
```

generated benchmark gate 不重新仿真，只检查：

- frozen benchmark 的 `FREEZE.json`、summary、manifest 和 BDDL 是否一致；
- generated goal 段是否还残留 LIBERO runtime 不识别的 `Inside` / `On` 大写谓词；
- smoke split 的每个 task 是否至少有指定条数的 episode；
- 每个 smoke episode 是否产出 `episode.json`、`query_trace.jsonl` 和需要的视频。

当前代码层面已经实现了 `repair` 和 `grasp` 的类型静态 gate；`grounding`、`geometry`、
`place` 会先执行 schema / capability gate 和 offline scan，并在结果中明确记录
`schema_only: true`。后续补专门类型 gate 时，继续接入这个入口即可。

输出：

```text
skill_admission_result.json
skill_admission_report.md
grasp_static_gate.md
grasp_static_gate.json
offline_scan/
```

如果没有显式传 `--scan-root`，`run_skill_admission.py` 会默认扫描
`analysis_outputs/offline_trigger_corpus/` 下最近的 archived run。可以用
`--corpus-root` 和 `--max-corpus-runs` 控制这个 rolling window。`--fallback-scan-root`
现在表示当前 task/run root，会和 rolling corpus 一起进入同一个全局 scan；它不是
“没有 corpus 时才回退”的第二套局部检查。

如果 admission 发现 scan 里只有当前 task episode、没有任何 non-current episode，默认会失败。
调试时可以显式加 `--allow-current-only-scan`，但这种结果不能说明全局安全性。

## 5. 在 mining loop 中的位置

推荐顺序：

```text
online/baseline rollout
  -> archive trace corpus
  -> triage / Codex 写 draft skill
  -> run_skill_admission.py
       -> schema / static gate
       -> global offline trigger scan
            current task traces + rolling corpus + explicit canaries
       -> current-task effectiveness / global safety checks
  -> 同 init validation
  -> 入 pair/online 或保留 fail_only / 丢弃
```

离线扫描不能替代真实 validation。它只回答“这个 skill 在旧 qstate 上会怎样触发”，不回答
“触发后真实 recovery 一定成功”。但它很适合防止 agent 在 mining 中写出过宽 trigger、
抢占稳定 skill，或让 recovery hint 在无关目标上大面积匹配。

当前 repair admission 的关键区别：

- `current_task_effectiveness`：当前 task 内允许覆盖既有成功 episode，但要求首次触发不早于
  默认 q5，且最终 same-init validation 不回退。
- `global_safety`：非当前 task 更严格；新 repair 如果成为成功 episode 的实际 winner 则失败。
  只 would-fire 但被更高优先级 skill shadow 的记录是 report-only。
