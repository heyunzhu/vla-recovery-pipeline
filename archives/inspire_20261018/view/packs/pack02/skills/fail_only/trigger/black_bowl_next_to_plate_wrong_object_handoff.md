---
id: black_bowl_next_to_plate_wrong_object_handoff
name: Black bowl next-to-plate wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 71
when_to_apply: In the spatial task that asks for the akita black bowl next to the
  plate to be placed on the plate, hand off once the VLA has persistently aimed at
  the other akita black bowl, the gripper is still open, and the arm has moved into
  the q5-like recovery window without approaching the true BDDL target.
when_not_to_apply: Do not use for the not-between plate/ramekin task, generic bowl-on-plate
  tasks, white bowls, rack/cabinet/stove goals, or after the robot is already holding
  any object. Do not fire from target approach alone; require persistent wrong-object
  intent plus a target trajectory that remains far from the real target bowl.
failure_signature:
- Skills-off baseline for libero_spatial_task task3 seed51-65 was 2/15; W0 with the
  current cross-suite pack was 1/15.
- In W0, most failures never fired a skill. Query traces bind the BDDL target to akita_black_bowl_2_main,
  but the VLA intent object is akita_black_bowl_1_main with intent_object_is_target=false
  and large wrong_object_intent_margin_m.
- The first draft fired around q2 and failed admission because the admission gate
  requires a q5+ repair window and because rolling task3 success fragments would have
  been preempted.
- Threshold replay for this W1b predicate first fires no earlier than q5, avoids W0/baseline
  success episodes, and covers 13 of 14 W0 failed episodes.
- A 5-episode forced q5 probe on seeds 51-55 achieved 3/5 with the existing grasp_bowl_plate_hollow_rim_topdown
  hint and current place execution, supporting this safer handoff timing.
recovery_point: Fire at the q5-like wrong-object approach window, before the VLA closes
  on or transports the wrong bowl, so cuTAMP can own a full pick-place for akita_black_bowl_2_main.
applies_to:
  all:
  - task_language_matches: black bowl.*next to.*plate.*place.*plate|black bowl.*next
      to the plate.*on the plate|next to.*plate.*on the plate
  - target_name_matches: akita_black_bowl_2|black_bowl|bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.03
  - intent_min_xy_distance_lt: 0.085
  - target_future_min_xy_distance_gt: 0.12
  - target_ee_distance_lt: 0.33
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_spatial_task03_cross_suite_w1b_force_q5_probe
    notes: Reuses the already registered grasp_bowl_plate_hollow_rim_topdown hint;
      no new grasp or place profile is introduced in this write.
evidence:
  tasks:
  - 'libero_spatial_task task3: Pick the akita black bowl next to the plate and place
    it on the plate'
  - libero_90 task03 Pick the akita black bowl next to the plate and place it on the
    plate
  episodes:
  - task3_ep0_seed51_w0_first_fire_q5_success_in_probe
  - task3_ep1_seed52_w0_first_fire_q5_success_in_probe
  - task3_ep3_seed54_w0_first_fire_q6
  - task3_ep4_seed55_w0_first_fire_q5_success_in_probe
  - task3_ep5_seed56_w0_first_fire_q5
  - task3_ep6_seed57_w0_first_fire_q25
  - task3_ep7_seed58_w0_first_fire_q6
  - task3_ep8_seed59_w0_first_fire_q5
  - task3_ep9_seed60_w0_first_fire_q8
  - task3_ep10_seed61_w0_first_fire_q6
  - task3_ep11_seed62_w0_first_fire_q5
  - task3_ep13_seed64_w0_first_fire_q7
  - task3_ep14_seed65_w0_first_fire_q6
  - probe_force_q5_seed51_success
  - probe_force_q5_seed52_success
  - probe_force_q5_seed55_success
  - task3_ep0_seed51
  - task3_ep1_seed52
  - task3_ep3_seed54
  - task3_ep6_seed57
  - task3_ep7_seed58
  - task3_ep8_seed59
  - task3_ep9_seed60
  - task3_ep10_seed61
  - task3_ep13_seed64
  - task3_ep14_seed65
  - task3_ep4_seed55
  - task3_ep5_seed56
---
This trigger is deliberately narrower than the generic bowl-on-plate handoff and separate from the task1 not-between skill. It keys on task3 wording plus wrong-object intent diagnostics, delays until the q5+ admission-safe window, and lets the existing bowl-plate grasp/place hints choose the executable plan.
