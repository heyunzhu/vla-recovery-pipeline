---
id: black_bowl_cabinet_top_to_plate_wrong_object_handoff
name: Black bowl cabinet-top to plate wrong-object handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 72
when_to_apply: In the spatial task that asks for the akita black bowl on the top of
  the cabinet to be placed on the plate, hand off once the VLA has persistently aimed
  at the other akita black bowl while the true BDDL target remains on the cabinet
  top and away from the gripper.
when_not_to_apply: Do not use for cabinet-top placement goals, not-between or next-to-plate
  variants, generic bowl-on-plate tasks without cabinet-top wording, white bowls,
  cream-cheese tasks, rack/stove/cabinet-goal tasks, or after the robot is already
  holding any object. Do not fire from target approach alone; require persistent wrong-object
  intent and a still-far true target.
failure_signature:
- Skills-off baseline for libero_spatial_task task4 seed51-65 was 0/15; W0 with the
  current cross-suite pack was also 0/15.
- W0 query traces bind the BDDL target to akita_black_bowl_2_main and the goal to
  plate_1_main, with the target initially on wooden_cabinet_1_cabinet_top.
- In all W0 failures the VLA intent object is akita_black_bowl_1_main, intent_object_is_target=false,
  nearest_pickable_is_target=false, wrong_object_intent_margin_m is high, and wrong_progress_target_static
  remains true.
- The existing bowl_plate_pick_lost_or_wrong_intent trigger applies to the task but
  requires target approach; it never fires because the VLA is approaching the wrong
  bowl while the true target remains far.
- A 5-episode forced q5 probe on seeds 51-55 achieved 5/5 with the existing grasp_bowl_plate_hollow_rim_topdown
  hint and current plate placement path, proving no new grasp, geometry, or place
  profile is required for this write.
recovery_point: Fire in the q5+ wrong-object intent window, before the VLA spends
  the rollout moving the wrong bowl near the plate, so cuTAMP can own the full pick-place
  for akita_black_bowl_2_main from the cabinet top to plate_1_main.
applies_to:
  all:
  - task_language_matches: black bowl.*(?:on|top).*cabinet.*plate|black bowl.*cabinet.*plate|on
      the top of the cabinet.*place.*plate
  - target_name_matches: akita_black_bowl_2|black_bowl|bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - intent_object_is_target: false
  - nearest_pickable_is_target: false
  - wrong_progress_target_static: true
  - wrong_object_intent_persist_queries_gte: 4
  - wrong_object_intent_margin_gt: 0.1
  - intent_min_xy_distance_lt: 0.12
  - target_future_min_xy_distance_gt: 0.18
  - target_ee_distance_gt: 0.18
recovery_hints:
  params:
    repair_profile: entry_lift_open_hand_small_v1
    source: libero_spatial_task04_cross_suite_w1_force_q5_probe
    notes: Reuses the existing grasp_bowl_plate_hollow_rim_topdown hint and current
      plate placement path; no new grasp, geometry, grounding, collision-world, or
      place profile is introduced in this write.
evidence:
  tasks:
  - '{''libero_spatial_task task4'': ''Pick the akita black bowl on the top of the
    cabinet and place it on the plate''}'
  - libero_90 task04 Pick the akita black bowl on the top of the cabinet and place
    it on the plate
  episodes:
  - task4_ep0_seed51_w0_first_fire_q5_success_in_probe
  - task4_ep1_seed52_w0_first_fire_q5_success_in_probe
  - task4_ep2_seed53_w0_first_fire_q6_success_in_probe
  - task4_ep3_seed54_w0_first_fire_q5_success_in_probe
  - task4_ep4_seed55_w0_first_fire_q10_success_in_probe
  - task4_ep5_seed56_w0_first_fire_q5
  - task4_ep6_seed57_w0_first_fire_q5
  - task4_ep7_seed58_w0_first_fire_q5
  - task4_ep8_seed59_w0_first_fire_q7
  - task4_ep9_seed60_w0_first_fire_q11
  - task4_ep10_seed61_w0_first_fire_q10
  - task4_ep11_seed62_w0_first_fire_q6
  - task4_ep12_seed63_w0_first_fire_q9
  - task4_ep13_seed64_w0_first_fire_q8
  - task4_ep14_seed65_w0_first_fire_q6
  - probe_force_q5_seed51_success
  - probe_force_q5_seed52_success
  - probe_force_q5_seed53_success
  - probe_force_q5_seed54_success
  - probe_force_q5_seed55_success
  - task4_ep0_seed51
  - task4_ep1_seed52
  - task4_ep2_seed53
  - task4_ep3_seed54
  - task4_ep4_seed55
  - task4_ep5_seed56
  - task4_ep6_seed57
  - task4_ep7_seed58
  - task4_ep8_seed59
  - task4_ep9_seed60
  - task4_ep10_seed61
  - task4_ep11_seed62
  - task4_ep12_seed63
  - task4_ep13_seed64
  - task4_ep14_seed65
---
This trigger is deliberately separate from the cabinet-top placement trigger and the task1/task3 black-bowl variants. It keys on cabinet-top-to-plate wording plus wrong-object intent, while the BDDL goal surface remains the plate.
