---
id: grasp_cream_cheese_rack_flat_box_priority
name: Cream cheese rack flat-box priority grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 84
when_to_apply: 当 cream-cheese-to-rack recovery 已经触发，rack top-region grounding/geometry
  已进入 hints，但 `libero_topdown` grasp 让 cuTAMP 在 Pick 阶段出现 0/64 satisfying 时使用。
when_not_to_apply: 不用于 bowl、plate、wine bottle、rack 本体、非 cream cheese 目标，或已经成功 holding
  cream cheese 只剩 place/release 调参的情形。
failure_signature:
- W2 的 20 个 cutamp_debug solve 全部是 `num_satisfying = 0` 和 `No satisfying particles
  found after optimizing all 1 plan(s)`。
- query trace 的 `hint_conflicts` 明确记录 `grasp_profile` 从 `cream_cheese_flat_box_topdown_deep_v1`
  被高优先级 hint 覆盖为 `libero_topdown`。
- representative problem 已经有 `on(cream_cheese_1_main, wine_rack_1_top_region)` 和 virtual
  `wine_rack_1_top_region` surface，因此本轮主要不是 grounding/geometry 未生效。
- stderr 中每个 solve 都出现 `[KinematicConstraint] pos_err <= 0.005 has 0/64 satisfying`，并且
  `plan_summary` 为空，说明 Pick pose/IK 在进入可执行 plan 前失败。
recovery_point: After a repair/trigger skill has already decided to call recovery,
  before cuTAMP samples the Pick grasp candidates.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack|top_region
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deep_v1
  target: target
  params:
    source: libero_goal_task10_cream_cheese_rack_w2_flat_box_priority
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
---
这个 hint 不新增 grasp sampler，只把已经验证过的 `cream_cheese_flat_box_topdown_deep_v1` 提升到 rack 场景的最高优先级。W2 里 rack top-region goal 和 virtual surface 已经正确进入 cuTAMP；现在需要避免 `libero_topdown` 的中心 top-down 候选继续压过 flat-box/deep 候选，把 Pick IK 卡死在 `pos_err` 和 `robot_to_world`。
