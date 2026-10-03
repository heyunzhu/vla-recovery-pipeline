# 把 LIBERO-Pro 新任务收成 benchmark

日期：2026-10-03

一条任务的做法见 `docs/libero_pro_build_new_tasks_2026-10-03.md`。评测命令见 `docs/libero_pro_run_pack_eval_2026-10-03.md`。benchmark 是一组这样的任务，外加一份清单，用来比较 pack 开和关。3 条、每条 1 集只是 smoke，不是 benchmark。

这次不沿用仓库里的 `benchmarks/libero90_generated_v1_envfiltered_304`，也不沿用 `experiments/robot/libero/skill_pipeline/generated_benchmark.py`。那是更早的一次实验。下面的集合从 LIBERO-Pro 扰动 suite 现拷现改。

## 一条 benchmark 里有什么

一个新 suite，外加一份 `manifest.jsonl`。suite 的登记方式和单条任务相同：BDDL、`.pruned_init`、`libero_suite_task_map.py`、`Benchmark` 子类、`max_steps_for_suite`。suite 名不以 `libero_` 开头，所以不会被 `libero_pro` umbrella 扫进去；以 `_task` 结尾，语言从 BDDL 读。

manifest 每行一个任务，至少有这些字段：

| 字段 | 内容 |
| --- | --- |
| `task_id` | suite 里的任务名，和 BDDL 文件名一致 |
| `edit` | `goal`、`placement`、`geometry` 之一 |
| `source_suite` | 例如 `libero_object_swap` |
| `source_bddl` | 源文件的绝对路径 |
| `source_language` | 源 BDDL 的 `(:language)` |
| `new_language` | 新 BDDL 的 `(:language)`。只有目标轴会变 |
| `bddl_path` | 新 BDDL |
| `init_path` | 新 `.pruned_init` |
| `n_init` | init 条数 |
| `detail` | 这一轴具体改了什么：新目标、region 与平移、或 yaw |

源 suite、源语言和改动细节要留在清单里。评测日志只有新语言和成功与否，事后对不回「相对哪条 LIBERO-Pro 任务改了哪一轴」。

## 怎样凑任务

1. 源任务只从 LIBERO-Pro 扰动 suite 里抽。object pack 这一轮用 `libero_object_swap` 和 `libero_object_task`。同一物理场景只进一次：fixture、物体和 region 范围都相同的 BDDL 算同一场景。
2. 三个轴都要有，数量接近。一条任务只占一个轴，这样成功或失败能归到这一处改动。
3. 先写 BDDL，再采 init，再做 `reset()` / `check_success()` 过滤。过不了的不进清单。
4. 摆放和朝向的 init 条数与源任务对齐后再进正式集合。smoke 里的 8 条只够确认画面变了。
5. 目标轴拷源 init，删掉复位后已经成功的状态。留下的条数写进 `n_init`。

不要从空场景造。不要只改同义词。不要把尺寸写进共享资产。朝向不要拿旋转后看起来一样的物体充数，例如直立罐头转 180°。

## 评测时记什么

两个条件一起跑，任务顺序、`episode_seed_start` 和 init 下标相同。pack 用 `--enable_mining_skills` 和当前 object pack。对照不加载 skill。

这些任务没有「该用的 skill」。清单和汇总里只记：

- 有没有 `recovery_calls`，以及 `skill_id` 是哪一条。
- pack 的成功数相对对照是高、低、还是相同。按 `edit` 分开加总。
- 对照成功而 pack 失败的集数，按 `edit` 分开，记成干扰。

不把「触发了」写成泛化成功，也不把「没触发」写成泛化失败。`force_recovery_query` 不进这张表。它测的是 hint 合并之后 profile 还能不能做完，和这次「skill 有没有自己进门」是另一次运行。

汇总至少有一张表：行是三个 `edit`，列是任务数、episode 数、pack 成功、对照成功、有 recovery 的 episode 数、干扰 episode 数。触发过的 `skill_id` 按任务列在表下，不塞进成功格。

## 和 smoke 的差别

| | smoke | benchmark |
| --- | --- | --- |
| 任务数 | 每个轴 1 条，用来确认链路 | 每个轴多条，场景不重复 |
| init | 摆放/朝向可以先 8 条 | 与源 `.pruned_init` 条数对齐 |
| episode | `--num_trials_per_task 1` | 与要对的那次源评测相同，object 轴 50-seed 就是 50 |
| 结论 | 只说明触发和这一集的成败 | 按轴比较 pack 和对照，并单列干扰 |

2026-10-03 的 `pro_object_axis_20261003_task` 是 smoke：一个源场景、三个轴、摆放和朝向各 8 条 init、每条 1 集。它可以当作清单格式和评测命令的样例，不能当作 benchmark 的成功率。
