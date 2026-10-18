---
id: grasp_goal_swap_black_bowl_cabinet_rim_topdown
name: Goal-swap black bowl cabinet rim top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 51
when_to_apply: When recovery manipulates the black bowl target for a bowl-on-cabinet-top
  goal-swap task.
when_not_to_apply: Do not use for cream cheese, wine bottles, white bowls, mugs, cartons,
  flat boxes, books, baskets, trays, plates, or non-cabinet-top goals.
failure_signature:
- Task05 W0 never invoked recovery, but query traces show the parsed target is the
  black bowl and failures happen after or near target pick.
- A controlled recovery pick/regain should use the same diagonal rim top-down bowl
  profile that was already admitted for goal-swap bowl manipulation.
recovery_point: After the repair entrypoint starts `cutamp_recover`, bias cuTAMP toward
  diagonal top-down rim candidates on the target bowl.
applies_to:
  all:
  - task_language_matches: bowl.*cabinet|cabinet.*bowl
  - target_name_matches: bowl
  - target_name_excludes: white_bowl
  - bddl_goal_surface_matches: cabinet|cabinet_top|wooden_cabinet.*cabinet_top
recovery_hints:
  grasp_profile: goal_swap_black_bowl_rim_diagonal_topdown_v1
  target: target
  params:
    source: libero_goal_swap_task05_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task05: put the bowl on top of the cabinet'
  - libero_90 task05 put the bowl on top of the cabinet
  episodes:
  - task5_ep0_seed51
  - task5_ep1_seed52
  - task5_ep2_seed53
  - task5_ep3_seed54
  - task5_ep4_seed55
  - task5_ep5_seed56
  - task5_ep6_seed57
  - task5_ep7_seed58
  - task5_ep8_seed59
  - task5_ep9_seed60
  - task5_ep10_seed61
  - task5_ep11_seed62
  - task5_ep12_seed63
  - task5_ep13_seed64
  - task5_ep14_seed65
---
This hint reuses the existing pack-local bowl grasp profile; it adds no new sampler code.
