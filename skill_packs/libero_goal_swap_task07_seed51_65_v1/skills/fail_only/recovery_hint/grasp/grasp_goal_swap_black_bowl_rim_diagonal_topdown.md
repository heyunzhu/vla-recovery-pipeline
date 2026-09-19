---
id: grasp_goal_swap_black_bowl_rim_diagonal_topdown
name: Goal-swap black bowl rim diagonal top-down grasp
kind: recovery_hint
track: fail_only
scope: grasp
priority: 50
when_to_apply: When recovery is manipulating the black bowl target for a bowl-on-plate
  goal-swap task.
when_not_to_apply: Do not use for cream cheese, wine bottles, white bowls, mugs, cartons,
  flat boxes, books, baskets, trays, or non-plate goals.
failure_signature:
- Task09 W0 never invoked recovery, so cuTAMP did not get a chance to pick/place the
  bowl.
- Several failed episodes already contact or hold the black bowl, but the VLA release
  is far from the plate; recovery should produce a controlled bowl pick if handoff
  occurs before stable holding.
recovery_point: After the repair entrypoint enters `cutamp_recover`, bias cuTAMP toward
  diagonal top-down rim candidates on the target bowl.
applies_to:
  all:
  - task_language_matches: bowl.*plate|plate.*bowl
  - target_name_matches: bowl
  - target_name_excludes: white_bowl
  - bddl_goal_surface_matches: plate
recovery_hints:
  grasp_profile: goal_swap_black_bowl_rim_diagonal_topdown_v1
  target: target
  params:
    source: libero_goal_swap_task09_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task09: put the bowl on the plate'
  - libero_90 task09 put the bowl on the plate
  episodes:
  - task09_seed51_ep00
  - task09_seed52_ep01
  - task09_seed53_ep02
  - task09_seed54_ep03
  - task09_seed55_ep04
  - task09_seed56_ep05
  - task09_seed57_ep06
  - task09_seed58_ep07
  - task09_seed59_ep08
  - task09_seed60_ep09
  - task09_seed61_ep10
  - task09_seed62_ep11
  - task09_seed63_ep12
  - task09_seed64_ep13
  - task09_seed65_ep14
  - task9_ep0_seed51
  - task9_ep1_seed52
  - task9_ep2_seed53
  - task9_ep3_seed54
  - task9_ep4_seed55
  - task9_ep5_seed56
  - task9_ep6_seed57
  - task9_ep7_seed58
  - task9_ep8_seed59
  - task9_ep9_seed60
  - task9_ep10_seed61
  - task9_ep11_seed62
  - task9_ep12_seed63
  - task9_ep13_seed64
  - task9_ep14_seed65
---
This hint is pack-local and owns only the target-bowl grasp sampler. Goal grounding and plate geometry remain the parsed BDDL defaults.
