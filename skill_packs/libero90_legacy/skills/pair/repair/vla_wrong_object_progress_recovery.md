---
id: vla_wrong_object_progress_recovery
name: VLA transported a wrong object instead of the parsed target
kind: repair
track: pair
hook: after_pi0_query
priority: 76
when_to_apply: When the parsed target remains essentially static, but another
  pickable object has clearly been transported toward the task goal or has
  become the sustained manipulated object.
when_not_to_apply: Do not use for tiny contact jitter, one-query trajectory
  flicker, or cases where the parsed target itself has already moved.
failure_signature:
  - The task target stays at its initial pose while a non-target object moves
    many centimeters.
  - The moved non-target object is the VLA intent object, is being held, remains
    near the gripper, or has been carried close to the parsed goal object.
  - The episode can look task-like because the wrong object is moved toward the
    correct basket, caddy, shelf, drawer, or other placement target.
recovery_point: After semantic wrong-object progress is detected, before the
  episode spends more time completing the task with the wrong object.
applies_to:
  all:
    - target_name_matches: ".+"
  any:
    - goal_name_matches: ".+"
    - bddl_goal_surface_matches: ".+"
trigger:
  all:
    - wrong_progress_target_static: true
    - wrong_progress_object_total_motion_gt: 0.06
  any:
    - vla_wrong_object_progress_status_is: wrong_object_at_goal
    - vla_wrong_object_progress_status_is: wrong_object_transported
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task50 pick up the tomato sauce and put it in the basket
    - libero_90 task51 pick up the alphabet soup and put it in the basket
  episodes:
    - online_skill_regression_tasks30_90_selected_20260829 task50 failures where alphabet_soup or cream_cheese moved while tomato_sauce stayed static
---

## Intent

This repair catches semantic wrong-object progress. It does not ask whether the
gripper is merely close to a distractor; it asks whether the parsed target has
remained static while a different pickable object has become the object being
transported toward the current task goal.

The runner computes this from object motion, VLA trajectory intent, holding
evidence, end-effector proximity, and the parsed goal object. Once fired, this
skill enters the normal `cutamp_recover` backend. Grasp, grounding, geometry,
and place hint skills still decide how to pick the parsed target and place it.
