---
id: plate_stove_open_wrong_intent_pregrasp_handoff
name: Plate stove open-hand wrong-intent handoff
kind: trigger
track: fail_only
hook: after_pi0_query
backend: cutamp_recover
priority: 74
when_to_apply: When the task is plate-on-stove and the VLA has a stable wrong-object
  intent while the gripper is still open and no object is confirmed held, hand off
  before the VLA closes on the black bowl.
when_not_to_apply: Do not use after confirmed holding, after the gripper has already
  mostly closed, outside plate-to-stove tasks, or when the target plate is already
  the nearest/intent object.
failure_signature:
- >-
  W3 fixed the stove cook-region grounding and geometry, and all 15 same-init
  episodes triggered recovery, but success stayed 0/15 with a healthy runner.
- >-
  Recovery at q9-q11 was too late: the optimized cuTAMP plans often first tried
  MoveHolding/Place for akita_black_bowl_1_main before plate pick-place, because
  the VLA had already committed to the wrong bowl.
- >-
  Query traces show a clean earlier window at q5-q6 in all 15 W3 failures: open
  gripper, handempty_or_unconfirmed, persistent wrong-object intent, target plate
  still not the nearest pickable, and the arm close enough for a purposeful
  handoff but not yet closed.
recovery_point: Fire in the open-hand pregrasp window so cuTAMP owns the complete
  MoveFree/Pick/MoveHolding/Place sequence for plate_1_main to the stove cook region.
applies_to:
  all:
  - task_language_matches: plate.*stove|stove.*plate
  - target_name_matches: plate
  - bddl_goal_surface_matches: flat_stove|stove|cook_region
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - aperture_gt: 0.025
  - vla_pick_target_status_is: open
  - intent_object_is_target: false
  - wrong_object_intent_persist_queries_gte: 4
  - nearest_pickable_is_target: false
  - target_ee_distance_gt: 0.12
  - target_ee_distance_lt: 0.22
  - nearest_pickable_distance_lt: 0.20
recovery_hints:
  params:
    source: libero_goal_task02_plate_stove_pregrasp_w4
evidence:
  tasks:
  - 'libero_goal_task task02: Put the plate on the stove'
  episodes:
  - task2_ep0_seed51_q5
  - task2_ep1_seed52_q5
  - task2_ep2_seed53_q5
  - task2_ep3_seed54_q5
  - task2_ep4_seed55_q5
  - task2_ep5_seed56_q5
  - task2_ep6_seed57_q5
  - task2_ep7_seed58_q5
  - task2_ep8_seed59_q6
  - task2_ep9_seed60_q6
  - task2_ep10_seed61_q5
  - task2_ep11_seed62_q5
  - task2_ep12_seed63_q5
  - task2_ep13_seed64_q6
  - task2_ep14_seed65_q5
---
This trigger is intentionally earlier than `plate_stove_wrong_bowl_pick_handoff`.
It does not add new planner behavior; it prevents recovery from entering with a
wrong bowl already held, which forced W3 into hard MoveHolding/Place repairs for
the non-target object.
