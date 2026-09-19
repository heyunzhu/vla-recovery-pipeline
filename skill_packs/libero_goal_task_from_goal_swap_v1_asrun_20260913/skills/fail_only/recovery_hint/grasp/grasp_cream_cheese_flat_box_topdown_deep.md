---
id: grasp_cream_cheese_flat_box_topdown_deep
name: Cream cheese flat-box top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 73
when_to_apply: 当 recovery 已经由 cream-cheese-to-rack 的 wrong-object trigger 介入，需要为扁平
  cream cheese 盒子生成稳定 top-down pick 候选时使用。
when_not_to_apply: 不用于 bowl、plate、wine bottle、rack 本体或非 cream cheese 目标；也不用于目标已被稳定
  holding、只剩放置或 release 问题的情形。
failure_signature:
- 当前失败在 recovery 前就偏向 bowl 或 wine bottle，尚无 cuTAMP pick 约束记录；但目标物体是扁平 cream cheese
  盒子，默认/native grasp 容易给出过浅或居中不足的抓取候选。
- active capability registry 已注册 `cream_cheese_flat_box_topdown_deep_v1`，该 profile
  是 pack-local grasp adapter 支持的 flat-box top-down/deep grasp，不需要新增代码能力。
- 与 entrypoint 配套后，cutamp_recover 可以从正确目标的 flat-box grasp 开始生成 Pick/MoveHolding/Place，而不是沿用
  VLA 的非目标 intent。
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
  - target_name_matches: cream_cheese
  - goal_name_matches: wine_rack|rack
  - bddl_goal_surface_matches: wine_rack|rack
recovery_hints:
  grasp_profile: cream_cheese_flat_box_topdown_deep_v1
  target: target
  params:
    source: libero_goal_task10_cream_cheese_rack_wrong_object_w0
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
这个 hint 只引用已注册的 `cream_cheese_flat_box_topdown_deep_v1`，不改变 trigger、grounding、geometry 或 place policy。它的作用是让 recovery 在接管后优先用适合扁平 cream cheese 盒子的 grasp profile，而不是继续受错误 VLA intent 影响。
