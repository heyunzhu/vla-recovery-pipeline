# Geometry Skill Static Test Standard

更新日期：2026-09-09

本文定义 `geometry` recovery hint 的静态测试标准。它面向 harness / CI 使用，用来防止
Codex 在 mining loop 中写出不受控的虚拟 surface、错误的 region bounds、过宽的碰撞排除，
或把 geometry / grounding / grasp / place 职责混在一起的 skill。

本文只约束 active skill pack 下的：

```text
skill_packs/<pack>/skills/pair/recovery_hint/geometry/*.md
```

`geometry` 不决定是否进入 recovery，也不决定任务语义应该绑定到哪里。它只在某个
repair / trigger 已经决定进入 recovery，并且 grounding 已经给出正确语义目标后，把目标区域
转成 planner 可以优化的几何表示。

## 1. 核心契约

`geometry` skill 只回答一个问题：

> 已经确定的目标 surface / region / support object，在 planner 世界里应该被表示成什么几何？

因此静态测试检查六层契约：

1. **Catalog 契约**：在线 geometry skill 必须显式出现在 active pack 的
   `skills/_index.yaml`。
2. **Schema 契约**：必须是 `kind: recovery_hint`、`scope: geometry`，不能声明
   `trigger`、`hook` 或 `backend`。
3. **语义边界契约**：已入库 geometry skill 优先只引用 `geometry_profile`；新增 profile 草稿才允许输出 `geometry_hints`，不得重新做 grounding 或 grasp。
4. **数值契约**：bounds、margin、thickness、z offset、release tolerance 必须处在合理范围。
5. **链路契约**：hint 使用的 profile 必须能经由当前 skill pack 的 geometry adapter 转成
   `real_cutamp_adapter.py`、`tamp_scene.py` 或 executor 明确消费的 planner primitive / 字段。
6. **配套契约**：虚拟 region / movable support 类 geometry 必须能和对应 grounding skill
   一起工作。
7. **坐标帧契约**：adapter 读取的 site / bounds 必须与 planner problem 中的 movable pose 同帧；
   virtual surface / opening metadata 必须显式声明 `planner_frame` 或 `world`。

## 2. 当前 Online Geometry Skills

`libero90_legacy` pack 当前有 9 个 online geometry skill：

| skill | 几何类型 | 作用 |
| --- | --- | --- |
| `plate_side_region_geometry.md` | BDDL table rect | 把 plate 左/右侧 BDDL region 暴露为 planner 可用的薄桌面矩形。 |
| `desk_caddy_side_region_geometry.md` | BDDL table rect | 把 caddy 左/右侧 BDDL region 暴露为 table region，并裁到远离 caddy 的一侧。 |
| `task35_mug_front_region_geometry.md` | fixed table rect | task35 专用 front-of-white-mug 虚拟桌面区域。 |
| `task38_plate_right_region_geometry.md` | fixed table rect | task38 专用 right-of-plate 虚拟桌面区域，并优先选择远离 plate 的候选。 |
| `container_inside_region.md` | inner-floor proxy | 把 basket/container inside 目标转成 `*_inner_floor` place-on proxy。 |
| `top_drawer_inner_floor_geometry.md` | inner-floor proxy | 把 top drawer inside 目标转成抽屉内地板 proxy。 |
| `shelf_region_inner_floor_geometry.md` | inner-floor proxy | 把 shelf top/bottom region 转成 shelf 内部地板 proxy。 |
| `desk_caddy_compartment_geometry.md` | compartment inner-floor proxy | 把 desk caddy 前/后/左/右格转成 inner-floor proxy，并带 high-drop / yaw 预算。 |
| `bowl_stack_support_geometry.md` | movable support surface | 把目标 bowl 注册为临时 support surface。 |

这些 skill 会直接影响 planner world、place candidates、collision exclusion 和部分 release
metadata，比 grounding 更容易把系统写歪。

## 3. Catalog 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | active pack `skills/_index.yaml` 中引用的 geometry skill 文件不存在。 |
| ERROR | active pack `skills/pair/recovery_hint/geometry/` 下存在未 online 且没有 `status: draft/retired/archived/experimental` 的 `.md` 文件。 |
| ERROR | online geometry skill 标记为 `status: draft/retired/archived/experimental`。 |
| ERROR | online geometry skill 的 `id` 与文件名语义冲突。 |
| WARN | 文件正文没有说明它和配套 grounding / place skill 的边界。 |

## 4. Schema 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | `kind` 必须是 `recovery_hint`。 |
| ERROR | `scope` 必须是 `geometry`。 |
| ERROR | 不得声明 `trigger`、`hook`、`backend`。 |
| ERROR | 必须有 `recovery_hints.params.geometry_profile` 或 `recovery_hints.params.geometry_hints`。 |
| ERROR | 已入库 online skill 直接内联 `geometry_hints`，且没有明确处于 draft / profile-authoring 状态。 |
| ERROR | 使用 `geometry_profile` 时，profile 必须存在于当前 skill pack 的 `profiles/geometry.yaml` 且已在 capability registry 注册。 |
| ERROR | 需要 benchmark-specific 代码的 `geometry_profile` 必须由当前 skill pack 的 `code/geometry_profiles.py` 暴露并映射到通用 planner primitive。 |
| ERROR | 使用 `geometry_hints` 时，必须至少包含 `placement_region` 或 `movable_support_surface` 之一。 |
| ERROR | 不得出现 `recovery_hints.grasp_profile`。 |
| ERROR | 不得出现 `grounding_hints`。 |
| WARN | `recovery_point` 不是 “After a repair/trigger skill has already decided to call recovery.” 或等价表述。 |
| WARN | `when_not_to_apply` 缺少明确反例。 |

geometry skill 可以在少数情况下带 executor 参数，但必须通过第 9 节的 allowlist。默认策略是：
能不写 executor 就不写 executor。

## 5. Hint Vocabulary / Primitive 检查

当前代码主要消费两类 geometry hint。

hint 可以使用 pack-local intent 名称，但必须通过 active pack 的
`code/geometry_profiles.py` 归一化到主引擎支持的 generic planner primitive。generic primitive
的单一来源是 `experiments/robot/libero/tiptop_repro/engine_capabilities.py`。

### 5.1 `placement_region`

`placement_region` 表示 planner 应该创建或使用一个放置 region / proxy。

允许的 `intent`：

| intent | 用途 |
| --- | --- |
| `bddl_table_rect` | 从 BDDL goal surface 的 region bounds 创建 table rectangle。 |
| `fixed_table_rect` | 为少数 task-specific BDDL region 创建固定 table rectangle。 |
| `container_inner_floor` | open container / basket 内部地板 proxy。 |
| `drawer_inner_floor` | drawer 内部地板 proxy。 |
| `compartment_inner_floor` | desk caddy front/back/left/right compartment 内部地板 proxy。 |
| `shelf_region_inner_floor` | shelf top/bottom region 内部地板 proxy。 |

常用字段：

| 字段 | 要求 |
| --- | --- |
| `relation` | 必须和语义一致，通常是 `on` 或 `inside`。 |
| `support_surface` | table region 类必须明确。 |
| `region_name` | 只用于 task-specific fixed region。 |
| `region_name_from_bddl_goal` | BDDL 动态 region 建议使用。 |
| `bounds_from_bddl_region` | BDDL 动态 region 必须使用。 |
| `bounds_m` | fixed region 必须使用，并且 x/y min/max 有效。 |
| `container_name_matches` | inner-floor proxy 类必须提供。 |
| `region_name_matches` | compartment / shelf region 类必须提供。 |
| `proxy_suffix` | inner-floor proxy 类必须提供，通常是 `inner_floor`。 |
| `support_z_from` | table region 类建议是 `table`。 |

静态 gate 应检查：

| 级别 | 检查项 |
| --- | --- |
| ERROR | hint 既没有可识别 `intent`，也没有显式 `planner_primitive`。 |
| ERROR | `intent` 未在 active pack 的 `capabilities.yaml` 注册。 |
| ERROR | adapter 归一化后仍无法得到 `fixed_table_rect`、`inner_floor` 或 `movable_support_surface`。 |
| ERROR | 新 profile 需要 benchmark-specific adapter，但 active pack 没有暴露 `geometry_profile_adapter`。 |
| WARN | 依赖主流程 legacy 名称猜测，而不是显式 planner primitive。 |

### 5.2 `movable_support_surface`

`movable_support_surface` 表示 planner 应该允许某个可移动物体临时成为 support surface。

允许的 `intent`：

| intent | 用途 |
| --- | --- |
| `stack_support` | bowl-on-bowl stack，把第二个 bowl 注册为 support surface。 |

常用字段：

| 字段 | 要求 |
| --- | --- |
| `object_class` | 必须存在，例如 `bowl`。 |
| `require_movable` | 建议为 `true`。 |
| `predicates` | 建议列出 `on`。 |

### 5.3 Generic Geometry Descriptor

如果 `fixed_table_rect` / `inner_floor` / `movable_support_surface` 不需要新增控制流，只是要构造
一个简单代理几何，可以使用 `surface_descriptor`。当前支持的 descriptor shapes：

| shape | 用途 |
| --- | --- |
| `box` | axis-aligned cuboid / thin support。 |
| `rotated_box` | 有 yaw 的矩形 proxy。 |
| `cylinder` | 圆柱或圆盘 proxy。 |
| `sphere` | 球形 sanity / blocker proxy。 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | descriptor shape 不在 engine 支持列表。 |
| ERROR | descriptor shape 未在 active pack 的 `capabilities.yaml` 注册。 |
| ERROR | descriptor 缺少尺寸、中心、source 或 coordinate frame 说明。 |
| WARN | descriptor 用来替代本应由 inner-floor / table-rect 表达的常规 region。 |

需要斜面、圆环、漏斗、非凸格腔等新构造时，应提出共享 engine primitive。不要把新形状藏在
pack adapter 输出里让主流程无法审计。

## 6. 数值 Sanity 检查

geometry 直接改变 planner 的物理世界。所有米制参数都必须有合理范围。

| 字段 | 建议范围 | 说明 |
| --- | --- | --- |
| `thickness_m` | 0.002 - 0.050 | 虚拟 support 不应变成厚障碍物。 |
| `min_span_m` | 0.020 - 0.200 | 太小不可达，太大会超出目标区域。 |
| `margin_m` | 0.000 - 0.060 | inner-floor 裁剪边界。 |
| `site_margin_m` | 0.000 - 0.030 | 使用 MuJoCo site bounds 时的额外 margin。 |
| `floor_clearance_m` | 0.000 - 0.030 | inner floor 抬离真实底面高度。 |
| `place_z_offset_m` | 0.000 - 0.250 | place 候选点高度偏置。 |
| `planner_support_z_offset_m` | 0.000 - 0.250 | high-drop 中 planner 支撑面偏置。 |
| `release_z_offset_m` | 0.000 - 0.200 | high-drop 开爪高度。 |
| `release_z_tolerance_m` | 0.000 - 0.100 | high-drop z 容差。 |
| `release_xy_margin_m` | 0.000 - 0.050 | 开爪前 footprint 必须进入的 shrink margin。 |
| `place_candidate_entry_fraction` | 0.050 - 0.950 | compartment entry candidate 的归一化位置。 |
| `place_candidate_edge_margin_m` | 0.000 - 0.030 | candidate 距边缘 margin。 |
| `place_candidate_max_count` | 1 - 16 | 候选过多会增加调试难度。 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | `bounds_m.x_min >= bounds_m.x_max` 或 `bounds_m.y_min >= bounds_m.y_max`。 |
| ERROR | fixed table rect 缺少 `bounds_m`。 |
| ERROR | BDDL table rect 缺少 `bounds_from_bddl_region: true`。 |
| ERROR | 数值字段不是数字。 |
| ERROR | 数值字段超出硬范围。 |
| WARN | fixed region 使用绝对坐标，但没有 `source_bddl_region` / `source_bddl_ranges`。 |
| WARN | place / release z offset 和 support z 之间的关系没有在正文解释。 |

## 7. Region 来源检查

| 几何形态 | 必要来源 |
| --- | --- |
| `bddl_table_rect` | `region_name_from_bddl_goal: true` 和 `bounds_from_bddl_region: true`。 |
| `fixed_table_rect` | `region_name`、`bounds_m`、`source_bddl_region`。 |
| `container_inner_floor` | container name pattern 和 proxy suffix。 |
| `drawer_inner_floor` | drawer level 或明确 drawer container pattern。 |
| `compartment_inner_floor` | container pattern、region pattern、compartment 从 region name 解析。 |
| `shelf_region_inner_floor` | shelf region pattern。 |
| `stack_support` | movable support object class。 |

禁止在 geometry 中凭单条视频估一个任意点，然后把它作为通用 region 入库。若必须使用固定
region，只能写成 task-specific skill，并保留 BDDL 来源和验证证据。

## 8. Grounding 配套检查

geometry 一般不应该单独出现。它需要 grounding 把语义目标指向同一类 region / support。

| geometry skill | 需要配套 grounding |
| --- | --- |
| `plate_side_region_geometry` | `plate_side_region_grounding` |
| `desk_caddy_side_region_geometry` | `desk_caddy_side_region_grounding` |
| `desk_caddy_compartment_geometry` | `desk_caddy_compartment_grounding` |
| `task35_mug_front_region_geometry` | `task35_mug_front_region_grounding` |
| `task38_plate_right_region_geometry` | `task38_plate_right_region_grounding` |
| `top_drawer_inner_floor_geometry` | `top_drawer_container_grounding` |
| `shelf_region_inner_floor_geometry` | `shelf_support_grounding` |
| `bowl_stack_support_geometry` | `bowl_stack_support_grounding` |

| 级别 | 检查项 |
| --- | --- |
| ERROR | 虚拟 region geometry 没有对应 online grounding。 |
| ERROR | geometry 的 intent 与 grounding 的 intent 无法对应。 |
| ERROR | geometry 的 `region_name_matches` 与 grounding 的 `bddl_goal_surface_matches` / `region_name_matches` 不相交。 |
| ERROR | relation 冲突，例如 grounding 是 `on`，geometry 只接受 `inside`。 |
| WARN | grounding 来自 BDDL 动态 region，而 geometry 写死固定 region。 |

## 9. Collision / Release / Executor 检查

geometry 可以携带少量 planner metadata，但这些字段风险较高。

### 9.1 Collision

| 字段 | 检查 |
| --- | --- |
| `exclude_source_collision` | 只能用于目标 source/container 本身阻挡进入其内部区域的情况。 |
| `exclude_table_collision` | 必须说明为什么 table 在该目标上等价于 support 而不是障碍。 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | collision exclude 出现在 table-side fixed region 中。 |
| WARN | collision exclude 没有 evidence 说明 planner 卡在哪个 collision / constraint。 |
| WARN | 同时排除 source 和 table，但没有 trace 对照。 |

### 9.2 Release

| 字段 | 检查 |
| --- | --- |
| `release_mode` | 当前只允许 `high_drop_into_compartment`。 |
| `release_z_offset_m` | 必须和 `release_z_tolerance_m` 同时检查。 |
| `release_xy_margin_m` | 不能靠过大 margin 掩盖目标偏差。 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | 未知 release mode。 |
| ERROR | high-drop 用在非 container / compartment 类目标。 |
| WARN | high-drop 没有说明为什么普通 release guard 不能工作。 |

### 9.3 Executor

默认 geometry 不写 executor。当前允许的例外字段：

| key | 合理范围 |
| --- | --- |
| `place_yaw_after_hover` | `world_z_thin_x` |
| `place_yaw_after_hover_max_steps` | 0 - 80 |
| `place_yaw_step_rad` | 0.01 - 0.30 |
| `place_yaw_max_cmd` | 0.01 - 0.50 |

| 级别 | 检查项 |
| --- | --- |
| ERROR | executor key 不在 allowlist。 |
| ERROR | executor value 超出范围。 |
| ERROR | executor yaw 出现在非 compartment / book-caddy 类 geometry，且无说明。 |
| WARN | executor 参数没有配套 place skill 或验证 run。 |

## 10. Canary 匹配检查

静态 gate 应维护 canary state，离线调用 matcher，检查典型任务是否命中正确 geometry。

| canary | 预期 geometry |
| --- | --- |
| chocolate pudding left of plate，BDDL surface 为 `*_table_plate_left_region` | `plate_side_region_geometry` |
| red mug right of caddy，BDDL surface 为 `*_desk_caddy_right_region` | `desk_caddy_side_region_geometry` |
| book in right compartment of caddy，BDDL surface 为 `*_right_contain_region` | `desk_caddy_compartment_geometry` |
| white bowl right of plate | `task38_plate_right_region_geometry` |
| yellow-white mug front of white mug | `task35_mug_front_region_geometry` |
| ketchup in top drawer of cabinet | `top_drawer_inner_floor_geometry` |
| book in shelf top/bottom region | `shelf_region_inner_floor_geometry` |
| cream cheese in basket | `container_inside_region` |
| stack bowl on bowl | `bowl_stack_support_geometry` |

| 级别 | 检查项 |
| --- | --- |
| ERROR | canary 没有命中任何 geometry。 |
| ERROR | canary 命中错误 geometry。 |
| ERROR | caddy compartment 被 caddy side geometry 抢走。 |
| ERROR | table-side region 被 container inner-floor geometry 抢走。 |
| WARN | 多个 geometry 同时命中，且 priority 关系没有说明。 |

## 11. Trace / Problem Scan 检查

静态 gate 不重跑仿真，但应能用历史 trace 和 `.problem.json` 扫描 geometry 链路。

最低报告：

| 字段 | 含义 |
| --- | --- |
| `task_id` / `episode_idx` / `query_idx` | 匹配位置。 |
| `task_description` | 原始任务语言。 |
| `target_name` / `goal_name` | recovery 解析出的目标和语义 goal。 |
| `bddl_goal_surfaces` | BDDL 给出的候选 surface / region。 |
| `matched_geometry_hints` | 所有匹配的 geometry skill。 |
| `compiled_goal_surface` | `real_cutamp_adapter` 最后使用的 surface / proxy。 |
| `created_virtual_surfaces` | `tamp_scene.py` 创建的 virtual surface / proxy。 |
| `surface_opening` | executor 看到的 release opening。 |
| `surface_opening.coordinate_frame` | opening 是 planner frame 还是 world frame。 |
| `inner_bounds_coordinate_frame` | virtual surface inner bounds 的声明帧。 |
| `place_candidates` | planner 收到的 place candidate 数量和范围。 |
| `collision_exclusions` | 被排除的 source / table / support collision。 |
| `planner_constraint_failures` | 规划失败时的主要约束。 |
| `success` | episode 最终是否成功。 |

这个报告用于回答：

1. grounding 命中了以后，geometry 是否也命中了？
2. adapter 是否把 semantic `inside` 编译到了正确 proxy？
3. planner world 是否真的创建了对应 surface？
4. release opening 和 planner surface 是否一致？

## 12. 坐标帧 / Adapter Parity 检查

geometry 静态或单元测试需要覆盖 frame contract，尤其是 desk-caddy 这类依赖 MuJoCo site 的
profile。

| 级别 | 检查项 |
| --- | --- |
| ERROR | `geometry["sites"]`、`metadata.sites`、`metadata.containment_sites` 没有和 `geoms` 一起转到 planner frame。 |
| ERROR | adapter 输出的 `inner_bounds` 与 problem 中 movable / surface pose 不同帧。 |
| ERROR | virtual surface metadata 缺少 `inner_bounds_coordinate_frame`。 |
| ERROR | executor 对已声明 `world` 的 opening 再次做 planner-to-world 转换。 |
| WARN | planner 用的 opening 和 executor release check 用的 opening 来自两套独立实现，缺少 parity 单测。 |

当前 desk-caddy 修复要求：planner problem、cuTAMP endpoint、executor opening 和 release guard
都基于同一套 pack adapter 产出的 bounds / metadata。不要在 executor 里重新按名字猜
`desk_caddy_*_contain_region` 的位置。

## 13. Evidence 检查

| 级别 | 检查项 |
| --- | --- |
| ERROR | 缺少 `evidence.tasks`。 |
| ERROR | 没有写明原始失败是 unknown surface、0/64、collision、pos_err 还是 release guard。 |
| ERROR | fixed region 缺少 BDDL 来源。 |
| ERROR | 需要 site / opening 的 skill 没有说明坐标帧来源。 |
| ERROR | collision exclude 缺少约束失败证据。 |
| WARN | 没有列出失败 run / episode。 |
| WARN | 没有说明配套 grounding skill。 |
| WARN | 没有说明不适用场景。 |
| WARN | 没有视觉或几何可视化检查记录。 |

## 14. 当前 Gate 状态和建议产物

当前 `run_skill_admission.py` 对 geometry 已执行 schema、capability registry 和 offline trigger
scan；专门的 geometry 类型静态 gate 仍是待补工具。后续可以新增：

```bash
python scripts/recovery/skill_pipeline/check_geometry_skills.py
```

建议输出：

- `geometry_static_gate_result.json`
- `geometry_static_gate_report.md`
- `geometry_canary_matches.csv`
- `geometry_trace_scan.csv`
- `geometry_problem_surface_scan.csv`

默认只有 ERROR 失败。WARN 写入报告，留给人工确认。
