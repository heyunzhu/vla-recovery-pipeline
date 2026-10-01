# LIBERO-Pro object 包：当前 skill 与 profile

日期：2026-09-30

范围是工作区里这一份包的当前文件，不是 2026-09-21 那次 32 条快照：

`skill_packs/libero_object_task_from_spatial_swap_mining_base_20260918`

索引 `skills/_index.yaml` 的 `online` 为空。36 条都列在 `fail_only` 下。`--enable_skills` 只加载 `pair/` 里、并且写进 `online` 的技能，所以这 36 条不会随普通开技能开关进入正式评测；挖掘验证用单独的 fail_only 加载。`skills/drafts/` 里还有两条未进索引的草稿，不在下面的 36 条里。

2026-09-21 确定性基线用的 32 条，是下面清单去掉最后一组酒架 4 条。那一版索引校验是 `b32e5a1024daa74e3fc771a726d2eeb9`。

## 两种文件各管什么

技能文件决定两件事：什么情况下接手，以及这次接手要带上哪个 profile 名字。Profile 是被点名的那份做法，定义在 yaml 或 `code/grasp_profiles.py` 里，同一份可以被多条技能引用。

当前文件并没有把这两件事分干净：

- 技能分成触发器和 hint。触发器只决定何时把控制交给 cuTAMP。hint 才改抓取、表面、几何或放下步数。
- profile 有五类，发生在不同环节：repair 在规划前抬手或转腕；grasp 生成抓取候选；grounding 决定放到哪一块表面；geometry 把那一块做成规划器里的盒子；place 只放宽悬停和下降的步数，不改落点坐标。
- 有的 hint 只写 profile 名字，有的把同类参数直接写在技能正文里，有的两处都写。

## 技能

下列「使用的 profile」只统计技能正文里出现的 `*_profile:` 名字。另外写在技能里、但没有 profile 名字的参数放在「内联」列。

### 奶油奶酪放进碗

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `cream_cheese_bowl_wrong_object_intent` | 触发器，优先级 60 | 语言是奶油奶酪和碗，策略反复朝别的物体去 | 目标名含 cream cheese；BDDL 表面含 bowl | 无 | 无 |
| `grasp_cream_cheese_bowl_flat_box_topdown_deep` | grasp hint，优先级 55 | 恢复要抓这盒奶油奶酪，通用顶抓太浅、太宽 | 同上，并排除 butter、碗、瓶子、牛奶盒等 | `cream_cheese_flat_box_topdown_deep_v1` | 无 |
| `cream_cheese_bowl_support_grounding` | grounding hint，优先级 45 | 目标表面是碗这个可动物体 | 语言、目标名、goal 名都含 bowl | `cream_cheese_bowl_support_v1` | 又抄了一份 `grounding_hints`，其中 `relation` 和 `predicates` 写成 `true`。生效定义在 profile 里 |
| `cream_cheese_bowl_support_geometry` | geometry hint，优先级 44 | 规划器需要把这只碗登记成可放置的面 | 同上 | `cream_cheese_bowl_support_geometry_v1` | 无 |
| `cream_cheese_bowl_hover_drop_budget` | place hint，优先级 43 | 已经抓住奶油奶酪，要放进碗 | 同上 | `cream_cheese_bowl_hover_drop_budget_v1` | 无 |

### 碗放到柜顶

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `bowl_cabinet_target_holding_handoff` | 触发器，优先级 63 | 碗放柜顶，策略已经抓住目标之后 | 目标是碗，排除白碗；表面是 cabinet top | `entry_lift_open_hand_small_v1` | 无 |
| `cabinet_top_surface_geometry_explicit` | geometry hint，优先级 48 | 需要 BDDL 表面 `wooden_cabinet_1_cabinet_top` | 同上 | 无 | 直接写几何：源物体 `wooden_cabinet_1_main`，盒子，xy 内缩 0.012 m，顶偏移 0.012 m，厚 0.012 m，`place_z_offset_m` 0.14 |

### 碗放到盘子，以及几条「哪一只黑碗」

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `bowl_plate_pick_lost_or_wrong_intent` | 触发器，优先级 55 | 碗放盘子，抓丢了或认错物体 | 目标是黑碗，表面是盘子 | 无 | 无 |
| `bowl_cookie_box_wrong_bowl_handoff` | 触发器，优先级 71 | 饼干盒上的碗要放到盘子，认错了碗 | 目标是黑碗，goal 是盘子 | `entry_lift_open_hand_small_v1` | 无 |
| `grasp_bowl_plate_hollow_rim_topdown` | grasp hint，优先级 25 | 恢复要抓这只碗 | 黑碗放盘子，排除白碗 | `hollow_bowl_rim_topdown` | 无 |
| `black_bowl_not_between_wrong_object_handoff` | 触发器，优先级 70 | 「不在盘子和 ramekin 中间的那只黑碗」认错 | 目标名倾向 `akita_black_bowl_2`，goal 是盘子 | `entry_lift_open_hand_small_v1` | 无 |
| `bowl_plate_hover_drop_budget` | place hint，优先级 58 | 这条「不在中间」的任务已经抓住碗，要放到盘子 | 目标名含黑碗，goal 是盘子 | 无 | 直接写执行器步数。抬起最多 70 步，到达 0.014 m，最小间隙 0.03 m；悬停间隙 0.055 m、最多 90 步，到达 0.014 m；下降最多 120 步，到达 0.018 m；松手高度上限 0.1 m，张爪停留 8 步 |
| `black_bowl_next_to_plate_wrong_object_handoff` | 触发器，优先级 71 | 「盘子旁边那只黑碗」认错 | 目标名倾向 `akita_black_bowl_2` | `entry_lift_open_hand_small_v1` | 无 |
| `bowl_plate_next_to_plate_hover_drop_budget` | place hint，优先级 62 | 这条「旁边」的任务已经抓住碗，要放到盘子 | 同上 | 无 | 与上一条 place hint 相同的一组执行器步数 |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | 触发器，优先级 72 | 柜顶的黑碗放到盘子，认错 | 同上 | `entry_lift_open_hand_small_v1` | 无 |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | 触发器，优先级 78 | 木柜顶的黑碗放到盘子，更早接手 | 语言里要求 wooden cabinet | `entry_lift_open_hand_small_v1` | 无 |

### 盘子放炉子

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | 触发器，优先级 74 | 盘子放炉子，手还开着，却稳定地朝别的物体（黑碗）去 | 目标是盘子，表面是炉子或 cook region | 无 | 无 |

这份包里登记了炉灶的 grounding / geometry profile，这条触发器没有点它们。见文末「没有技能点名的 profile」。

### 酒瓶放进碗、酒瓶放到盘子

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `wine_bottle_bowl_wrong_object_handoff` | 触发器，优先级 72 | 酒瓶放进黑碗，策略还在跟别的物体 | 目标是酒瓶，goal 是碗 | `entry_lift_open_hand_small_v1` | 无 |
| `grasp_wine_bottle_topdown_close_guard` | grasp hint，优先级 59 | 恢复要先抓住酒瓶再放进碗 | 同上 | `libero_topdown` | `grasp_close_max_above_m: 0.18`。默认 0.12 m 会把瓶身上方的闭合判成太高 |
| `ground_wine_bottle_bowl_inner_floor` | grounding hint，优先级 49 | 落点要从整只碗改到碗的内底 | 同上 | `wine_bottle_bowl_inner_floor_v1`（grounding 登记表） | 无 |
| `geometry_wine_bottle_bowl_inner_floor` | geometry hint，优先级 48 | 规划器里要有这块内底 | 同上 | `wine_bottle_bowl_inner_floor_v1`（geometry 登记表，同名不同文件） | 无 |
| `place_wine_bottle_bowl_drop_budget` | place hint，优先级 47 | 已经抓住酒瓶，要放进碗 | 同上 | `wine_bottle_bowl_drop_budget_v1` | 无 |
| `wine_bottle_plate_wrong_object_handoff` | 触发器，优先级 71 | 酒瓶放到盘子，策略还在跟别的物体 | 目标是酒瓶，goal 是盘子 | `entry_lift_open_hand_small_v1` | 无 |
| `grasp_wine_bottle_plate_topdown_close_guard` | grasp hint，优先级 59 | 恢复要先抓住酒瓶再放到盘子 | 同上 | `libero_topdown` | 同样把 `grasp_close_max_above_m` 放到 0.18 |

### 物体放进篮子

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `object_basket_persistent_wrong_intent_group_a` | 触发器，优先级 76 | 字母汤、黄油、巧克力布丁、ketchup、牛奶：连续 4 次认错，手仍空着 | 语言是 pick … and place it in the basket；表面是 basket | 无 | 无 |
| `object_basket_bbq_orange_precontact_wrong_intent` | 触发器，优先级 78 | 烧烤酱或橙汁：认错已经进入距非目标 0.08–0.20 m 的窗口 | 同上，目标是 bbq sauce 或 orange juice | 无 | 无 |
| `object_basket_salad_dressing_precontact_wrong_intent` | 触发器，优先级 76 | 沙拉酱：靠近状态下的持续认错 | 目标是 salad dressing | 无 | 无 |
| `object_basket_cream_cheese_precontact_wrong_intent` | 触发器，优先级 77 | 奶油奶酪放进篮子：靠近状态下的持续认错 | 目标是 cream cheese | 无 | 无 |
| `object_basket_tomato_persistent_wrong_intent` | 触发器，优先级 75 | 番茄酱放进篮子：认错持续 | 目标是 tomato sauce | 无 | 无 |
| `object_basket_cream_tomato_q5_wrong_intent_window` | 触发器，优先级 79 | 奶油奶酪或番茄酱：第 5 次查询附近的更窄认错窗口。上面两条的「连续 4 次」在这些集上达不到 | 目标是 cream cheese 或 tomato sauce | 无 | 无 |
| `grasp_object_basket_flat_box_topdown_deep` | grasp hint，优先级 60 | 篮子恢复要抓奶油奶酪、黄油或巧克力布丁 | 这三样，表面是 basket | `cream_cheese_flat_box_topdown_deep_v1` | 无 |
| `grasp_carton_upright_body_side` | grasp hint，优先级 60 | 直立牛奶盒或橙汁盒。通用顶抓会夹在收窄的盒顶上 | 目标名是 milk 或 orange juice，朝向 upright。语言范围交给前面的篮子触发器 | `carton_upright_body_side_v1` | 无 |

字母汤、ketchup、沙拉酱、烧烤酱、番茄酱只有触发器，没有单独的抓取 hint，接手后仍用通用采样器。

### 奶油奶酪放到酒架

这 4 条在 32 条快照之后才进索引。

| 技能 | 种类 | 何时接手 / 何时生效 | 适用范围 | 使用的 profile | 内联 |
| --- | --- | --- | --- | --- | --- |
| `cream_cheese_rack_wrong_object_handoff` | 触发器，优先级 71 | 奶油奶酪放酒架，空手持续跟着别的物体 | 目标是 cream cheese，goal 是 rack | `entry_topdown_orientation_reset_v1` | 无 |
| `ground_cream_cheese_rack_top_region` | grounding hint，优先级 68 | 表面要锁在 `wine_rack_1_top_region`，不要整只酒架 | 同上 | `wine_rack_top_region_v1` | 无 |
| `geometry_cream_cheese_rack_top_region` | geometry hint，优先级 67 | 用现场 site 做出这块顶面，并允许碰到旁边的黑碗 | 同上 | `wine_rack_top_region_surface_v1` | 无 |
| `grasp_cream_cheese_rack_flat_box_deep` | grasp hint，优先级 59 | 从桌面抓这盒大约 18 mm 厚的奶油奶酪 | 同上，并排除黄油、碗、瓶子、纸盒 | `cream_cheese_flat_box_topdown_deeper_v2` | 无 |

## Profile

「引用它的技能」只列当前索引里的 36 条。没有引用的也列在这里，因为它们仍在 `capabilities.yaml` 或对应 yaml 里。

### grasp

采样代码有两处。`libero_topdown` 和 `hollow_bowl_rim_topdown` 在核心 `experiments/robot/libero/tiptop_repro/grasp_profiles.py`，两者都走同一套顶抓采样，后者把 `rim=True`。本包 `code/grasp_profiles.py` 实现下面四个 id。`capabilities.yaml` 还登记了 `default`、`native`、`cutamp_native`，没有技能点它们。

| profile | 做法 | 引用它的技能 |
| --- | --- | --- |
| `cream_cheese_flat_box_topdown_deep_v1` | 按现场盒子找朝上的轴。沿长边取中心和 ±8% 半长，四个 yaw。深度在顶面下 0.35 和 0.15 个顶半高。夹爪开度是短边半宽的 2.25 倍，限制在 0.025–0.075 m。名字带奶油奶酪，篮子里的黄油和巧克力布丁用的是同一份 | `grasp_cream_cheese_bowl_flat_box_topdown_deep`，`grasp_object_basket_flat_box_topdown_deep` |
| `cream_cheese_flat_box_topdown_deeper_v2` | 与上一份相同，深度改到顶面下 0.75 和 0.55 个顶半高，给约 18 mm 厚的盒子 | `grasp_cream_cheese_rack_flat_box_deep` |
| `carton_upright_body_side_v1` | 直立纸盒。抓取高度是总高的 80%（离桌面，避开盒顶）。物体中心，yaw 为 0 和 π，闭合方向沿物体 x、与顶棱平行。开度是盒身短边加 6 mm | `grasp_carton_upright_body_side` |
| `plate_rim_edge_topdown_v1` | 盘子边缘：两个高度、两个径向比例、八个方向，每个方向四个 yaw。开度按厚度的 2.2 倍，限制在 0.035–0.060 m | 无 |
| `libero_topdown` | 核心通用顶抓 | `grasp_wine_bottle_topdown_close_guard`，`grasp_wine_bottle_plate_topdown_close_guard` |
| `hollow_bowl_rim_topdown` | 核心顶抓的碗沿形式 | `grasp_bowl_plate_hollow_rim_topdown` |
| `default` / `native` / `cutamp_native` | 能力表里的通用别名 | 无 |

### place

定义在 `profiles/place.yaml`。三份都只写执行器步数和高度容差。

| profile | 悬停 | 下降与松手 | 引用它的技能 |
| --- | --- | --- | --- |
| `cream_cheese_bowl_hover_drop_budget_v1` | 抬起最多 50 步，到达 0.012 m，最小间隙 0.025 m；悬停最多 80 步，到达 0.015 m | 下降最多 120 步，到达 0.018 m，松手高度上限 0.090 m，张爪停留 8 步 | `cream_cheese_bowl_hover_drop_budget` |
| `cream_cheese_bowl_low_hover_balanced_v1` | 悬停间隙 0.045 m；抬起最多 40 步；悬停最多 50 步，到达 0.020 m | 下降最多 120 步，松手高度上限 0.100 m，张爪停留 8 步 | 无 |
| `wine_bottle_bowl_drop_budget_v1` | 悬停间隙 0.055 m；抬起最多 45 步；悬停最多 70 步，到达 0.018 m | 下降最多 130 步，松手高度上限 0.115 m，张爪停留 8 步 | `place_wine_bottle_bowl_drop_budget` |

### grounding

定义在 `profiles/grounding.yaml`。作用是把目标从粗的物体名改到该放的那一块。

| profile | 改写 | 引用它的技能 |
| --- | --- | --- |
| `cream_cheese_bowl_support_v1` | 把碗标成支撑物：`support_object`，`intent: stack_support`，关系 `on` | `cream_cheese_bowl_support_grounding` |
| `plate_stove_cook_region_v1` | 盘子放炉子时，把 `flat_stove_1_main`、burner 等改写成 `flat_stove_1_cook_region` | 无 |
| `wine_bottle_bowl_inner_floor_v1` | 酒瓶放进碗时，把整只碗改写成内底代理，后缀 `inner_floor`，关系 `inside` | `ground_wine_bottle_bowl_inner_floor` |
| `wine_rack_top_region_v1` | 奶油奶酪放酒架时，把酒架本体改写成 `wine_rack_1_top_region` | `ground_cream_cheese_rack_top_region` |

### geometry

定义在 `profiles/geometry.yaml`。作用是用现场场景把上一节那一块做成规划器里的盒子。`wine_bottle_bowl_inner_floor_v1` 与 grounding 里的同名条目不是同一份。

| profile | 盒子 | 引用它的技能 |
| --- | --- | --- |
| `cream_cheese_bowl_support_geometry_v1` | 可动支撑面，物体类是碗，谓词 `on` | `cream_cheese_bowl_support_geometry` |
| `stove_cook_region_surface_v1` | site `flat_stove_1_cook_region`。边距 0.006 m，最小半宽 0.040 m，顶间隙 0.002 m，厚 0.010 m，`place_z_offset_m` 0.160 | 无 |
| `wine_bottle_bowl_inner_floor_v1` | 碗的内底。边距 0.018 m，离底 0.006 m，厚 0.010 m，最小跨度 0.040 m，`place_z_offset_m` 0.110，排除容器自身碰撞 | `geometry_wine_bottle_bowl_inner_floor` |
| `wine_rack_top_region_surface_v1` | site `wine_rack_1_top_region`。边距 0.003 m，最小半宽 0.024 m，顶间隙 0.003 m，厚 0.006 m，`place_z_offset_m` 0.095。允许与黑碗接触，排除酒架自身碰撞 | `geometry_cream_cheese_rack_top_region` |

### repair

定义在 `profiles/repair.yaml`。挂在触发器上，发生在规划开始之前。

| profile | 动作 | 引用它的技能 |
| --- | --- | --- |
| `entry_lift_open_hand_small_v1` | 空手竖直抬起 0.045 m，最多 12 步，到达容差 0.008 m，夹爪命令 0.0 | `bowl_cabinet_target_holding_handoff`，`bowl_cookie_box_wrong_bowl_handoff`，`black_bowl_not_between_wrong_object_handoff`，`black_bowl_next_to_plate_wrong_object_handoff`，`black_bowl_cabinet_top_to_plate_wrong_object_handoff`，`black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff`，`wine_bottle_bowl_wrong_object_handoff`，`wine_bottle_plate_wrong_object_handoff` |
| `entry_topdown_orientation_reset_v1` | 规划前把腕部转回竖直向下，不改 xyz。朝向名 `libero_topdown_home_v1`，最多 30 步，夹爪命令 0.0 | `cream_cheese_rack_wrong_object_handoff` |

## 技能到 profile 的对照

一行一条技能。空的表示该技能没有 `*_profile:` 字段。

| 技能 | repair | grasp | grounding | geometry | place |
| --- | --- | --- | --- | --- | --- |
| `cream_cheese_bowl_wrong_object_intent` | | | | | |
| `grasp_cream_cheese_bowl_flat_box_topdown_deep` | | `cream_cheese_flat_box_topdown_deep_v1` | | | |
| `cream_cheese_bowl_support_grounding` | | | `cream_cheese_bowl_support_v1` | | |
| `cream_cheese_bowl_support_geometry` | | | | `cream_cheese_bowl_support_geometry_v1` | |
| `cream_cheese_bowl_hover_drop_budget` | | | | | `cream_cheese_bowl_hover_drop_budget_v1` |
| `bowl_cabinet_target_holding_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `cabinet_top_surface_geometry_explicit` | | | | | |
| `bowl_plate_pick_lost_or_wrong_intent` | | | | | |
| `bowl_cookie_box_wrong_bowl_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `grasp_bowl_plate_hollow_rim_topdown` | | `hollow_bowl_rim_topdown` | | | |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | | | | | |
| `wine_bottle_bowl_wrong_object_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `grasp_wine_bottle_topdown_close_guard` | | `libero_topdown` | | | |
| `wine_bottle_plate_wrong_object_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `grasp_wine_bottle_plate_topdown_close_guard` | | `libero_topdown` | | | |
| `ground_wine_bottle_bowl_inner_floor` | | | `wine_bottle_bowl_inner_floor_v1` | | |
| `geometry_wine_bottle_bowl_inner_floor` | | | | `wine_bottle_bowl_inner_floor_v1` | |
| `place_wine_bottle_bowl_drop_budget` | | | | | `wine_bottle_bowl_drop_budget_v1` |
| `black_bowl_not_between_wrong_object_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `bowl_plate_hover_drop_budget` | | | | | |
| `black_bowl_next_to_plate_wrong_object_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `bowl_plate_next_to_plate_hover_drop_budget` | | | | | |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | `entry_lift_open_hand_small_v1` | | | | |
| `object_basket_bbq_orange_precontact_wrong_intent` | | | | | |
| `object_basket_cream_cheese_precontact_wrong_intent` | | | | | |
| `object_basket_persistent_wrong_intent_group_a` | | | | | |
| `object_basket_salad_dressing_precontact_wrong_intent` | | | | | |
| `object_basket_tomato_persistent_wrong_intent` | | | | | |
| `grasp_object_basket_flat_box_topdown_deep` | | `cream_cheese_flat_box_topdown_deep_v1` | | | |
| `object_basket_cream_tomato_q5_wrong_intent_window` | | | | | |
| `grasp_carton_upright_body_side` | | `carton_upright_body_side_v1` | | | |
| `cream_cheese_rack_wrong_object_handoff` | `entry_topdown_orientation_reset_v1` | | | | |
| `ground_cream_cheese_rack_top_region` | | | `wine_rack_top_region_v1` | | |
| `geometry_cream_cheese_rack_top_region` | | | | `wine_rack_top_region_surface_v1` | |
| `grasp_cream_cheese_rack_flat_box_deep` | | `cream_cheese_flat_box_topdown_deeper_v2` | | | |

没有点名 profile、但技能正文里写了同类参数的三条：`cabinet_top_surface_geometry_explicit`，`bowl_plate_hover_drop_budget`，`bowl_plate_next_to_plate_hover_drop_budget`。两条酒瓶抓取 hint 在 `libero_topdown` 之外还写了 `grasp_close_max_above_m: 0.18`。

登记了、当前 36 条都没有点名的 profile：`plate_rim_edge_topdown_v1`，`default`，`native`，`cutamp_native`，`cream_cheese_bowl_low_hover_balanced_v1`，`plate_stove_cook_region_v1`，`stove_cook_region_surface_v1`。
