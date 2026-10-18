---
id: bowl_plate_pick_lost_or_wrong_intent
name: Bowl plate pregrasp handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 55
when_to_apply: In bowl-on-plate placement tasks, hand off to cuTAMP when the VLA has
  entered a close target approach window but still reports an open pick state, before
  it closes on the bowl or creates a hard-to-plan holding pose.
when_not_to_apply: Do not use outside bowl-to-plate placement tasks. Do not use before
  the arm has clearly approached the target bowl. Do not use after a confirmed holding
  state; at that point this skill is too late and tends to force cuTAMP into a hard
  MoveHolding-only repair.
failure_signature:
- W1 validation on LIBERO-PRO goal-swap task09 reached only 1/5 before stopping.
- The only successful W1 episode fired at q5 with an open empty hand and let cuTAMP
  generate a full MoveFree/Pick/MoveHolding/Place plan.
- Failed W1 episodes mostly fired at q18-q21 after the bowl was already held or after
  the VLA had produced an unstable grasp, causing cuTAMP to optimize MoveHolding/Place
  from a bad current pose.
- Failed cuTAMP attempts still had satisfying particles, but cuRobo motion planning
  failed for all satisfying particles or execution stalled on the pick trajectory.
- On the W0 traces, the revised open-pick approach trigger covers 14/15 failed episodes
  without firing before q5.
recovery_point: Fire at the first clean approach window after q5-like evidence, while
  the gripper is still open, the runner still reports handempty or unconfirmed holding,
  and `vla_pick_target_status` is still `open`. This asks cuTAMP to own the complete
  pick-place sequence.
applies_to:
  all:
  - task_language_matches: bowl.*plate|plate.*bowl
  - target_name_matches: akita_black_bowl|black_bowl|bowl
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - vla_pick_target_status_is: open
  - target_ee_distance_lt: 0.16
  - target_future_min_xy_distance_lt: 0.08
recovery_hints:
  params:
    source: libero_goal_swap_task09_seed51_65_w2
evidence:
  tasks:
  - 'libero_goal_swap task09: put the bowl on the plate'
  - libero_90 task09 put the bowl on the plate
  - libero_90 task01 Pick the akita black bowl not between the plate and the ramekin
    and place it on the plate
  - libero_90 task03 Pick the akita black bowl next to the plate and place it on the
    plate
  - libero_90 task05 Pick the akita black bowl on the top of the wooden cabinet and
    place it on the plate
  episodes:
  - task09_seed51_w1_ep00_q5_counterfactual
  - task09_seed52_w1_ep01_q5_success
  - task09_seed53_w1_ep02_q5_counterfactual
  - task09_seed54_w1_ep03_q5_counterfactual
  - task09_seed55_w1_ep04_q5_counterfactual
  - task09_seed56_w1_ep05_q6_counterfactual
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
  - task1_ep4_seed55
  - task1_ep5_seed56
  - task3_ep6_seed57
  - task5_ep14_seed65
---
This repair skill intentionally fires before a bad grasp exists, but only after
the runner has evidence that the VLA is still in an open-pick state inside the
target approach window. It uses only generic runner state fields, so the scratch
pack remains isolated from the LIBERO-90 legacy skill implementation.
