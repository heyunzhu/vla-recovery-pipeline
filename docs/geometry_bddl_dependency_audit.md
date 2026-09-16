# libero_90 geometry 的 BDDL 依赖：审计与解决方案

日期：2026-09-16
分支：`feature/bddl-language-and-goal`
状态：审计完成；方案待批准实施。本文只谈 geometry 读取 BDDL 的部分，不涉及 goal layer 的语言化改造（见 `docs/bddl_goal_context_migration_implementation_plan.md`）。

## 0. 一句话结论

整个 libero_90 里，**只有 7/90 个任务的 goal 需要 BDDL `(:ranges)` 的数字**，落在 **5 个区域**上；加上我们在跑的套件，全世界的需求是 **libero_goal_task 1 个（t6）+ libero_10_swap 1 个**，而 **libero_spatial_swap 和 libero_object_swap 是 0 个**。

这 5+2 个区域**全部是桌子坐标系下的小方片**（10×10 cm，一个 8×8 cm），数字是场景作者写死在 BDDL 里的常数。它们可以被**一次性转写成常量**（数据已经在仓库里），从而把运行时对 BDDL 的几何依赖压缩到 **5 个常量**，不需要新 schema，也不需要运行时读 BDDL。

## 1. 审计用的数据与复现方法

- 权威数据：`benchmarks/libero90_generated_v1_envfiltered_304/inventory/libero_90_tasks.jsonl`（90 行，一行一个原始 libero_90 任务）。每行含 `bddl_file`、`bddl_path`、`language`、`goal_atoms`（**已解析成 qualified region name**）、`regions`（`name` / `qualified_name` / `ranges` / `target`）、`task_id_1based`。
- 审计脚本：`experiments/.pro/audit_libero90_goal_regions.py`（本地 `.pro/` 工具，未入库），运行：

```powershell
cd E:\VLA_recovery_workspace\openvla-oft\experiments
python .pro\audit_libero90_goal_regions.py
```

- 判据：一个 goal atom 的最后一个参数若命中该任务的 `regions` 中某条 —— `ranges` 非空 ⇒ `TABLE_RECT`（需要数字）；`ranges` 为空 ⇒ `SITE`（几何只存在于 MuJoCo 模型/site 里，BDDL 没有数字）；否则该 goal 只是普通物体。
- 重要区分：BDDL 里 `(:ranges)` **绝大多数是 init region**（物体初始摆放的采样范围，例如 `plate_init_region`）。它们和本议题无关。**只有出现在 goal atom 里的区域才需要数字。**

## 2. 90 个任务的分类结果

| 类别 | 数量 | 任务 id |
|---|---|---|
| goal 需要 BDDL `(:ranges)` 数字 | **7** | 35, 38, 70, 71, 77, 85, 86 |
| goal 是 fixture/site 区域（无 ranges） | 59 | 2–9, 11, 12, 16, 19, 20, 22, 24–28, 30, 32, 33, 39, 41–44, 46–63, 74–76, 78–84, 87–90 |
| goal 只是物体 | 15 | 10, 13, 14, 15, 17, 18, 31, 36, 37, 66–69, 72, 73 |
| 混合 | 2 | 64, 65 |

其它套件（只统计 goal atom，`(:language)` 取自各套件 BDDL）：

| 套件 | 需要数字的 goal 区域 |
|---|---|
| `libero_spatial_swap`（正在 mining） | **0** —— 10 个 goal 全是 `(On bowl plate_1)` 这种物体 goal |
| `libero_goal_task`（已 mining 完） | **1** —— t6 `push_the_plate_to_the_front_of_the_stove` |
| `libero_10_swap` | 1 —— `(On chocolate_pudding_1 living_room_table_plate_right_region)` |
| `libero_object_swap` | 0 —— goal 全是 `(In x basket_1_contain_region)` |

## 3. 需要数字的 goal atom 全清单（含真实数字）

| task | goal atom | goal region | ranges（表格坐标系 x1 y1 x2 y2） | 尺寸 | 所属 table |
|---|---|---|---|---|---|
| 35 | `on white_yellow_mug_1` | `kitchen_table_porcelain_mug_front_region` | −0.05, −0.30, +0.05, −0.20 | 10×10 cm | kitchen_table |
| 38 | `on white_bowl_1` | `kitchen_table_plate_right_region` | −0.05, +0.05, +0.05, +0.15 | 10×10 cm | kitchen_table |
| 70 | `on chocolate_pudding_1` | `living_room_table_plate_left_region` | +0.10, −0.15, +0.20, −0.05 | 10×10 cm | living_room_table |
| 71 | `on chocolate_pudding_1` | `living_room_table_plate_right_region` | +0.10, +0.05, +0.20, +0.15 | 10×10 cm | living_room_table |
| 77 | `on white_yellow_mug_1` | `study_table_desk_caddy_right_region` | −0.25, +0.10, −0.15, +0.20 | 10×10 cm | study_table |
| 85 | `on red_coffee_mug_1` | `study_table_desk_caddy_right_region` | −0.25, +0.10, −0.15, +0.20 | 10×10 cm | study_table |
| 86 | `on porcelain_mug_1` | `study_table_desk_caddy_right_region` | −0.25, +0.10, −0.15, +0.20 | 10×10 cm | study_table |
| goal_task t6 | `on cream_cheese_1` | `main_table_stove_front_region` | −0.09, +0.17, −0.01, +0.25 | **8×8 cm** | main_table |

`goal_region` 的命名模式是固定的：`<table>_<anchor>_<direction>_region`，`direction ∈ {left, right, front}`。

## 4. 现有实现怎么消费这些数字

包：`skill_packs/libero90_legacy/`（`feature/recovery-mining-campaign` 与 `main` 上一致）。

### 4.1 两个 profile 走 `bddl_table_rect`

| profile | `profiles/geometry.yaml` | 匹配的 goal surface | 实际触发任务 |
|---|---|---|---|
| `plate_side_region_geometry_v1` | 4–21 | `*_table_plate_left_region` / `*_table_plate_right_region` | 38, 70, 71 |
| `desk_caddy_side_region_geometry_v1` | 22–47 | `*_desk_caddy_left_region` / `*_desk_caddy_right_region` | 77, 85, 86 |

（注意：caddy 那个 profile 覆盖的是 **77/85/86 三个**任务，不只是 85/86。另外它们的 language 是 "to the right of **the caddy**"，不是"右格"。）

### 4.2 读取路径

`code/geometry_profiles.py`：

- `_bddl_regions()` 123–125：从 `task.diagnostics["bddl_regions"]` 取（即 `task_parser.py` 的 BDDL 解析产物）。
- `_bddl_region_xy_bounds()` 138–153：取 `ranges` 前 4 个数当 x/y min/max。
- `_bddl_table_rect_bounds()` 232–260：`bounds_from_bddl_region` 为真时给出 bounds + provenance（`source_bddl_region` / `source_bddl_qualified_region` / `source_bddl_target` / `source_bddl_ranges` / `bddl_scene_xy_offset`）。
- `_bddl_region_xy_offset()` 169–197：`align_bddl_regions_to_scene`（默认 True）时，用**同一张桌子上所有 init atom** 的"（物体实际世界 xy − 该物体 BDDL init region 中心 xy）"的**中位数**作为整张桌子的坐标系偏移，叠加到 bounds 上。
- profile 选择仍依赖 BDDL goal surface：`_fixed_table_region_candidate()` 218–229 要求 `region_name in _bddl_goal_surface_names(task)`，后者 200–215 读 `diagnostics["bddl_goal_surfaces"]/["bddl_goal_atoms"]`。

`experiments/robot/libero/tiptop_repro/tamp_scene.py`：`_virtual_fixed_table_rect_surface()` 1618–1657 有一条平行的读取路径（adapter rect → `hint["bounds_m"]` → BDDL ranges）。

### 4.3 已经"烤成常量"的先例（我们建议的目标形态）

`task35_mug_front_region_geometry_v1`（`profiles/geometry.yaml` 48–70）与 `task38_plate_right_region_geometry_v1`（71–97）已经是 `intent: fixed_table_rect`：

```yaml
task38_plate_right_region_geometry_v1:
  params:
    geometry_hints:
      placement_region:
        intent: fixed_table_rect
        region_name: kitchen_table_plate_right_region     # 写死，不再从 goal 推
        bounds_m: {x_min: 0.60, x_max: 0.70, y_min: 0.05, y_max: 0.15}   # 世界坐标，写死
        place_z_offset_m: 0.160
        place_candidate_policy: farthest_from_reference_with_corners
        place_candidate_reference_object: plate_1_main
        source_bddl_region: plate_right_region            # provenance：数字来自哪里
        source_bddl_ranges: [-0.05, 0.05, 0.05, 0.15]
```

没有 `bounds_from_bddl_region`，没有 `align_bddl_regions_to_scene`，运行时**完全不碰 BDDL**。注意 `bounds_m` 与表格坐标系 `ranges` 的关系：x 平移 **+0.65**，y 不变 —— 这个 +0.65 就是 kitchen_table 的世界偏移，与 4.2 里运行时估出来的那个 offset 是同一个量，只是这里被冻结成了常量。

### 4.4 另外 5 个 profile 只用区域**名字**

`desk_caddy_compartment_inner_floor_v1`、`top_drawer_inner_floor_geometry_v1`、`shelf_region_inner_floor_geometry_v1`、`container_inside_region_geometry_v1`、`bowl_stack_support_geometry_v1` 不读数字，几何来自 MuJoCo 的 site / body AABB。它们仍然用 BDDL 里长出来的**字符串**（例如 `desk_caddy_1_right_contain_region`）做匹配，这属于 goal layer 的中性别名问题，不在本文范围。

### 4.5 隐患：静默兜底

`tamp_scene.py` 1649–1652：当 adapter rect、`bounds_m`、BDDL ranges **全都拿不到**时，函数静默使用 **以桌面中心为中心的 10×10 cm 方片**（`default_x ± 0.05`，下限 `min_span_m` 0.045，1654–1657），**不产生任何 diagnostic**。这意味着"停止读 BDDL"如果只做一半，不会报错，只会让机械臂把物体放在桌子中间 —— 属于必须一起修掉的静默降级。

## 5. 这些数字能不能不用 BDDL 算出来

把每个区域中心减去**锚物自己 init region 的中心**：

| task | 锚 + 方向 | 尺寸 | 偏移（m） | 说明 |
|---|---|---|---|---|
| 35 | porcelain_mug 前方 | 10×10 | **+0.100** (x) | 方片近边正好在锚物边缘（半径≈0.05） |
| 38 | plate 右方 | 10×10 | **+0.100** (y) | 同上 |
| 70 | plate 左方 | 10×10 | **−0.100** (y) | 同上 |
| 71 | plate 右方 | 10×10 | **+0.100** (y) | 同上 |
| 77/85/86 | desk_caddy 右方 | 10×10 | **+0.290** (y) | 近边距 caddy 中心 0.24 m，**不符合贴边规则** |
| goal_task t6 | stove 前方（main_table） | 8×8 | 待量 | 桌子区域，不在 caddy/plate 家族里 |

结论：**"10×10 cm 方片 + 近边贴在锚物 AABB 边缘"这条规则对 plate/mug 锚精确复现 4 个任务（35/38/70/71）；对 caddy 不成立**（若成立，caddy 的 +y 半宽得是 0.24 m）。所以 caddy 那个数字是作者常数，不能靠同一条规则推导。

### 5.1 三条可选路线

| 路线 | 做法 | 精确性 | 需要什么 | 是否读 BDDL |
|---|---|---|---|---|
| A. 锚 + 方向 + 约定常量 | 语言给 anchor 和方向；尺寸 0.10 m、"贴边"是约定 | t35/38/70/71 精确；caddy 不成立 | live 锚物 pose（已有） | 否 |
| B. 锚 AABB + 间隙 | 从 MuJoCo 量锚物 AABB，再外推一个间隙 | 间隙无统一值（0.05 vs 0.19）⇒ 仍需标定 | caddy 真实 AABB | 否 |
| C. 历史成功落点反推 | 从成功 episode 的最终落点相对锚物取中位数邻域/凸包 | **保证落在真矩形内部**，但不复刻边界 | 该任务有成功样本（85/86 有） | 否 |
| D. 一次性转写 | 从 inventory jsonl 把数字转成 profile 常量 | 精确 | 无（数据已在仓库） | 离线一次，运行时否 |

C 的关键认识：**pack 需要的不是"复刻校验器的矩形"，而是一个合法的 place target**。只要目标点落在真矩形**内部**，校验器就通过。所以从成功样本反推出来的子区域完全够用。

### 5.2 推荐

**走 D**，理由不是"方便"，而是：

1. 这些数字是场景作者常数，BDDL 之外没有第二处定义，也没有统一规则可推导（§5 的 caddy 例外就是证据）。
2. 数据**已经在仓库里**（`inventory/libero_90_tasks.jsonl`），转写是**转录**，不是引入新依赖。
3. 不转写的话只剩两条路：继续在运行时读 BDDL（被否），或者让 §4.5 的兜底接管（静默改几何，更糟）。
4. 规模是 **5 个常量 + 6 个任务**（t35/38/70/71/77/85/86），再加 goal_task t6 一个。
5. 有现成先例（task35/task38 已经这么干了，且是稳定通过的 known-good）。

## 6. 推荐的最小改法（geometry 部分）

1. 把 `plate_side_region_geometry_v1`、`desk_caddy_side_region_geometry_v1` 改成 §4.3 那种 `fixed_table_rect`：写死 `region_name` + 写死 `bounds_m`（世界坐标）+ 保留 `source_bddl_*` provenance；删掉 `bounds_from_bddl_region`、`region_name_from_bddl_goal`、`align_bddl_regions_to_scene`。
2. `bounds_m` = 表格坐标系 `ranges` + 该 table 的世界偏移。kitchen_table 已经知道是 **+0.65 (x)**；living_room_table / study_table 需要量一次（运行时已经在 metadata 里记录 `bddl_scene_xy_offset`，跑一个 episode 读出来冻结即可）。
3. 触发方式断掉 BDDL：legacy pack 由 runner 按 **task id** 直接选 profile；新套件由 goal layer 传中性的 surface 名字（例如保留 `study_table_desk_caddy_right_region` 这个字符串，但它由 goal layer 产生，而不是从 BDDL 解析）。
4. 顺手把 §4.5 的静默兜底改成**显式失败**（记录 diagnostic，不静默用桌面中心）。
5. 影响面：`profiles/geometry.yaml` 两个 profile + `code/geometry_profiles.py` 里两个 `bddl_*` 分支；`intent: bddl_table_rect` 这个 intent 在改完后应无引用。

## 7. 验收

1. **ranges 屏蔽回归（关键测试）**：**不要**去改 BDDL 文件清空 `(:regions)` —— init 摆放也用它，环境会直接失效。正确做法是把**运行时解析结果**对 geometry 层屏蔽：给一个测试钩子/开关，使 geometry 层看到的 `ranges` 为空，然后跑 libero_90 的 known-good 回归，结果必须与改前**逐条一致**。
2. **static gate（可执行的规则）**：新增测试扫描 pack 的 geometry profile，出现 `bounds_from_bddl_region` / `bddl_goal_surface_matches` / `align_bddl_regions_to_scene` 即失败，防止回退。
3. 常量与本文 §3 的数字逐条对照（脚本可重跑）。

## 8. 后续 geometry profile 怎么 mining

mining 挖的是 skill / trigger，**不挖几何数字**。分工是：

1. 套件入场时跑一次 §1 的分类（离线），产出 `geometry_regions.yaml`：每条 goal 区域一行 —— `kind`（`site` / `table_rect`）、`anchor`、`direction`、`size`、数字、`provenance`。**这是唯一允许接触 BDDL 的地方。**
2. 新写的 geometry profile 只能**引用**这张表里的条目，不允许自带 `bounds_from_bddl_region`；由 §7.2 的 static gate 强制。
3. 纪律：**绝不把 `table_rect` 类 goal 区域折叠成 fixture site。** 实例：`libero_goal_task` t6 的 goal 是 `(On cream_cheese_1 main_table_stove_front_region)`（x[−0.09,−0.01] y[0.17,0.25]，8×8 cm 的**桌面**区域），而当前 pack 把它折成 `flat_stove_1_main`（灶台面）。把物体放在灶台上无法满足 `On main_table_*_region`，这与 goal_task 里 t6 卡住的现象一致 —— 需要用 §7.1 的屏蔽测试确认。
4. 每个新套件入场检查里加一条：**goal atom 里有没有 `TABLE_RECT`**（本文 §2 已经给出四个套件的答案）。

## 9. 未决问题 / 风险

1. `align_bddl_regions_to_scene` 的 offset 是否逐 episode 漂移？它是同桌所有物体 init 残差的中位数；如果桌子位姿固定，它应当是常数（kitchen_table 的 +0.65 支持这一点）。需要跨若干 episode 采样确认，否则冻结常量会有偏差。
2. caddy 的 0.29 m 成因未定（作者常数？还是与 table 后排/其它物体对齐？）。若日后要换成推导式，需先用 MuJoCo 量出 caddy AABB。
3. 本文只覆盖 goal 里的区域；**init region 的对齐量**（§4.2 那个 offset）与 site 类区域的 AABB 取法未在本次范围内。
4. 三个套件的分类是用 BDDL 文本逐文件确认的，`libero_swap/lan/object` 的其它变体未逐个量。

## 10. 附录：文件与行号索引

| 内容 | 位置 |
|---|---|
| 90 任务权威数据 | `benchmarks/libero90_generated_v1_envfiltered_304/inventory/libero_90_tasks.jsonl` |
| 审计脚本 | `experiments/.pro/audit_libero90_goal_regions.py`（本地工具） |
| profile 定义 | `skill_packs/libero90_legacy/profiles/geometry.yaml:4-21, 22-47, 48-70, 71-97` |
| 运行时读 ranges | `skill_packs/libero90_legacy/code/geometry_profiles.py:123-125, 138-153, 169-197, 232-260` |
| profile 选择读 goal surface | 同上 `:200-215, 218-229` |
| 平行读取路径 + 静默兜底 | `experiments/robot/libero/tiptop_repro/tamp_scene.py:1618-1657`（兜底 1649–1657） |
| 相邻先例（site 读取） | `skill_packs/libero_goal_task_from_goal_swap_v1/code/geometry_profiles.py:158-235` |
