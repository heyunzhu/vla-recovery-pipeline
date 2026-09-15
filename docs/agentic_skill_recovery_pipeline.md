# Agentic Skill Recovery Pipeline

本文档是后续实现的唯一规格。写代码时按本文执行，不要沿用旧评测日志格式，也不要把 Codex / 大模型放进在线控制环。双轨口径的讨论记录见 `docs/skill_pipeline_dual_track_2026-08-20.md`。

灵感来自 Aspire（Agentic Skill Programming through Iterative Robot Exploration）：细粒度 traces、对照失败归因、验证后再把可复用模式写入 skill 库。我们不把 Pi0 整条策略重写成 code-as-policy。在线策略仍是 Pi0；skill 只决定 **何时离开 VLA** 以及 **离开后跑哪段已有修复后端**。

旧仿真日志（`query_trigger.csv` + 降采样视频 + 偶发 `cutamp_recovery`）不足以让 Codex 写出可靠的 trigger skill。挖掘 skill 和验证 skill 都必须用 **重写后的评测 runner** 重新跑仿真。

---

## 1. 目标与非目标

### 目标

1. 离线：支持两条写作线——同一 task 的成功/失败 pair，或 libero_90 上的失败单边集合。Codex 写出「何时调用 cuTAMP」的 skill。
2. 在线：Pi0 正常推理；hook 上的 matcher 命中 **pair 库**里的 skill 后，dispatcher 调用已有执行桥（主线是 `cutamp_recover`），结束后交还 Pi0。cuTAMP 的 recovery goal 仍由规则表生成。
3. Skill 是可复用模式，不是单条 seed 的补丁，也不是「强制 q15 触发」这类实验开关。

### 非目标

- 在线每步询问 Codex / 任何 LLM。
- 用 Aspire 式进化搜索一次生成整段任务程序来替代 Pi0。
- 复用当前 `pi0_rolling_cutamp_recovery_eval_jax.py` 的落盘格式做 skill 挖掘。
- 把残差 trigger 与 skill hook 同时作为生效触发源（对照实验除外，见第 8 节）。

---

## 2. 总流程

```text
                    离线（写库）
  新 runner 仿真 ──► pack_pair 或 pack_fail_set ──► Codex actor ──► coordinator
                         │                              │
                         └─ pair.json / fail_set.json   ├─ skill_packs/<pack>/skills/pair/      （可晋升上线）
                                                        └─ skill_packs/<pack>/skills/fail_only/ （草稿库，不进 --enable_skills）
                                                                      │
                    在线（只用 pair 库）                              │
  Pi0 query ──► hook ──► matcher ──► dispatcher ──► cuTAMP 规则 goal ──┘
                     │                   │
                     └─ 未命中：继续 Pi0 ─┘
```

两个目录就是两条库。不要把 fail-only 草稿和 pair 对照稿写进同一个可上线索引。Aspire 用库指导下一次写程序；我们用 pair 库决定何时切、切了跑 cuTAMP。goal 不由 Codex 写。

---

## 3. 目录约定

后续代码放在这些位置，不要把逻辑塞回旧 eval 脚本。

```text
experiments/robot/libero/skill_pipeline/
  schema.py                 # skill YAML/Markdown 字段与校验
  trace_schema.py           # 步级 / recovery 事件 schema
  runner.py                 # 新评测入口（重写落盘）
  hooks.py                  # hook 点注册与调用
  matcher.py                # 谓词求值
  dispatcher.py             # skill_id → backend
  packer.py                 # pack_pair（成败对照）与 pack_fail_set（失败单边）
  coordinator.py            # 入库检查；pair / fail_only 门槛不同
  validate.py               # held-out / 同 init 开关 skill
  backends/                 # 对现有执行桥的薄封装
    keep_closed.py
    ...

skill_packs/<pack>/         # 以 benchmark / mining campaign 隔离 skill 库和 profile adapter
  pack.yaml                 # registry / profile / adapter 入口
  capabilities.yaml         # 当前 pack 允许使用的 profile、hint、executor 参数
  profiles/                 # grasp / grounding / geometry / repair / place 命名 profile
  code/                     # benchmark-specific adapter，不写进主流程
  skills/
    _index.yaml             # online: 仅 pair/ 路径；fail_only: 草稿清单，不加载
    pair/                   # 有验证证据、可晋升上线
      repair/
      recovery_hint/
        grasp/
        grounding/
        geometry/
        place/
    fail_only/              # 失败单边草稿；默认不进 --enable_skills
      ...

docs/agentic_skill_recovery_pipeline.md   # 本文
```

Codex actor 第一版可以是脚本 + 提示词（`scripts/recovery/skill_pipeline/run_codex_actor.py` 与 `prompts/`），不把提示词散写在 runner 里。

当前代码约定是：task-specific skill 不直接改 runner / planner / executor 主流程。普通 mining
只能改 active skill pack 下的 Markdown、profile YAML、pack-local adapter、capability registry
和测试。主流程只保留通用 primitive；引擎可消费的 executor option、place policy、grounding /
geometry primitive 和 descriptor shape 统一登记在
`experiments/robot/libero/tiptop_repro/engine_capabilities.py`。如果一个新 task 需要超出这些
通用能力的动作或几何，应先输出 engineering blocker，而不是把 benchmark 私货写回主流程。

---

## 4. 仿真必须新落盘的信息

旧 runner 的问题：VLA 段几乎没有逐步状态；成功条没有 recovery 事件，对照极不对称；视频降采样且无单独关键帧；`contacts` 整表过大，不适合作为 agent 主输入。

新 runner 每个 episode 写：

```text
<run_dir>/<task>/epXX/
  episode.json          # 成败、seed、task 语言、路径索引
  query_trace.jsonl     # 每次 Pi0 query 一条紧凑记录（主时间轴）
  recovery_trace.jsonl  # 仅 recovery/backend 段的原语事件
  frames/               # 按 query 抽的 agentview（及可选 wrist）静止图
  video.mp4             # 可选，给人看，不是 Codex 主输入
```

### 4.1 `query_trace.jsonl`（每次 Pi0 query 必写）

字段固定，禁止再倾倒整表 contacts。

| 字段 | 说明 |
|---|---|
| `task_id_1based`, `episode_idx`, `seed` | 定位 |
| `query_idx`, `env_step` | 时间轴 |
| `mode` | `vla` 或 `recovery` |
| `ee_xyz`, `ee_quat` | 末端 |
| `gripper_qpos`, `gripper_aperture`, `gripper_cmd` | 开度与命令 |
| `target_name`, `target_xyz` | 当前 task 目标物（仿真可读，但 trigger 谓词默认不依赖 geom 名以外的真值） |
| `holding_status`, `holding_object`, `bilateral`, `object_followed` | 摘要，不要 candidates 全列表 |
| `logvar_gripper_first`, `residual_score` | 仅作分析/对照基线，**不得**作为 skill trigger 的唯一条件 |
| `hook_fired`, `skill_id` | 若本步触发了 skill |

`object_followed` 若本 query 未做抬升探测，写 `null`，不要填 0 假装测过。

### 4.2 `recovery_trace.jsonl`（仅修复段）

每个执行桥原语一条：`close` / `lift_probe` / `trajectory` / `place_*` / `open` / `plan`。必须包含：

- `label`（如 `Pick(...)`）
- `gripper_hold_value`（这段轨迹实际下发的夹爪命令）
- `success`, `error`
- 抬升探测时的 `object_lift_m`, `object_followed`, `confirmed`

`recover()` 进了但没有执行器事件时，仍写一条 `kind=plan`（`execution_source` / MotionGen `failure_reason`），禁止留下空 `recovery_trace.jsonl` 让人以为没进 recover。

这是 repair skill 的主要证据。**写作 rollout 可以没有 recovery**：基线 Pi0、skills 关闭时文件应存在但可以为空。packer 必须带 `recovery_available` / `recovery_event_count`，禁止把空文件当成缺失而拒绝打包。验证阶段打开 skill 后再跑，才会重新产生 recovery 事件。

### 4.3 帧

每个 query 存 `frames/qXXXX_agentview.jpg`。pair 线的 Codex 主输入是 packer 选出的对齐关键帧（接近 / 合爪 / 抬起 / 松爪 / 放置，缺槽则跳过）。fail-only 线改为接近 / 中段 / 停滞 / 结束。整段 mp4 不是主输入。

### 4.4 真值使用边界

仿真可以记录 holding / 物体位姿，供离线归因和验证。**写入 skill 的 `trigger` 只能使用在线也能算的量**：开度、EE、label、是否 object_followed、短窗口是否无进展。禁止把「整表接触」或 body 真值写进在线谓词。

---

## 5. Skill 内容与应用方式

Aspire 的 skill 是给 coding agent 读的手册，真正执行的是 `fix_code.py`。我们的 skill 要同时服务：

- 离线 Codex（in-context）
- 在线 matcher / dispatcher（可计算谓词 + backend 名）

### 5.1 文件格式

`skill_packs/<pack>/skills/pair/repair/example.md`（YAML front matter + 正文）：

```yaml
---
id: hold_then_pick_traj_opens
name: 抓住后重规划开爪
kind: repair          # trigger | repair | diagnostics
track: pair           # pair | fail_only；缺省按路径推断，fail_only 不得上线
hook: before_trajectory_step
priority: 100         # 同 hook 上数字大者优先，一次只派发一个
when_to_apply: 合爪后物体已跟随抬起，下一段却是空手 Pick/MoveFree
when_not_to_apply: 第一次合爪后物体 z 未跟随（空抓走另一条 skill）
failure_signature:
  - object_followed after close
  - next label matches pick( or movefree
recovery_point: 第一次确认抓住之后、第二条 Pick 轨迹开始之前
trigger:
  all:
    - object_followed_lift: true
    - label_matches: "pick\\(|movefree"
    - aperture_gt: 0.02
backend: keep_gripper_closed
evidence:
  tasks: []
  episodes: []
---
```

正文写给人看的解释、anti-patterns。缺谓词时写在 `findings.md` 的 `## Proposed predicates`，不要写进 `trigger`。`diagnostics` 类只给离线 actor 读，不注册 hook。

### 5.2 入库规则（coordinator）

两条线共用 schema 禁令（谓词白名单、禁止 query 号 / 绝对坐标 / contacts），入学门槛不同。

**pair（`skill_packs/<pack>/skills/pair/`）必须同时满足：**

1. `trigger` 只用第 4.4 节允许的特征。
2. 不是单条 seed 的绝对坐标或硬编码 query 号。
3. 写作时用过的 episode 不得当作唯一证据；至少还要在 held-out 失败上对得上（见第 8 节）。
4. `backend` 必须已存在。主线是 `cutamp_recover`；`keep_gripper_closed` 仅用于执行桥内夹爪修补。
5. 成功条不应长期命中同一 trigger（允许极短误触发，阈值在 `validate.py`）。

**fail_only（`skills/fail_only/`）：**

1. 允许只有失败写作 episode（这是这条线的定义）。
2. `ok=true` 只表示可以进草稿库，**永远** `online_ready=false`。
3. `--enable_skills` 只读当前 skill pack 的 `_index.yaml` 的 `online:`。`fail_only:` 清单给人看，不加载。
4. 晋升到 pair/online 仍要走第 8 节：held-out 失败召回、同 init 开/关变好、成功条不回退（若后来有成功条）。

太贴单 task 的细节留在该 task 的 `findings.md`。cuTAMP 的 `Holding` / `On` / `Inside` goal 仍由规则表生成，不要写进 skill。

---

## 6. 各组件实现逻辑

### 6.1 新 runner

- 保留 Pi0 推理、LIBERO env、执行桥，**换掉落盘与触发入口**。
- 每个 Pi0 query 之后调用 `hooks.emit("after_pi0_query", state)`。
- 执行桥合爪+抬升探测之后 `after_gripper_close`。
- 下一段关节/笛卡尔轨迹真正下发前 `before_trajectory_step`（可改 `gripper_hold_value` 或跳过该段）。
- recovery / backend 结束 `after_recovery_attempt`。
- 默认 **关闭** 残差 trigger 与 `force_recovery_query`。需要对照基线时用 CLI 显式打开，且不得与 skill hook 同时作为生效源。

### 6.2 Rollout packer

输入：第 4 节目录。两个入口：

- `pack_pair` → `pair.json`，`track: pair`。成功一条 + 失败集合；对齐槽为接近 / 合爪 / 抬起 / 松爪 / 放置，缺则跳过。
- `pack_fail_set` → `fail_set.json`，`track: fail_only`。只打包失败；对齐槽为接近 / 中段 / 停滞 / 结束。`success` 为 `null`。

两条都写出每条失败的 `recovery_available` 与 `recovery_event_count`。空 `recovery_trace.jsonl` 合法，不要内联整文件。

### 6.3 Codex actor（仅离线）

输入：active skill pack 的 `skills/`、profiles、capabilities（同时给 pair 与 fail_only 上下文，但稿子必须标 `track`）、一份 pack JSON、关键帧。
输出：`draft.md` + `findings.md`。pair 线解释成败分叉；fail-only 线解释共同失败模式，并写明下一步 held-out / 同 init。
禁止：把整段视频当唯一依据；输出无法求值的自然语言 trigger；把未入白名单的谓词写进 `trigger`；在 skill 里写 cuTAMP `recovery_type` / `goal_atoms`。

如果输出的是 bundle，actor 必须先定位失败层：

- repair 只写触发和 recovery-entry profile；
- grasp 写 `grasp_profile`，对象采样逻辑放 pack-local `code/grasp_profiles.py`；
- grounding 写 `grounding_profile`，语义绑定逻辑放 pack-local `code/grounding_profiles.py`；
- geometry 写 `geometry_profile`，region 测量 / proxy 逻辑放 pack-local `code/geometry_profiles.py`；
- place 写 `place_profile`，hover / align / release 策略放 pack-local `code/place_policies.py`；
- diagnostics 只能先 draft / shadow，不得同轮变成 online predicate。

带 Python / profile / registry 修改的草稿必须写 `code_patch_manifest.yaml`，并接受 code
admission 的改动边界和能力注册检查。

缺谓词时只允许出现在 findings 的 `## Proposed predicates`。人审后改 `schema.py`、`matcher.py` 和本节，并补测试，下一轮 actor 才能使用。

离线挖库按 **task 外环**（详见 `docs/skill_pipeline_mining_loop.md`），不要每个 task 无条件写一份：

```text
对每个 task:
  库空 → Codex 写 skill（默认每 task 最多 5 次）
  库非空 → 先 --enable_mining_skills 同 init 跑 5 条
  成功率 ≥ 3/5、不差于 skills-off 基线、剩余失败都切过 skill
      → passed，下一 task，不必再写
  否则 Codex 再写并再跑 5 条
  5 次仍不够 → write_budget_exhausted 保底放行（fail_only，sr_passed=false），下一 task 仍要自己跑 5 条
```

ingest 前仍用写作失败上的 trigger 重放做廉价门闩。真正过关看同 init 成功率。同 init 验证必须带真 cuTAMP/cuRobo（`mining_validation_command` 自带，不要只开 `--enable_mining_skills`）。没有 cuRobo 关节轨迹时不得走 optimized 插值（`--require_real_cutamp_executable_plan`）。`--enable_skills` 不得加载 fail_only。

### 6.4 Coordinator

第一版用规则校验 schema + 第 5.2 节清单。pair 过 8.3 后，当前 skill pack 的 `skills/_index.yaml` 的 `online:` 增加 `pair/...` 路径。fail_only 只写入 `fail_only:` 或对应目录，不进 `online:`。不要在第一版再套一层「coordinator agent」。

### 6.5 Hook 与 matcher

Hook 是运行时事件总线，不是 Aspire 那种「读完 SKILL.md 再写程序」。

固定钩子：

| hook | 何时 | 典型用途 |
|---|---|---|
| `after_pi0_query` | 每个 action chunk 边界 | 卡住、无进展 |
| `after_gripper_close` | 合爪并完成抬升探测后 | 空抓 / 真抓 |
| `before_trajectory_step` | 下一段轨迹下发前 | 禁止 Pick 开爪 |
| `after_recovery_attempt` | 一段 backend 结束 | 避免失败后立刻再开一条空手 Pick |

Matcher：只求值声明了该 hook 的 skill；按 `priority` 降序；**一次只命中一条**。谓词集合第一版固定为：`object_followed_lift`、`label_matches`、`aperture_gt` / `aperture_lt`、`holding_status_is`、`ee_stalled`（短窗口位移阈值）。新增谓词必须改 schema、matcher 与本文，并补测试；禁止 skill 文件里写任意 Python，也禁止 Codex 在 `trigger` 里自创谓词名。

### 6.6 Dispatcher 与 backends

`backend` 是函数名，实现放在 `backends/`，内部只调用现有 `libero_tiptop_executor` / controller，不在 backend 里直接 `env.step` 拼 7D。
返回后 runner 清空 Pi0 action chunk，从当前 obs 继续。

---

## 7. 在线时序（无 Codex）

```text
for env_step:
  if 需要新的 Pi0 chunk:
      Pi0.infer()
      写 query_trace
      hook after_pi0_query
      若命中 → dispatcher → 写 recovery_trace → continue
  否则执行当前 chunk 一步

执行桥内部:
  close + lift_probe → hook after_gripper_close
  每段 trajectory 前 → hook before_trajectory_step
      命中 keep_gripper_closed → 覆盖 gripper_hold_value
      命中 skip → 不执行该段
  段结束 → hook after_recovery_attempt
```

---

## 8. 如何验证 skill 有效

写作用的 episode 与打分用的 episode 必须切开。写作可以没有 recovery、可以没有成功条；验证打开 skill 后应重新跑仿真，那时才会有 recovery。

### 8.1 触发是否找对（可先不跑新仿真，但必须用新日志）

**pair：** 在 held-out 成功 / 失败条上：

- 失败条是否在 `recovery_point` 附近命中（召回）
- 成功条全程不应命中，或误触发极短（精确）
- 命中时刻不得晚于不可逆点（例如第二条 Pick 开爪之前）

**fail_only：** 没有成功对照时，先看 held-out **失败**召回与跨 episode 一致性；误触发检查推迟到出现成功条或同 init 开 skill 之后。草稿可以进 `skills/fail_only/`，不能因此宣称 online_ready。

### 8.2 修了是否有用（必须跑仿真）

1. **同 init 开关**：同一 `task + episode_idx + seed`，关 skill vs 开 skill。看任务成功率与该 `failure_signature` 是否还出现。这是主因果证据，也是 fail_only 晋升的必要条件。
2. **成功条回归**：打开 skill 后，原先成功的 held-out 条不得明显回退（有成功条时）。
3. **跨 task（入库加分项）**：未写入 `evidence` 的同类任务上，同类失败也能命中且变好，才算 skill 而不是 task 补丁。

从分叉点 snapshot 恢复是后续增强，不是第一版必须。

### 8.3 通过线（coordinator 硬条件）

pair 同时满足 8.1 的精确/召回门槛、8.2 的同 init 改善、成功条不回退，且 backend 已实现，才能把草稿移入 active skill pack 的 `skills/pair/` 并写入 `online:`。
fail_only 不得写入 `online:`。「Codex 说得通」不能上线。

默认门槛在 `validate.py` 实现时给出常数，并在 PR 说明里写清；改门槛必须改测试，不要在 skill 文件里私自放宽。

---

## 9. 实现顺序

1. `trace_schema.py` + `schema.py` + 空 `skill_packs/<pack>/skills/_index.yaml`
2. 新 `runner.py`：只跑 Pi0 + 新落盘，先不接 skill
3. `hooks.py` / `matcher.py` / `dispatcher.py` + 第一个 backend（`keep_gripper_closed`，对应 T56 抓住后 Pick 开爪）
4. `packer.py` + Codex actor 提示词与输出校验（含 fail-only pack）
5. `validate.py`：held-out 触发统计 + 同 init 开关
6. 用新 runner 按 `docs/skill_pipeline_mining_loop.md` 挖 `fail_only` 草稿（同 init 3/5 过关，默认每 task 最多写 5 次，五次不够标记 `write_budget_exhausted` 并继续）；pair 线用 spatial/goal 对照把工具跑通

不要在旧 `pi0_rolling_cutamp_recovery_eval_jax.py` 上打补丁充当新 runner。对照旧 trigger 时，另开 CLI 跑旧脚本，结果不要混进 skill 的 `evidence`。

---

## 10. 与现有执行桥的关系

cuTAMP / cuRobo / `libero_tiptop_executor.py` 仍是 repair backend 的实现位置。Skill 不复制规划器，也不写 recovery goal。命中后 `cutamp_recover` 进入执行桥，goal 由 `build_recovery_goal_candidates()` 规则表生成。`llm_recovery_goals.py` 默认关闭，不要接到在线环。若 skill 要求「抓住后禁止 Pick 开爪」，改动点是 `_gripper_hold_value`（`keep_gripper_closed`），而不是让 Codex 在线改代码。
