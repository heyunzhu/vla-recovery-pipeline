---
id: bowl_plate_target_approach_handoff
name: Bowl plate target approach handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 62
when_to_apply: In put-the-bowl-on-the-plate tasks, hand off once the VLA has committed
  to the parsed bowl target before it releases away from the plate.
when_not_to_apply: Do not use for cream cheese, flat boxes, mugs, cans, bottles, books,
  non-plate goals, or unrelated bowl tasks where the BDDL goal surface is not a plate.
failure_signature:
- LIBERO-PRO goal-swap task09 baseline and same-pack W0 are both 0/15 with no recovery
  calls.
- Query traces show most failures approach `akita_black_bowl_1_main` while the target
  is still static, then later release or carry it far from `plate_1_main`.
- Final target-to-plate XY errors are about 0.20-0.33 m, so the failure is the handoff
  before placement rather than target grounding.
recovery_point: Fire after the first legal q5 window when the target bowl is still
  static but the VLA path is already committed to the target-bowl approach neighborhood.
applies_to:
  all:
  - task_language_matches: bowl.*plate|plate.*bowl
  - target_name_matches: bowl
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - target_ee_distance_lt: 0.14
  - target_future_min_xy_distance_lt: 0.1
  - wrong_progress_target_static: true
  any:
  - nearest_pickable_is_target: true
  - intent_object_is_target: true
  - holding_status_is: holding
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_goal_swap_task09_seed51_65_w1
evidence:
  tasks:
  - 'libero_goal_swap task09: put the bowl on the plate'
  - libero_90 task09 put the bowl on the plate
  - libero_90 task05 put the bowl on top of the cabinet
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
  - task5_ep10_seed61
---
This repair skill supplies only the recovery entrypoint. It is intentionally tied to the parsed bowl target and plate goal surface, and it requires the target-static failure-evidence predicate so it does not become a generic early-delegation policy.
