# 在 LIBERO-Pro 上建新任务

日期：2026-10-03

源任务必须来自 LIBERO-Pro 会加载的扰动 suite，例如 `libero_object_swap`、`libero_object_task`。`libero_90`、`libero_object`、`libero_goal`、`libero_spatial`、`libero_10` 是底库，umbrella 评测会跳过它们。从底库拷场景，跑出来的 recovery 不能当成 LIBERO-Pro 的结果。

一次只改一个轴：目标、摆放，或朝向/尺寸。三种改法的文件边界见 `docs/skill_pack_task_variant_methods.md`。本文只写怎样把一条 LIBERO-Pro 源任务变成能进仿真、能被 runner 加载的新任务。

当前 object pack 的实例是 `scripts/recovery/skill_pipeline/build_pro_object_axis_tasks.py`。它从 `libero_object_swap` 的「把奶油奶酪放进篮子」造出三条，suite 名 `pro_object_axis_20261003_task`。

## 选源任务

1. 源 BDDL 放在 `LIBERO-PRO/libero/libero/bddl_files/<suite>/`。对应 init 是同名的 `.pruned_init`，在 `init_files/<suite>/`。
2. 源 suite 要在 `libero/libero/benchmark/__init__.py` 的 `libero_suites` 里，并且名字以 `libero_` 开头、不在 runner 的 `LIBERO_PRO_EXCLUDED_SUITES` 中。
3. 物体通过 `(:init)` 里的 `(On instance qualified_region)` 找到 region。region 名经常不带物体名，例如 `other_object_region_0`、`target_object_region`。不要用文件名后缀去猜。
4. 支撑面不只有 `main_table`。object 轴在 `floor` 上，厨房在 `kitchen_table` 上。

`libero_object_task` 会改写文件里的 `(:language)`，文件名仍是原来的物体。读语言以 BDDL 为准。

## 写到哪里

新 BDDL 和 init 放进新目录，不写回源 suite，不改 `assets/` 里的共享网格，不改 `profiles/*.yaml`。

```text
bddl_files/<new_suite>/<task_name>.bddl
init_files/<new_suite>/<task_name>.pruned_init
```

`<new_suite>` 不要以 `libero_` 开头。runner 的 umbrella 会把所有以 `libero_` 开头、且不在排除表里的 suite 扫进去，任务序号会跟着变。名字要以 `_task` 结尾，这样 `--task_language_source auto` 会读 BDDL 里的 `(:language)`，而不是文件名。文件名上的 `shift`、`yaw` 因此不会被当成指令。

实例：`pro_object_axis_20261003_task`。

## 三种改法里仿真真正吃到的部分

目标。一起改 `(:goal)`、`(:language)`、`(:obj_of_interest)`。新目标必须是场景里已经有的物体或 region。谓词沿用这条任务能表达的关系，篮子用 `In`，桌面物体用 `On`。区域和 init 不动。源 `.pruned_init` 可以拷过来，但要逐条 `set_init_state` 再 `check_success()`，已经成功的状态丢掉。

摆放。只改被操作物体所在 region 的 `(:ranges)`。新范围留在原来的支撑面上，不要和别的 region 重叠，也不要移出支撑面。然后用改过的 BDDL 重新 `reset()`，存成这条任务自己的 `.pruned_init`。沿用源 init 时，物体还在旧位置。

朝向。object 轴的 region 经常没有 `(:yaw_rotation)`，要插进这个 region，不要改共享 xml。罐头转 180° 从机械臂视角几乎看不出来；盒子、杯子把手、锅柄转 90° 才看得出来。插好后再重采 init。只改 BDDL、沿用旧 init，朝向不会变。改尺寸时复制一份任务私有资产再改包围盒，不要改 LIBERO 的共享 xml。这次奶油奶酪实例只改了 yaw，没有改尺寸。

改 region 时按括号配平替换整段 `(:ranges ...)` 或 `(:yaw_rotation ...)`。非贪婪正则会少吃掉一层右括号，改后的文件仿真器读不进去。

## 收下这条任务之前

用 run-local 配置，不要改 `~/.libero/config.yaml`：

```bash
export LIBERO_CONFIG_PATH=/mnt/nas/gezuhao/xinghanbo/libero_config_pro
export PYTHONPATH=/mnt/nas/gezuhao/xinghanbo/LIBERO-PRO
export MUJOCO_GL=egl
export PYOPENGL_PLATFORM=egl
```

解释器是 `/mnt/nas/gezuhao/xinghanbo/envs/openpi_jax_py311/bin/python`。这个环境没有把 libero 装成包，要靠上面的 `PYTHONPATH`。

对每条新 BDDL：

1. `OffScreenRenderEnv` 能构造，`reset()` 能返回。
2. `check_success()` 在复位之后是假。目标任务对拷来的每一条 init 都查；摆放和朝向对新采的每一条都查。
3. 括号数量平衡，`bddl.parsing.scan_tokens` 能过。
4. 摆放任务上，被移动物体的平面位置相对源 init 有可见位移。朝向任务上，位置应留在源 region 附近，转的是姿态。

init 用 `torch.save` 存成 `float64` 的二维数组，和源 `.pruned_init` 一样。源文件一般是 50 条。摆放和朝向可以先采 8 条，正式 benchmark 再加到和源任务相同的条数。

## 登记成 runner 能打开的 suite

三处都要加，缺一处 runner 找不到任务，或者找到了却在步数上抛 `KeyError`：

1. `libero/libero/benchmark/libero_suite_task_map.py` 里增加 `"<new_suite>": ["task_name", ...]`。
2. `libero/libero/benchmark/__init__.py` 的 `libero_suites` 加上同名字符串，并注册一个 `Benchmark` 子类，`self.name` 等于这个字符串。
3. `experiments/robot/libero/skill_pipeline/runner.py` 的 `max_steps_for_suite` 给这个名字一个步数。object 轴用 `libero_object` 的 280。名字不以 `libero_` 开头时，现有分支不会自动给步数。

`task_maps` 里的 `language` 来自文件名。真正发给策略和 recovery 的句子在评测时由 `apply_language_sources` 从 BDDL 读出，前提是 suite 名以 `_task` 结尾，或者显式传 `--task_language_source bddl --engine_language_source bddl`。

## 这次三条实例

源文件：`libero_object_swap/pick_up_the_cream_cheese_and_place_it_in_the_basket.bddl`。

| 任务 | 轴 | 实际改动 |
| --- | --- | --- |
| `pick_the_alphabet_soup_and_place_it_in_the_basket` | 目标 | 成功条件改成字母汤进入篮子，50 条源 init 都还没成功 |
| `pick_the_cream_cheese_and_place_it_in_the_basket_shift` | 摆放 | `other_object_region_0` 沿 x 移了 0.10 m，重采 8 条；奶油奶酪大约移了 10.6 cm |
| `pick_the_cream_cheese_and_place_it_in_the_basket_yaw` | 朝向 | 同一 region 加上 yaw π/2，重采 8 条；平面位置几乎没动 |
