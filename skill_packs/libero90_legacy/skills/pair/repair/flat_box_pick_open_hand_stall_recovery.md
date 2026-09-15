---
id: flat_box_pick_open_hand_stall_recovery
name: Flat-box target open-hand stall recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 69
when_to_apply: When the parsed target is a flat grocery box, the hand is still
  open and empty, the end effector is already close to the target, and the VLA
  stops making progress before a grasp.
when_not_to_apply: Do not use for bowls, mugs, cans, cartons, bottles, books,
  or when the nearest/intent object is clearly a non-target.
failure_signature:
  - The end effector stays within a few centimeters of the target for several
    queries with an open gripper.
  - The target object remains static, so the VLA has not started a useful pick.
  - Existing close-gripper stall repairs do not fire because the aperture never
    falls below their closed-gripper thresholds.
recovery_point: During the open-hand target approach, after the gripper has
  reached the target neighborhood but before the VLA disturbs the object.
applies_to:
  all:
    - target_name_matches: "chocolate_pudding|cream_cheese|cream cheese|butter|box"
    - target_name_excludes: "alphabet_soup|tomato_sauce|ketchup|milk|orange_juice|bowl|mug|cup|can|bottle|book"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - wrong_progress_target_static: true
    - target_ee_distance_lt: 0.09
    - nearest_pickable_is_target: true
    - ee_stalled:
        window: 4
        max_disp_m: 0.015
  any:
    - intent_object_is_target: true
    - target_future_min_xy_distance_lt: 0.10
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task62 pick up the chocolate pudding and put it in the tray
  episodes:
    - task62_wrong_object_progress_20260829 ep00 open-hand stall within 6cm of chocolate_pudding
---

## Intent

This repair catches flat-box target approaches where the VLA reaches the object
neighborhood but never closes or moves the target. It is intentionally separate
from the grasp hint: after it fires, `grasp_flat_box_topdown_short_side_deep`
supplies the actual flat-box grasp profile.
