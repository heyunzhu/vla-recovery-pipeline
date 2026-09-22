# object / goal 两轴现状 + 评测可复现性修复（2026-09-21）

本文是阶段性状态文档：记录**评测口径的重大修复**（逐集播种 + XLA 确定性）、
**object 两轴的确定性基线**、**纸盒线的收口**、**cream cheese 触发器的进展**，
以及 **goal 两套的排查结论**与待办。

---

## 0. 一句话总结

- **评测现在是可复现的**：同一 seed 在任意上下文下位级一致（两臂 5/5 集哈希全同）；
  修复前的"±2–3 集"在线 A/B 结论**全部作废**（大效应如纸盒仍然成立）。
- **object 两轴确定性基线（1000 集，seeds 1–50）**：`object_task` **439/500 = 0.878**、
  `object_swap` **458/500 = 0.916**，与修复前旧表几乎逐集复现（+3 / +5）。
- **纸盒线已收口**：新 profile 让 milk/orange juice 从 **0/200 → 197/200**（已提交 `8e7b0bf`）。
- **cream cheese 触发器**：v1 在线 **+1（零回归）**，瓶颈是"触发太晚"（首触发 q25–42）；
  我离线做出 v2（首触发**中位 q5**、覆盖更广、成功集零误触），在线 A/B 待补完。
- **goal 两套**：`goal_task` 部分完成 ~0.43（与 09-19 旧表同型）；**`goal_swap` ~0.03**，
  原因是当前包的 skill 未覆盖它的扰动指令集（触发率 3.6%），不是"包拿错了"。
  另发现我此前**硬写了 `--task_language_source bddl`**，与 runner 的默认协议（`_swap` 用 filename）不符，已改正重跑。

---

## 1. 评测可复现性：问题、根因、修复、验证

### 1.1 问题（实测）

同一套包、同一 task、同一批 seeds（51–65）跑两遍：**5/13 集结果翻转**，
且翻转形态固定——要么"q5 触发器命中→秒救成功"，要么"整集不触发→跑满预算失败"。

### 1.2 根因

runner 只在**进程启动**时 `np.random.seed(90)` 一次，每集只做 `env.seed(episode_seed)`；
而策略（OpenPI/JAX）的动作采样 RNG **从未逐集播种**：OpenPI 用 `jax.random.key(0)`
并在每次 `infer` 时 split，`reset()` 是 no-op → 同一集的噪声取决于**进程边界**与**前面跑过的 infer 次数**。

### 1.3 修复（worktree `eval-repro-seed-fix-20260920`）

- `13a9871` `fix(eval): seed OpenPI policy per episode`：把 `episode_seed` 透传到 in-process /
  subprocess 两个策略适配器；每集 reset 时同步播种 Python/NumPy，并把策略 RNG 替换为
  `jax.random.key(episode_seed)`（保留 PyTorch 分支）。
- `a6b4b46` `fix(eval): hash typed JAX PRNG keys`：JAX 新版 typed PRNG key 不能直接转 numpy，
  改为对 `jax.random.key_data` 取哈希。
- 每查询落盘复现性元数据：`policy_rng_seed`、`policy_infer_index`、`policy_rng_state_hash`、
  `policy_sample_key_hash`、`observation_agent_hash`、`observation_wrist_hash`、`action_chunk_hash`。

### 1.4 门（三臂 × 15 集）

| 臂 | 形式 | 结果 |
| --- | --- | --- |
| `continuous_a` | 单进程 15 集 | 7/15 |
| `continuous_b` | 同臂重跑 | 6/15 |
| `split_5_plus_10` | 5+10 模拟抢占续跑 | 6/15 |

逐 seed 比对：**14/15 结果一致、1 集不同**。逐字段拆解（query 0）：

| 字段 | 三臂 |
| --- | --- |
| `policy_rng_seed` / `policy_rng_state_hash` / `policy_sample_key_hash` | **一致** ✓ |
| `observation_agent_hash` / `observation_wrist_hash` | **一致** ✓ |
| **`action_chunk_hash`** | **不一致 ✗（第 0 行即分叉）** |

→ 残余不确定性在 **JAX/XLA 的 GPU kernel 层**（autotune 选算法、非确定性归约、TF32 等），
不在播种代码里。

### 1.5 补丁：确定性开关（已验证）

```
XLA_FLAGS="--xla_gpu_deterministic_ops=true --xla_gpu_autotune_level=0"
NVIDIA_TF32_OVERRIDE=0
```

两臂 × 5 集（task t01，seeds 51–55）：**逐 seed 位级一致（含 `action_chunk_hash`）** ✓。

**副作用（重要）**：确定性开关**改变数值**（关 TF32 + 换 kernel）→ 成绩会变；
因此所有基线必须在**同一套开关下**重测（本文第 2 节即是）。

---

## 2. object 两轴：确定性基线（1000 集，seeds 1–50）

配置：worktree `a6b4b46` + 上述确定性开关；pack = **32 条**（`skills/_index.yaml` md5
`b32e5a1024daa74e3fc771a726d2eeb9`）；每 task 单进程、可断点续跑。

### 2.1 合计

| suite | 新基线 | 旧表（纸盒修复后） | 差 |
| --- | ---: | ---: | ---: |
| `libero_object_task` | **439/500 = 0.878** | 436/500 = 0.872 | +3 |
| `libero_object_swap` | **458/500 = 0.916** | 453/500 = 0.906 | +5 |
| 合计 | **897/1000 = 0.897** | 889/1000 = 0.889 | +8 |

### 2.2 逐 task

| task | 物体 | task 轴 | swap 轴 |
| ---: | --- | ---: | ---: |
| t01 | alphabet soup / **cream cheese** | 50/50 = 1.00 | **42/50 = 0.84** |
| t02 | **cream cheese** / alphabet soup | **25/50 = 0.50** | 50/50 = 1.00 |
| t03 | **tomato sauce** / salad dressing | **42/50 = 0.84** | 50/50 = 1.00 |
| t04 | ketchup / bbq sauce | 50/50 = 1.00 | 49/50 = 0.98 |
| t05 | milk（纸盒） / ketchup | 50/50 = 1.00 | 50/50 = 1.00 |
| t06 | bbq sauce / tomato sauce | 50/50 = 1.00 | 46/50 = 0.92 |
| t07 | orange juice（纸盒） / **butter** | 50/50 = 1.00 | **30/50 = 0.60** |
| t08 | **butter** / milk（纸盒） | **24/50 = 0.48** | 50/50 = 1.00 |
| t09 | salad dressing / chocolate pudding | 49/50 = 0.98 | 41/50 = 0.82 |
| t10 | chocolate pudding / orange juice（纸盒） | 49/50 = 0.98 | 50/50 = 1.00 |

（左列 = task 轴，右列 = swap 轴；两轴 task 顺序不同）

### 2.3 弱点与失败结构（逐集归因已完成）

| 弱点 | 结果 | 失败结构 |
| --- | ---: | --- |
| task t01 cream cheese | 25/50 | 25 集失败中 **24 集零触发**（`recovery_calls=0`、跑满 56 query）；成功的 25 集全部由既有 q5 触发器在 6 个 query 内解决 |
| task t08 butter | 24/50 | 26 集失败**全部触发过**（rec≥1）；抬升探针 `followed=False`、开度中位 **0.0013 m（夹穿）**、提起 ≈0 |
| task t03 tomato sauce | 42/50 | 6 集零触发 + 2 集触发未果 |
| swap t02 cream cheese | 42/50 | 12 集失败 = 5 零触发 + **4 集 Pick 追踪停滞**（`optimized_motion_tracking_stalled`）+ **3 集 Place 预算耗尽**（`place_hover` / `place_hover_xy_correct` 报 `trajectory_tracking_budget_exhausted`）|
| swap t07 butter | 30/50 | 执行/抓取层（同 task t08） |
| swap t09 chocolate pudding | 41/50 | 含 `no_feasible` 等规划不可行 |

---

## 3. 纸盒线（已收口）

- 旧病：上一轮的 `grasp_object_basket_tall_carton_topdown_deep` 把纸盒指向小方盒 profile
  → cuTAMP 规划几乎全不可行（`real_cutamp_no_feasible_goal` 398 次），0/200。
- 处理：撤回该 hint（`fee3177`），并为直立纸盒新写 profile
  **`carton_upright_body_side_v1`**（抓盒身、闭合轴**平行于棱**、高度 80% = 离桌 10.50 cm）。
- 高度扫描（dev seeds 51–65，每臂 60 集）：70% → 7/60、75% → 52/60、**80% → 60/60**、通用对照 18/40。
- 测试集验证（seeds 1–50，4 个纸盒 task × 50 集）：**197/200 = 0.985**（对照 105/200）；
  抬升探针 200/200 保持、开度中位 0.0270 m、`place_lift_too_low` 0 次、`no_feasible` 398 → 4。
- 提交：`8e7b0bf`（profile + hint + capabilities + index）、`0a016f6`（文档补记）；确定性基线下四个纸盒 task 全部 50/50 复现 ✓。

---

## 4. cream cheese 触发器（进行中）

### 4.1 靶子

task t01 的 **24 个零触发失败**（见 2.3）。离线语料（dev 51–65）里同类集数量与之同量级。

### 4.2 v1（codex，`object_basket_cream_cheese_far_target_ee_stall`）

`ee_stalled{window:6, max_disp_m:0.03}` + 手空 + 夹爪张开 + 目标远且静止（priority 75）。

- 离线：命中 58 个失败集、**0 成功集误触**、无 q<5 早触（我用本地语料独立复算一致）。
- 在线（确定性，dev 51–65，task t01 + swap t02）：B0 **6/15** → B1 **7/15**（**+1，零回归**）；
  它在**原本零触发的 9 集里 9/9 全部触发**，但首触发落在 q25–42 → **只转化 1 集**；
  swap 轴 12/15 → 13/15（该轴只触发 1 次）。
- 结论：**覆盖没问题，时机太晚**。

### 4.3 v2（本轮新增，`object_basket_cream_cheese_early_no_approach`）

去掉停滞门，改为"手空 + 夹爪张开 + 非目标意图 + 最近可抓物非目标 + **目标远（EE>0.22 m）
且在未来窗口仍远（>0.20 m）+ 目标静止**"，在**第一个满足的 query** 就接管。

离线对比（本地 dev 语料，同一扫描器）：

| 变体 | task 覆盖 | task 首触发 q | swap 覆盖 | swap 首触发 q | 成功集误触 |
| --- | ---: | --- | ---: | --- | ---: |
| v1（stall） | 29 | 中位 **27** | 29 | 中位 27 | 0 |
| 松停滞 4 帧/8 cm | 13 | 中位 26 | 28 | 中位 24 | 0 |
| pick-status 类 | 8 | 5 | 28 | 1 | 0 |
| **v2（早接管）** | **30** | **中位 5** | **29** | 中位 0–2 | **0** |

→ v2 同时拿到"覆盖更广 + 早 20 个 query + 零误触"（q5 接管时还剩 ~50 query 预算）。

### 4.4 状态

两个候选已入库为 **drafts**（不激活，`0c398d7`）。v2 的在线 A/B（B0 32 条 vs B2 33 条
= `8384a0ce…`）在 pod 抢占时中断：B0 task 轴已完成（6/15，与上一轮逐集一致 → 确定性再验证 ✓），
B2 两臂待补跑（幂等驱动，一处命令即可续）。

---

## 5. goal 两套（排查结论）

用**当前 pack** 重跑（用户要求），seeds 1–50：

| suite | 进度 | 成功率 | 逐 task |
| --- | --- | ---: | --- |
| `libero_goal_task` | 316 集 | **138/310 ≈ 0.445** | t03 0.88 / t07 0.86 / t08 0.94 / t09 0.52 正常；t01 0.02、t02 0、t06 0.12、t10 0 近零 |
| `libero_goal_swap` | 307 集 | **10/304 ≈ 0.033** | 只有 t04 7/50、t07 3/4，其余六个 task **0/50** |

### 5.1 排查（三条）

1. **"包拿错了"不成立**：goal 包的 23 条 skill 与 object 包内同名文件**逐字节相同**，
   `profiles/{repair,place,grounding,geometry}.yaml`、`diagnostics/registry.yaml` 亦相同
   → **object 包是 goal 包的严格超集**。所谓 0.336 是 09-19 那次 **`goal_task`**（165/500）。
2. **goal_swap 的 3% 是"未开发"**：包内 skill 的 `applies_to` 按指令文本匹配，
   而 goal_swap 是被扰动过的另一套指令 → 实测**仅 3.6% 的集有任意触发器命中**（296/307 零触发）。
3. **确实存在一个设置问题（我已改正）**：runner 的协议是 `*_task → bddl/bddl`、
   其它（含 `*_swap`）→ `filename/policy`；而我此前对所有 suite **硬写了 `bddl/bddl`**。
   goal_swap 因此被喂了 BDDL 内嵌指令。已改为 `auto` 重跑（新目录 `goal_50seed_auto_20260921`，
   旧的错误设置数据完整保留在 `goal_50seed_20260921` 作对照）。

### 5.2 待办（脚本已就绪）

1. 问 LIBERO 取 `libero_goal_swap` 的 task 列表：比较**文件名语言 vs BDDL 内嵌语言 vs goal 谓词**，
   确定应喂哪个（`ask_libero_goal_swap.sh`）。
2. **裸 VLA 对照**（关 skill，同 suite 同 seeds）：验证"裸 VLA ≈0.2 而我们 0.03"是否成立；
   若成立说明管线在帮倒忙，必须查；若裸 VLA 也≈0，则该 suite 需像 object 轴那样重新挖 skill
   （`goal_swap_bare_vla.sh`）。

---

## 6. 基础设施与踩过的坑（供复现）

- **平台抢占**：pod 优先级 LOW，约为每 10–30 分钟被抢一次；曾出现一次 **STOPPED 约 6 小时**。
  应对：每 task 单进程 + `--episode_index_start` 断点续跑、实例侧自循环、本机 supervisor。
- **本轮修掉的自造 bug**：
  1. `pgrep -c … || echo 0` 会输出两行 "0" → 所有"是否在跑"的判断恒为真（supervisor/queue 空转）；
  2. launcher 用 `$D/<suite>/taskNN` 统计已完成集数，而真实路径是 `$D/<suite>/<exp>/taskNN`
     → 反复重跑已完成的 task（白烧 GPU）；
  3. 包搭建不幂等（父子两次执行时子进程删掉了刚摆好的包）；
  4. `bash -s` 场景下 `$0` 是 `/usr/bin/bash` → nohup 自启动失败；
  5. scp 偶发"报 OK 但文件未落地" → 关键文件必须**落地后核实**（曾导致 B2 臂空跑）；
  6. XLA 确定性开关会改变数值 → 基线与 A/B 必须同开关。
- **产物位置**（实例 `$W=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`）：
  - 确定性基线：`$W/logs/fixed_50seed_20260920/`
  - 可复现性门：`$W/logs/repro_gate_episode_seed_fix_20260920_13a9871/`
  - XLA 探针：`$W/logs/xla_det_probe_20260920/`
  - cream v1 A/B：`$W/logs/cream_stall_det_20260921/`；v2 A/B：`$W/logs/cream_early_ab_20260921/`
  - goal（错误设置）：`$W/logs/goal_50seed_20260921/`；goal（auto）：`$W/logs/goal_50seed_auto_20260921/`
- **仓库**：`feature/recovery-mining-campaign`，本轮推送 `fee3177..0c398d7`（3 个提交）。

---

## 7. 下一步（按优先级）

1. **补完 v2 的在线 A/B**（B0 vs B2，dev 51–65，task t01 + swap t02）→ 决定 cream cheese 触发器
   进包（v2 预期优于 v1 的 +1）。
2. **butter（第 2 项）**：flat-box profile 只有单一深抓点、无高度维度 → 照纸盒方法做
   **高度/深度扫描**（dev 51–65，4 臂 × 2 task），目标是 task t08 与 swap t07。
3. **goal 两步验证**（5.2），据此决定 goal_swap 是"重挖 skill"还是"先修设置"。
4. **swap 轴执行层**：4 集 Pick 追踪停滞 + 3 集 Place 预算耗尽（cream cheese）与
   butter/pudding 的执行问题同源，查控制器参数/轨迹可达性。
