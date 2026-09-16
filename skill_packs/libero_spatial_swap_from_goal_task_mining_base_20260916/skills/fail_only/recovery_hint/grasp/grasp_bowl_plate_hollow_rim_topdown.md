---
id: grasp_bowl_plate_hollow_rim_topdown
name: Bowl plate hollow rim topdown grasp
kind: recovery_hint
scope: grasp
track: fail_only
priority: 25
when_to_apply: Use with bowl-on-plate recovery when cuTAMP is asked to recover the
  target black bowl before placing it on a plate.
when_not_to_apply: Do not use for white or shallow bowls, mugs, bottles, cartons,
  boxes, or non-plate goals.
failure_signature:
- The current task09 traces approach a hollow bowl-like object, and the default object-center
  top-down grasp is less appropriate than a rim-biased top-down grasp.
- W1 showed that a clean early cuTAMP handoff can execute a full Pick/Place plan when
  the grasp hint is active.
recovery_point: When a matching repair entrypoint fires, prefer the core hollow-bowl
  rim top-down sampler for the target bowl.
applies_to:
  all:
  - task_language_matches: bowl.*plate|plate.*bowl
  - target_name_matches: akita_black_bowl|black_bowl|bowl
  - target_name_excludes: white_bowl|white bowl
  - bddl_goal_surface_matches: plate
recovery_hints:
  grasp_profile: hollow_bowl_rim_topdown
  target: target
  params:
    source: libero_goal_swap_task09_seed51_65_w2
evidence:
  tasks:
  - 'libero_goal_swap task09: put the bowl on the plate'
  - libero_90 task09 put the bowl on the plate
  episodes:
  - task09_seed51_w1_ep00
  - task09_seed52_w1_ep01
  - task09_seed53_w1_ep02
  - task09_seed54_w1_ep03
  - task09_seed55_w1_ep04
  - task09_seed51
  - task09_seed52
  - task09_seed53
  - task09_seed54
  - task09_seed55
  - task09_seed56
  - task09_seed57
  - task09_seed58
  - task09_seed59
  - task09_seed60
  - task09_seed61
  - task09_seed62
  - task09_seed63
  - task09_seed64
  - task09_seed65
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
This hint keeps the object-specific pick policy separate from the repair timing.
It uses the core `hollow_bowl_rim_topdown` profile and does not depend on the
LIBERO-90 legacy grasp adapter.
