# LIBERO-Pro object 包：skill 与 profile 引用盘点

日期：2026-10-03  
对照提交：`refactor/bottom-drawer-capability-clean` @ `3b6fb6a`

盘点对象是当前 LIBERO-Pro object 战役的工作包：

`skill_packs/libero_object_task_from_spatial_swap_mining_base_20260918`

它从 spatial-swap 包拷贝而来，再叠上 object 轴和酒架 skill。`skills/_index.yaml` 的 `online` 为空，36 条全部在 `fail_only`。`--enable_skills` 不会加载它们；挖掘验证用 `--enable_mining_skills` 才会把这 36 条一起放进 matcher。`skills/pair/` 只有空目录，没有已晋升的 online skill。

2026-09-30 的表格式清单仍在 `docs/libero_pro_object_pack_skills_and_profiles_2026-09-30.md`。本文按当前文件重读 frontmatter，把引用关系写清楚，并逐条说明每条 skill 的适用范围和它跟同包其它 skill 的关系。

## 引用是怎么接上的

一条 skill 文件只做两件事里的一件，或者两件都沾一点：

- **trigger**（`kind: trigger`，`hook: after_pi0_query`）：决定这一拍要不要把控制交给 cuTAMP。`match_skills` 按 `priority` 从高到低取**第一个**触发成功的。后写的 skill 只要 priority 更高、语言又能匹配，就会盖住先写的。
- **recovery hint**（`kind: recovery_hint`）：不负责“何时接手”。recovery 已经开始后，`match_recovery_hints` 把**所有** `applies_to` 命中的 hint 合并进去，按 priority 从低到高排序。抓取、表面、几何、放下步数可以同时生效。

Profile 是被点名的那份做法，定义不在 skill 正文里：

| 种类 | 登记文件 | skill 里的字段 | 发生时机 |
| --- | --- | --- | --- |
| repair | `profiles/repair.yaml` | `recovery_hints.params.repair_profile` | 规划前抬手或转腕。挂在 trigger 上 |
| grasp | 本包 `code/grasp_profiles.py`，或核心 `experiments/robot/libero/tiptop_repro/grasp_profiles.py` | `recovery_hints.grasp_profile` | 生成抓取候选 |
| grounding | `profiles/grounding.yaml` | `recovery_hints.params.grounding_profile` | 把粗物体名改到该放的那一块 |
| geometry | `profiles/geometry.yaml` | `recovery_hints.params.geometry_profile` | 把那一块做成规划器里的盒子 |
| place | `profiles/place.yaml` | `recovery_hints.params.place_profile` | 只放宽悬停、下降、松手步数 |

`capabilities.yaml` 是允许名单。skill 点了一个没登记的名字，runner 会报 schema 错误。登记了但没有 skill 点名的 profile 仍留在包里，不会自己生效。

有三类例外，引用关系不是“一个字段对一个 profile”：

- 技能正文直接写 `geometry_hints` 或 `executor`，没有 `*_profile` 名字。柜顶几何和两条碗放盘子的 place hint 是这种。
- 点了 profile，又在技能里抄一份同类参数。奶油奶酪的 grounding hint 抄了一份坏掉的 `grounding_hints`；两条酒瓶 grasp hint 在 `libero_topdown` 之外又写了 `grasp_close_max_above_m: 0.18`。
- grounding 和 geometry 里都有 `wine_bottle_bowl_inner_floor_v1`。同名，两个文件，两份定义。

下面每一族先给接手链，再逐条写。链上的箭头表示“同一次 recovery 里会一起带上”，不是文件之间的 import。

## 奶油奶酪放进碗

来源是 LIBERO-Pro goal-swap task07。语言要同时像 cream cheese 和 bowl。

```text
cream_cheese_bowl_wrong_object_intent          接手，不改做法
  -> grasp_cream_cheese_bowl_flat_box_topdown_deep
       profile cream_cheese_flat_box_topdown_deep_v1
  -> cream_cheese_bowl_support_grounding
       profile cream_cheese_bowl_support_v1
  -> cream_cheese_bowl_support_geometry
       profile cream_cheese_bowl_support_geometry_v1
  -> cream_cheese_bowl_hover_drop_budget
       profile cream_cheese_bowl_hover_drop_budget_v1
```

### `cream_cheese_bowl_wrong_object_intent`

trigger，优先级 60。空手、夹爪仍张开、意图物体不是奶油奶酪、末端离目标小于 0.37 m、预测轨迹离目标大于 0.18 m、认错裕量大于 0.1。不挂 repair profile。接手之后做法完全靠同语言范围的四条 hint。priority 60 低于酒架那条 71，也低于篮子里奶油奶酪那几条 77/79；语言范围不同，正常不会互抢。

### `grasp_cream_cheese_bowl_flat_box_topdown_deep`

grasp hint，优先级 55。范围在奶油奶酪+碗的语言上，并排除黄油、布丁、碗、瓶子、牛奶盒等。点 `cream_cheese_flat_box_topdown_deep_v1`。这份 profile 也被篮子里的扁盒 hint 共用，但那条要求篮子语言，两边 `applies_to` 不会同时成立。

### `cream_cheese_bowl_support_grounding`

grounding hint，优先级 45。点 `cream_cheese_bowl_support_v1`，把碗标成 `support_object` / `stack_support` / `on`。技能正文又抄了一份 `grounding_hints`，其中 `relation: true`、`predicates: [true]`。YAML 会把 `true` 读成布尔值，不是字符串 `"on"`。生效定义在 profile 里；这份内联副本和 profile 不一致。

### `cream_cheese_bowl_support_geometry`

geometry hint，优先级 44。点 `cream_cheese_bowl_support_geometry_v1`，把碗登记成可移动支撑面，谓词 `on`。和上一条 grounding 是一对，单独一条不会给出落点盒子。

### `cream_cheese_bowl_hover_drop_budget`

place hint，优先级 43。已经在抓奶油奶酪、目标是碗时生效。点 `cream_cheese_bowl_hover_drop_budget_v1`。包里还有一份没人点的 `cream_cheese_bowl_low_hover_balanced_v1`，是更早的低悬停参数，当前索引不会用到。

## 碗放到柜顶

来源是 goal-swap task05。语言是 bowl 和 cabinet，排除白碗。

```text
bowl_cabinet_target_holding_handoff
  repair entry_lift_open_hand_small_v1
  内联 place 步数
  -> cabinet_top_surface_geometry_explicit
       内联几何，无 profile 名
```

这一族没有 grasp hint，也没有 grounding profile。

### `bowl_cabinet_target_holding_handoff`

trigger，优先级 63。和上面那些“认错物体”的 trigger 相反：它在末端已经靠近碗（小于 0.19 m），并且已经抓住或夹爪小于 0.03 时接手。点 `entry_lift_open_hand_small_v1`，同时在 trigger 正文里直接写了一组 place 步数（抬起最多 80 步，悬停间隙 0.08 m）。repair 和 place 参数写在同一条 trigger 上，没有单独的 place skill。

### `cabinet_top_surface_geometry_explicit`

geometry hint，优先级 48。`applies_to` 与上面那条 trigger 相同。不点 geometry profile，直接写盒子：源物体 `wooden_cabinet_1_main`，表面 `wooden_cabinet_1_cabinet_top`，xy 内缩 0.012 m，顶偏移 0.012 m，厚 0.012 m，`place_z_offset_m` 0.14。柜顶几何因此无法被别的 skill 按名字复用。

## 黑碗放到盘子

这一族共用一条 grasp hint，trigger 按语言句子拆开。盘子落点没有 grounding / geometry profile。

```text
bowl_plate_pick_lost_or_wrong_intent                 优先级 55，不挂 repair
bowl_cookie_box_wrong_bowl_handoff                   71，repair entry_lift
black_bowl_not_between_wrong_object_handoff          70，repair entry_lift
black_bowl_next_to_plate_wrong_object_handoff        71，repair entry_lift
black_bowl_cabinet_top_to_plate_wrong_object_handoff 72，repair entry_lift
black_bowl_wooden_cabinet_top_to_plate_early_...     78，repair entry_lift
  共同 hint:
  grasp_bowl_plate_hollow_rim_topdown
    profile hollow_bowl_rim_topdown
  仅两条句子另有 place hint，且是内联步数，不是 place profile:
  bowl_plate_hover_drop_budget                  「不在中间」
  bowl_plate_next_to_plate_hover_drop_budget    「盘子旁边」
```

`hollow_bowl_rim_topdown` 定义在核心抓取采样里，是通用顶抓打开 `rim=True`，不是本包 `code/grasp_profiles.py`。

### `bowl_plate_pick_lost_or_wrong_intent`

trigger，优先级 55。语言是笼统的 bowl 和 plate，目标名是黑碗。条件是空手、VLA 仍报 open、末端已经靠近目标（小于 0.16 m）。它不要求“认错物体”。优先级低于下面五条句子级 trigger。那些句子如果也匹配 `bowl.*plate`，会先被高优先级抢走；这条只接住没有更具体句子的碗放盘子。不挂 repair，也不改抓取以外的东西。注释里写明抓住之后再进这条会太晚。

### `grasp_bowl_plate_hollow_rim_topdown`

grasp hint，优先级 25，是本包 grasp hint 里最低的。语言 bowl+plate，目标黑碗，排除白碗，goal 表面是盘子。点 `hollow_bowl_rim_topdown`。上面几条认错 trigger 的注释都写着复用这一条，没有再各写一份抓取。因为 hint 按 `applies_to` 合并，只要语言是碗放盘子，这条就会带上，不需要 trigger 点名它。

### `bowl_cookie_box_wrong_bowl_handoff`

trigger，优先级 71。语言必须出现 cookie box，再放到盘子。目标名倾向 `akita_black_bowl_1`。空手、持续认错至少 4 次、最近可抓物体不是目标。点 `entry_lift_open_hand_small_v1`。没有自己的 place hint。

### `black_bowl_not_between_wrong_object_handoff`

trigger，优先级 70。语言是 “not between the plate and the ramekin”。目标名倾向 `akita_black_bowl_2`，但正则同时接受 `black_bowl|bowl`，真正切开任务的是语言。认错只需持续 2 次，比其它黑碗 trigger 更松。点同一个抬手 profile。

### `bowl_plate_hover_drop_budget`

place hint，优先级 58。语言锁在 “not between”，所以只跟上面那条 trigger 配。不点 place profile，直接写执行器步数：抬起最多 70 步，悬停间隙 0.055 m、最多 90 步，下降最多 120 步，松手高度上限 0.1 m，张爪停留 8 步。和「盘子旁边」那条 place hint 的数字相同，范围不同。

### `black_bowl_next_to_plate_wrong_object_handoff`

trigger，优先级 71。语言是 “next to the plate”。认错持续 4 次，意图物体距离小于 0.085 m，真实目标的预测距离大于 0.12 m。点同一个抬手 profile。和 cookie-box 那条优先级相同，语言不重叠，同优先级时按 skill id 排序决定先后。

### `bowl_plate_next_to_plate_hover_drop_budget`

place hint，优先级 62。语言锁 “next to”。执行器步数与 `bowl_plate_hover_drop_budget` 相同。注释写明不要用于 “not between”。两条 place hint 是同一组参数复制了两份，靠语言正则分开。

### `black_bowl_cabinet_top_to_plate_wrong_object_handoff`

trigger，优先级 72。语言是柜顶上的黑碗放到盘子，不要求 “wooden”。空手、认错持续 4 次、最近物体不是目标、目标仍静止且末端离目标大于 0.18 m。点同一个抬手 profile。没有专用 place hint。它和 `bowl_cabinet_target_holding_handoff` 不是同一件事：那条是“已经抓住、要放到柜顶”，这条是“还没抓住、要从柜顶拿到盘子”。

### `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff`

trigger，优先级 78，黑碗 trigger 里最高。语言必须有 wooden cabinet。距离门比上一条松：意图距离小于 0.06 m，目标预测距离大于 0.1 m，末端离目标大于 0.12 m。注释写它就是为了接住 task4 那套门限错过的 task5 窗口。点同一个抬手 profile。若一句语言同时像 “cabinet” 和 “wooden cabinet”，78 会先于 72 触发。

## 盘子放炉子

### `plate_stove_open_wrong_intent_pregrasp_handoff`

trigger，优先级 74。语言 plate+stove，目标是盘子，表面是炉子或 cook region。空手、VLA 仍报 open、认错持续 4 次、最近物体不是盘子、末端离盘子在 0.12–0.22 m、最近可抓物小于 0.2 m。不挂 repair，也不点 grasp / grounding / geometry / place。

包里已经有炉灶的两份 profile，这条 trigger 没有点它们，也没有对应 hint：

- grounding `plate_stove_cook_region_v1`：把 `flat_stove_1_main` 等改写成 `flat_stove_1_cook_region`
- geometry `stove_cook_region_surface_v1`：用这个 site 做盒子

所以盘子放炉子目前只决定何时接手，接手后仍走通用落点。grasp 侧登记了 `plate_rim_edge_topdown_v1`，同样没有 skill 点它。

## 酒瓶放进碗

来源是 goal-task task03。

```text
wine_bottle_bowl_wrong_object_handoff
  repair entry_lift_open_hand_small_v1
  -> grasp_wine_bottle_topdown_close_guard
       profile libero_topdown
       内联 grasp_close_max_above_m 0.18
  -> ground_wine_bottle_bowl_inner_floor
       grounding profile wine_bottle_bowl_inner_floor_v1
  -> geometry_wine_bottle_bowl_inner_floor
       geometry profile wine_bottle_bowl_inner_floor_v1
  -> place_wine_bottle_bowl_drop_budget
       profile wine_bottle_bowl_drop_budget_v1
```

### `wine_bottle_bowl_wrong_object_handoff`

trigger，优先级 72。语言是 wine bottle in bowl。空手、认错持续 4 次、最近物体不是酒瓶、末端离目标小于 0.25 m。点 `entry_lift_open_hand_small_v1`。抓住之后这条不再适用，注释写那时已经变成拿错物体。

### `grasp_wine_bottle_topdown_close_guard`

grasp hint，优先级 59。点核心采样 `libero_topdown`，另外把闭合高度上限从默认 0.12 m 放到 0.18 m，避免瓶身上方的闭合被判成太高。范围是酒瓶放进碗，和放到盘子的那条 grasp hint 是两份文件、同一套参数。

### `ground_wine_bottle_bowl_inner_floor`

grounding hint，优先级 49。点 grounding 文件里的 `wine_bottle_bowl_inner_floor_v1`：把整只碗改写成内底代理，后缀 `inner_floor`，关系 `inside`。

### `geometry_wine_bottle_bowl_inner_floor`

geometry hint，优先级 48。点 geometry 文件里的同名 `wine_bottle_bowl_inner_floor_v1`。这是另一份定义：边距 0.018 m，离底 0.006 m，厚 0.010 m，最小跨度 0.040 m，`place_z_offset_m` 0.110，排除容器自身碰撞。grounding 改名字，geometry 造盒子，两边都要命中才完整。

### `place_wine_bottle_bowl_drop_budget`

place hint，优先级 47。点 `wine_bottle_bowl_drop_budget_v1`。悬停间隙 0.055 m，下降最多 130 步，松手高度上限 0.115 m。只在酒瓶放进碗时生效。

## 酒瓶放到盘子

```text
wine_bottle_plate_wrong_object_handoff
  repair entry_lift_open_hand_small_v1
  -> grasp_wine_bottle_plate_topdown_close_guard
       profile libero_topdown
       内联 grasp_close_max_above_m 0.18
```

没有盘子专用的 grounding、geometry、place。落点用通用盘子表面。

### `wine_bottle_plate_wrong_object_handoff`

trigger，优先级 71。语言是 wine bottle on plate。比放进碗那条多两个距离门：最近可抓物小于 0.22 m，意图 xy 距离小于 0.035 m。点同一个抬手 profile。

### `grasp_wine_bottle_plate_topdown_close_guard`

grasp hint，优先级 59。profile 和闭合高度与放进碗那条相同，`applies_to` 换成盘子。两条不会因为目标名都是酒瓶而同时命中，语言和 goal 表面把它们分开。

## 物体放进篮子

这一族几乎全是 trigger。抓取只覆盖扁盒和直立纸盒。字母汤、ketchup、沙拉酱、烧烤酱、番茄酱接手后仍用通用采样器。

篮子 trigger 的优先级从高到低：

| 优先级 | skill | 目标 |
| ---: | --- | --- |
| 79 | `object_basket_cream_tomato_q5_wrong_intent_window` | cream cheese 或 tomato sauce |
| 78 | `object_basket_bbq_orange_precontact_wrong_intent` | bbq sauce 或 orange juice |
| 77 | `object_basket_cream_cheese_precontact_wrong_intent` | cream cheese |
| 76 | `object_basket_persistent_wrong_intent_group_a` | alphabet soup、butter、chocolate pudding、ketchup、milk |
| 76 | `object_basket_salad_dressing_precontact_wrong_intent` | salad dressing |
| 75 | `object_basket_tomato_persistent_wrong_intent` | tomato sauce |

奶油奶酪进篮子时，79 和 77 的语言都能匹配。79 更高，会先试那扇更窄的 q5 窗口；窗口外才落到 77。番茄酱同样是 79 先于 75。group_a 不含奶油奶酪和番茄酱。

对应 hint：

```text
grasp_object_basket_flat_box_topdown_deep
  奶油奶酪、黄油、巧克力布丁
  profile cream_cheese_flat_box_topdown_deep_v1
grasp_carton_upright_body_side
  直立的牛奶或橙汁
  profile carton_upright_body_side_v1
```

### `object_basket_persistent_wrong_intent_group_a`

trigger，优先级 76。五个目标共用一条。条件是这组里最宽的：空手、认错持续 4 次、裕量大于 0。没有距离窗口。不挂 repair。黄油和巧克力布丁接手后会带上扁盒 grasp hint；牛奶会再看纸盒 hint 的朝向条件；字母汤和 ketchup 没有专用 grasp。

### `object_basket_bbq_orange_precontact_wrong_intent`

trigger，优先级 78。烧烤酱或橙汁。认错 4 次，并且最近物体距离落在 0.08–0.20 m。橙汁如果同时还是直立纸盒，grasp hint 会用侧抓；烧烤酱没有专用 grasp。

### `object_basket_salad_dressing_precontact_wrong_intent`

trigger，优先级 76。最近物体距离 0.10–0.16 m，末端离真实目标大于 0.18 m，VLA 状态仍是 open。不要求认错裕量字段。没有专用 grasp。和 group_a 同优先级，语言不重叠。

### `object_basket_cream_cheese_precontact_wrong_intent`

trigger，优先级 77。最近物体距离 0.10–0.16 m，状态要是 `non_target_intent`。不挂 repair。扁盒 grasp hint 用篮子语言加上奶油奶酪目标名，会在这次 recovery 里一起生效。它和“奶油奶酪放进碗”那条 trigger 靠 “place it in the basket” 对 “cream cheese.*bowl” 分开。

### `object_basket_tomato_persistent_wrong_intent`

trigger，优先级 75。认错持续 4 次，且目标预测距离大于 0.12 m。没有专用 grasp，也没有 place profile。

### `object_basket_cream_tomato_q5_wrong_intent_window`

trigger，优先级 79，篮子里最高。奶油奶酪或番茄酱。比上面两条更窄：末端 6 步内位移小于 0.35 m，认错只需持续 1 次但裕量要大于 0.1，最近物体距离卡在 0.20–0.24 m，目标预测距离大于 0.19 m。注释写 4 次持续认错在这些集上达不到，所以另开一扇窗。它不替代 77 和 75，只在这扇窗里先触发。

### `grasp_object_basket_flat_box_topdown_deep`

grasp hint，优先级 60。语言限定 “pick the (cream cheese|butter|chocolate pudding) and place it in the basket”。点 `cream_cheese_flat_box_topdown_deep_v1`，和碗任务那条扁盒 hint 是同一个采样器。priority 60 高于碗那条 grasp hint 的 55；两边语言不同，不会叠在同一次 recovery 里。

### `grasp_carton_upright_body_side`

grasp hint，优先级 60。`applies_to` 只看目标名是 milk 或 orange juice，朝向 upright，并排除一串其它物体。它不要求篮子语言。注释说“语言范围交给前面的篮子 trigger”，但 hint 的合并不看 trigger 有没有先触发，只看 `applies_to`。挖掘库打开时，任何直立牛奶盒或橙汁盒的 recovery 都会带上 `carton_upright_body_side_v1`。这是本包里范围写得比注释更宽的一条。

`carton_upright_body_side_v1` 抓取高度在总高的 80%（离桌面），yaw 为 0 和 π，开度是盒身短边加 6 mm。更早的 tall-carton 顶抓已经撤回，不在这 36 条里。

## 奶油奶酪放到酒架

这 4 条在 32 条快照之后进索引，来源记的是 goal-task task10，2026-10-01 又把入口改成了转腕。

```text
cream_cheese_rack_wrong_object_handoff
  repair entry_topdown_orientation_reset_v1
  -> grasp_cream_cheese_rack_flat_box_deep
       profile cream_cheese_flat_box_topdown_deeper_v2
  -> ground_cream_cheese_rack_top_region
       profile wine_rack_top_region_v1
  -> geometry_cream_cheese_rack_top_region
       profile wine_rack_top_region_surface_v1
```

没有 place profile。

### `cream_cheese_rack_wrong_object_handoff`

trigger，优先级 71。语言 cream cheese + rack。空手、认错持续 3 次、最近物体不是目标且距离小于 0.28 m、末端离奶油奶酪小于 0.265 m、目标仍静止。点 `entry_topdown_orientation_reset_v1`：规划前把腕部转回竖直向下，不改 xyz，最多 30 步。这是本包唯一使用这份 repair profile 的 skill。抬手那份 `entry_lift_open_hand_small_v1` 不在这条上。

### `ground_cream_cheese_rack_top_region`

grounding hint，优先级 68。点 `wine_rack_top_region_v1`，把酒架本体改写成 `wine_rack_1_top_region`。

### `geometry_cream_cheese_rack_top_region`

geometry hint，优先级 67。点 `wine_rack_top_region_surface_v1`。site 边距 0.003 m，最小半宽 0.024 m，厚 0.006 m，`place_z_offset_m` 0.095。允许与黑碗接触，排除酒架自身碰撞。和 grounding 是一对。

### `grasp_cream_cheese_rack_flat_box_deep`

grasp hint，优先级 59。点 `cream_cheese_flat_box_topdown_deeper_v2`，不是碗和篮子用的 v1。v2 把深度改到顶面下 0.75 和 0.55 个顶半高，给大约 18 mm 厚的盒子。语言和 goal 都要求 rack，所以不会和碗任务、篮子任务的扁盒 hint 同时命中。

## Profile 对照

「引用」只计这 36 条索引里的 `*_profile` 字段。内联参数不算引用。

### repair

| profile | 做法 | 引用它的 skill |
| --- | --- | --- |
| `entry_lift_open_hand_small_v1` | 空手竖直抬起 0.045 m，最多 12 步，到达容差 0.008 m，夹爪命令 0.0 | `bowl_cabinet_target_holding_handoff`，`bowl_cookie_box_wrong_bowl_handoff`，`black_bowl_not_between_wrong_object_handoff`，`black_bowl_next_to_plate_wrong_object_handoff`，`black_bowl_cabinet_top_to_plate_wrong_object_handoff`，`black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff`，`wine_bottle_bowl_wrong_object_handoff`，`wine_bottle_plate_wrong_object_handoff` |
| `entry_topdown_orientation_reset_v1` | 规划前转到 `libero_topdown_home_v1`，最多 30 步，不改 xyz | `cream_cheese_rack_wrong_object_handoff` |

9 条 trigger 挂了 repair。其余 9 条 trigger 只接手，不改规划前姿态：奶油奶酪进碗、笼统碗放盘子、盘子放炉子、全部篮子 trigger。

### grasp

| profile | 定义位置 | 做法 | 引用它的 skill |
| --- | --- | --- | --- |
| `cream_cheese_flat_box_topdown_deep_v1` | 本包 `code/grasp_profiles.py` | 朝上的面，沿长边中心和 ±8% 半长，四个 yaw，深度在顶面下 0.35 和 0.15 个顶半高 | `grasp_cream_cheese_bowl_flat_box_topdown_deep`，`grasp_object_basket_flat_box_topdown_deep` |
| `cream_cheese_flat_box_topdown_deeper_v2` | 同上 | 同上，深度改为 0.75 和 0.55 个顶半高 | `grasp_cream_cheese_rack_flat_box_deep` |
| `carton_upright_body_side_v1` | 同上 | 直立纸盒，高度在总高 80%，侧向闭合 | `grasp_carton_upright_body_side` |
| `plate_rim_edge_topdown_v1` | 同上 | 盘沿：两个高度、两个径向比例、八个方向 | 无 |
| `libero_topdown` | 核心 `grasp_profiles.py` | 通用顶抓 | `grasp_wine_bottle_topdown_close_guard`，`grasp_wine_bottle_plate_topdown_close_guard` |
| `hollow_bowl_rim_topdown` | 核心，顶抓加 `rim=True` | 碗沿 | `grasp_bowl_plate_hollow_rim_topdown` |
| `default` / `native` / `cutamp_native` | 能力表里的通用别名 | 未在本包展开 | 无 |

### grounding

| profile | 改写 | 引用它的 skill |
| --- | --- | --- |
| `cream_cheese_bowl_support_v1` | 碗作为支撑物，关系 `on` | `cream_cheese_bowl_support_grounding` |
| `plate_stove_cook_region_v1` | 炉体改写成 `flat_stove_1_cook_region` | 无 |
| `wine_bottle_bowl_inner_floor_v1` | 碗改写成内底代理，关系 `inside` | `ground_wine_bottle_bowl_inner_floor` |
| `wine_rack_top_region_v1` | 酒架改写成 `wine_rack_1_top_region` | `ground_cream_cheese_rack_top_region` |

### geometry

| profile | 盒子 | 引用它的 skill |
| --- | --- | --- |
| `cream_cheese_bowl_support_geometry_v1` | 可动碗面，谓词 `on` | `cream_cheese_bowl_support_geometry` |
| `stove_cook_region_surface_v1` | site `flat_stove_1_cook_region`，`place_z_offset_m` 0.160 | 无 |
| `wine_bottle_bowl_inner_floor_v1` | 碗内底，`place_z_offset_m` 0.110。与 grounding 同名不同文件 | `geometry_wine_bottle_bowl_inner_floor` |
| `wine_rack_top_region_surface_v1` | site `wine_rack_1_top_region`，允许碰到黑碗 | `geometry_cream_cheese_rack_top_region` |

`cabinet_top_surface_geometry_explicit` 写了几何，但没有点上面任何一份。

### place

| profile | 悬停与下降 | 引用它的 skill |
| --- | --- | --- |
| `cream_cheese_bowl_hover_drop_budget_v1` | 抬起最多 50 步，悬停最多 80 步，下降最多 120 步，松手高度上限 0.090 m | `cream_cheese_bowl_hover_drop_budget` |
| `cream_cheese_bowl_low_hover_balanced_v1` | 悬停间隙 0.045 m，下降最多 120 步，松手高度上限 0.100 m | 无 |
| `wine_bottle_bowl_drop_budget_v1` | 悬停间隙 0.055 m，下降最多 130 步，松手高度上限 0.115 m | `place_wine_bottle_bowl_drop_budget` |

另外三条把同类执行器数字直接写在 skill 里：`bowl_plate_hover_drop_budget`，`bowl_plate_next_to_plate_hover_drop_budget`，以及 trigger `bowl_cabinet_target_holding_handoff`。

## 这一包里已经能看见的叠用

- 黑碗放盘子有 6 条 trigger、1 条 grasp、2 条内联 place。句子不同，抬手 profile 和碗沿抓取相同。priority 78 到 55 决定谁先接手。
- 扁盒顶抓 v1 被“放进碗”和“放进篮子”各包了一层语言。酒架用更深的 v2，没有复用 v1。
- 两条酒瓶 grasp 是同一份 `libero_topdown` 加同一个 0.18 m 闭合上限，拆成两个文件。
- 篮子里奶油奶酪、番茄酱各有一条宽 trigger 和一条更高优先级的窄窗口。窄窗口先匹配。
- 炉灶的 grounding / geometry，以及盘沿 grasp、低悬停 place，已经登记，没有 skill 接上。
- `grasp_carton_upright_body_side` 的注释把范围交给篮子 trigger，`applies_to` 却只限制物体名和朝向。
- `cream_cheese_bowl_support_grounding` 在 profile 之外又写了一份 `relation: true` 的内联 hint。
