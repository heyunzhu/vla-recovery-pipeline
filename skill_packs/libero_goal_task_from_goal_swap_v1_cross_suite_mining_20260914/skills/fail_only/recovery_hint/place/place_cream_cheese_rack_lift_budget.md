---
id: place_cream_cheese_rack_lift_budget
name: Cream cheese rack place lift budget
kind: recovery_hint
track: fail_only
scope: place
priority: 76
when_to_apply: 当 cream cheese 已由 recovery 抓起并要放到 wine_rack_1_top_region，且 rack 周围容易因低空转移或
  release 前对齐不足而失败时使用。
when_not_to_apply: 不用于非 rack 放置任务；不用于 grasp/grounding 尚未解决、planner 仍完全没有 satisfying
  particle 的情形。
failure_signature:
- W1 的主要失败在 planner/pick，但 ep03 已经出现过 Pick 轨迹并在执行阶段 stalled；一旦浅抓取和低 rack surface 产生可行解，需要给后续
  lift/hover/drop 留足 executor 步数。
- rack top region 比普通桌面更窄，place 阶段需要先抬升再水平移动，避免 cream cheese 或夹爪低空扫过 rack/邻近物。
recovery_point: After successful recovery pick and before final rack release.
applies_to:
  all:
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack
recovery_hints:
  params:
    executor:
      place_lift_max_steps: 60
      place_lift_reached_m: 0.014
      place_lift_min_clearance_m: 0.035
      place_hover_clearance_m: 0.065
      place_hover_max_steps: 80
      place_hover_reached_m: 0.018
      place_drop_max_steps: 110
      place_drop_reached_m: 0.02
      place_release_z_max_m: 0.095
      place_open_dwell_steps: 8
    source: libero_goal_task10_cream_cheese_rack_w1
evidence:
  tasks:
  - libero_goal_task task10 Put the cream cheese on the rack
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - task10_ep3_seed54_q20
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
---
这个 place hint 只使用当前 capability registry 已注册的 executor options。它不是新的 place policy；它给 rack 放置阶段更多 lift/hover/drop 预算，和本轮的浅抓取、低 rack 虚拟面一起使用。
