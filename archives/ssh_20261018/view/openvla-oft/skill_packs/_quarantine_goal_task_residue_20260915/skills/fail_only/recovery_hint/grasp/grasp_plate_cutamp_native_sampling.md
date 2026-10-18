---
id: grasp_plate_cutamp_native_sampling
name: Plate native cuTAMP grasp sampling
kind: recovery_hint
track: fail_only
scope: grasp
priority: 34
when_to_apply: 当已有 plate_stove_wrong_bowl_pick_handoff 触发，目标是 plate_1_main，任务是把 plate
  放到 stove / cook_region，且默认 top-down plate grasp 导致 planner 无可行解或 close/lift 后未确认持有时使用。
when_not_to_apply: 不用于 bowl-on-plate、box、bottle、cabinet、drawer 或目标物不是 plate 的任务；也不用于已经明确是
  place release / hover 失败的情形。
failure_signature:
- w1 中已有 repair entrypoint 在错误对象意图持续后触发，说明入口时机不是主要缺口。
- 13/15 个验证 episode 在 cutamp_recover 规划阶段返回 real_cutamp_no_feasible_goal，没有进入 executor
  pick/place。
- ep02 和 ep08 进入过 Pick(plate_1_main, grasp1, q1)，但 close/lift 记录 gripper_closed_but_not_holding
  或 lift_probe_unconfirmed。
- default 在当前采样链中等价于 libero_topdown，薄 plate 的中心 top-down 抓取对闭合和抬升确认不稳定。
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
recovery_hints:
  grasp_profile: cutamp_native
  target: target
  params:
    source: libero_goal_task_task02_seed51_65_w1
evidence:
  tasks:
  - libero_90 task02 Put the plate on the stove
  episodes:
  - task2_ep0_seed51
  - task2_ep1_seed52
  - task2_ep2_seed53
  - task2_ep3_seed54
  - task2_ep4_seed55
  - task2_ep5_seed56
  - task2_ep6_seed57
  - task2_ep7_seed58
  - task2_ep8_seed59
  - task2_ep9_seed60
  - task2_ep10_seed61
  - task2_ep11_seed62
  - task2_ep12_seed63
  - task2_ep13_seed64
  - task2_ep14_seed65
---
这个 hint 不改变 repair 触发逻辑，只把已注册的 `cutamp_native` 抓取采样交给 `cutamp_recover`。证据显示默认 top-down plate grasp 既会让大多数 episode 在规划阶段找不到可行解，也会在少数可执行 pick 中闭合后无法确认 plate 跟随抬升。

如果 `cutamp_native` 仍然不能让 same-init 验证越过 3/5，下一步不要继续调触发器，应补一个真正的 plate edge / thin object grasp profile，或先解决 stove `cook_region` 到 planner surface 的 geometry/grounding 表达。
