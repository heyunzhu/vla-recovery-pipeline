# 类 CI/CD 门禁与新任务生成方式

本文记录当前 recovery skill pipeline 中两个约定：

1. 类 CI/CD 系统如何阻止 Codex 在 mining 中写歪 skill；
2. 新任务 benchmark 如何从 LIBERO-90 受控生成。

## 1. 类 CI/CD 系统

这里的 CI/CD 不是完整软件工程流水线，而是 skill 入库前的三道门禁。目标是让 Codex 可以参与离线 mining，但不能把过宽、错层、不可验证的 skill 直接放进 online skill 库。

完整入口可以理解为：

```text
Codex 写 fail_only skill / bundle
→ 静态检查
→ 离线触发扫描
→ 当前任务少量 rollout 验证
→ 达标后才进入 online skill index
```

### 1.1 静态检查层

静态检查不跑仿真，只检查 skill 文件本身是否合格。

主要检查内容：

- skill markdown frontmatter 是否能解析；
- `id`、`kind`、`scope`、`track`、`hook`、`trigger`、`recovery_hints` 等字段是否合法；
- repair skill 是否包含明确失败证据，而不是只根据“夹爪靠近目标”“手为空”“正在接近目标”等正常 pick 过程触发；
- grasp skill 是否只负责抓取，不把 grounding、geometry、place 逻辑混进来；
- grasp profile 是否存在、能否采样、候选数量和夹爪宽度是否合理；
- skill 使用的底层能力是否在 capability registry 中注册，例如 grasp profile、geometry hint、grounding hint、executor option、place policy 等。

这一层回答的问题是：**这个 skill 在结构和职责上是不是靠谱。**

如果静态检查失败，skill 不应进入 rollout 验证，更不能进入 online。

### 1.2 离线触发扫描

离线触发扫描不重跑环境，而是读取历史 rollout trace，重放每个 query 的状态，检查新 skill 会在什么地方匹配或触发。

输入通常来自过去评测保存的：

- `episode.json`
- `query_trace.jsonl`
- `recovery_trace.jsonl`
- skill invocation 记录
- 规划失败摘要

主要检查内容：

- 新 skill 会匹配哪些 episode；
- 会在第几个 query 触发；
- 是否在成功 episode 上误触发；
- 是否过早触发，例如首次触发早于 query 5；
- repair skill 是否能覆盖失败 episode；
- recovery hint skill 是否匹配到合理对象和场景。

这一层回答的问题是：**这个 skill 会不会太宽、太敏感，或者破坏已有成功经验。**

离线触发扫描的好处是便宜。它不能证明 skill 一定有效，但可以快速筛掉明显危险的 skill。

### 1.3 少量 rollout 重跑

前两层通过后，才对当前 mining task 做少量真实 rollout 验证。

常用设置是同初始化、同 seed、每个 task 跑 5 条 episode，当前经验阈值是：

```text
success >= 3/5
```

这一层主要检查：

- skill 是否真的提升当前 task 成功率；
- recovery 是否在合理时机触发；
- cuTAMP 是否能产出可执行解；
- pick / place / release 是否完整执行；
- 是否产生明显副作用。

如果少量 rollout 失败，Codex 最多修改有限轮次。若问题明显属于 planner、executor、共享 geometry、模型能力等非 skill 层问题，应输出 blocker / engineering action，而不是继续硬写 skill。

这一层回答的问题是：**这个 skill 是否真的能救当前任务。**

## 2. 新任务生成方式

当前新任务不是由 LLM 随机编写，而是从 LIBERO-90 原始 BDDL 任务中受控派生。核心思想是：保留原始场景和物体布局，只改写 pick object、place target、goal predicate 和语言描述。

主要代码入口：

```text
scripts/recovery/skill_pipeline/generate_libero_generated_benchmark.py
experiments/robot/libero/skill_pipeline/generated_benchmark.py
scripts/recovery/skill_pipeline/classify_generated_benchmark_tasks.py
```

当前冻结 benchmark 目录：

```text
benchmarks/libero90_generated_v1_envfiltered_304
```

### 2.1 读取原始 LIBERO-90 场景

生成器先读取 `libero_90` 的 90 个原始 BDDL task，并解析：

- 任务语言；
- objects；
- fixtures；
- `obj_of_interest`；
- 原始 goal atoms；
- BDDL 中已有 region。

这些原始任务被当成 scene template。也就是说，桌面布局、物体初始位置、柜子、盘子、篮子、笔筒等实体都来自原始 LIBERO 场景。

### 2.2 用固定模板改写 goal

当前 v1 启用三类稳定模板：

| 模板 | 含义 |
| --- | --- |
| `pick_place_on_surface` | 在同一场景中选可移动物体和 surface，改写为 `pick up X and place it on Y` |
| `put_inside_container` | 在同一场景中选可移动物体和 container，改写为 `pick up X and place it in Y` |
| `caddy_compartment` | 对 desk caddy 生成 front / back / left / right compartment 放置任务 |

生成时会改写 BDDL 的：

- `:language`
- `:obj_of_interest`
- `:goal`

对于 caddy compartment 这类任务，还会补 synthetic region，例如：

```text
desk_caddy_1_front_contain_region
desk_caddy_1_left_contain_region
```

但生成器不会重新随机摆放物体，也不会生成新 mesh。

### 2.3 去重与稳定 ID

每个生成任务用以下信息计算稳定 hash：

```text
source suite + source task id + template + object + target
```

因此生成出的 task id 是可复现的，例如：

```text
libero_90_gen_t084_caddy_compartment_dcf77fac
```

同样配置重复生成，ID 不会变化。

### 2.4 环境加载过滤

生成出的 BDDL 候选不一定都能被 LIBERO 正常加载，所以会在评测环境里做 env-load filter：

1. 临时写出 candidate BDDL；
2. 用 `OffScreenRenderEnv` 加载；
3. `reset()`；
4. 调 `check_success()`；
5. 能正常加载的保留，失败的丢弃。

当前冻结版本结果：

```text
候选任务: 362
通过过滤: 304
过滤失败: 58
```

这一步只保证任务能加载，不保证 VLA 或 recovery 一定能完成。

### 2.5 固定 split 和行为分类

过滤后得到 304 个任务，并固定划分：

```text
smoke: 3
train: 256
validation: 45
```

之后分类脚本再按“放什么、放到哪里”打行为标签，例如：

```text
surface/plate/black_bowl
surface/plate/flat_box
inside/basket/can_or_bottle
inside/basket/carton_bottle
inside/basket/flat_box
inside/wooden_tray/can_or_bottle
inside/wooden_tray/flat_box
caddy_compartment/book
```

这些分类不改变 BDDL，只用于后续 mining 抽样、训练/测试划分和结果统计。

### 2.6 当前用途

这些 generated tasks 的用途不是替代官方 LIBERO benchmark，而是作为 skill mining benchmark：

- 提供比 LIBERO-90 更多的任务组合；
- 让相似 failure mode 在多个场景中重复出现；
- 支持按类别抽样，例如每类抽若干任务做 mining；
- 保留 validation split，用来检查新 skill 是否泛化，而不是只对 mining task 过拟合。

简言之：**新 task 是从真实 LIBERO 场景中受控改 goal 得到的可复现任务集合，用来给 recovery skill pipeline 提供更多可挖、可测、可留出的任务。**
