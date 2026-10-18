---
id: geometry_wine_rack_top_region_low_surface
name: Wine rack top-region lower virtual surface
kind: recovery_hint
track: fail_only
scope: geometry
priority: 78
when_to_apply: 当 recovery 目标是把 cream cheese 放到 wine_rack_1_top_region，但上一轮 rack top
  虚拟面仍导致 cuTAMP `pos_err` 或 collision 无解时使用。
when_not_to_apply: 不用于 bowl、plate、stove、cabinet、tray、basket 或非 rack 放置任务。
failure_signature:
- W1 problem.json 中 `wine_rack_1_top_region` 已存在，但 half_extents 约为 [0.097, 0.024,
  0.003]，对 cream cheese 的短边只有很小余量。
- 同一 problem 的 rack place candidates 使用 z≈0.1085m，对应 `place_z_offset_m=0.095`，而 support_z≈0.0135m；这个高度更像
  executor hover，而不是 planner 的 On 目标。
- W1 stderr 多次出现 `KinematicConstraint pos_err <= 0.005 has 0/64 satisfying`，说明目标点本身对优化器过紧或过高。
recovery_point: During TAMP scene construction, after grounding has selected wine_rack_1_top_region.
applies_to:
  all:
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack
recovery_hints:
  params:
    geometry_hints:
      placement_region:
        intent: fixed_table_rect
        relation: 'on'
        surface_name: wine_rack_1_top_region
        region_name: wine_rack_1_top_region
        source_object: wine_rack_1_main
        source_site_name: wine_rack_1_top_region
        site_margin_m: 0.012
        min_half_extent_m: 0.04
        top_clearance_m: 0.004
        thickness_m: 0.006
        place_z_offset_m: 0.045
        exclude_source_collision: true
        surface_descriptor_shape: box
    source: libero_goal_task10_cream_cheese_rack_w1
evidence:
  tasks:
  - libero_goal_task task10 Put the cream cheese on the rack
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
---
这个 geometry hint 不改变目标绑定，仍然使用 `wine_rack_1_top_region`。它只把 rack top 的 planner 代理从上一轮的窄、高 hover 面改为略宽、较低的可放置面，以便 cuTAMP 先找到可满足的 On/IK 粒子。
