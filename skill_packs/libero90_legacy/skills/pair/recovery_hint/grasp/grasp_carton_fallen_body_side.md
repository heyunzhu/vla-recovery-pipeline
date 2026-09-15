---
id: grasp_carton_fallen_body_side
name: Carton fallen body-side grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 59
when_to_apply: When recovery is manipulating a HOPE drink carton such as milk or orange juice after it has been knocked down.
when_not_to_apply: Do not use for upright cartons or for non-carton objects.
failure_signature:
  - The target carton has been bumped and its semantic upright axis is mostly horizontal.
  - Recovery should grasp the fallen carton in place instead of assuming the upright body profile.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "milk|orange_juice|orange juice|juice|carton"
    - target_name_excludes: "cream_cheese|butter|alphabet_soup|tomato_sauce|ketchup|bowl|mug|can"
    - target_orientation_is: fallen
recovery_hints:
  grasp_profile: carton_fallen_body_side_v1
  target: target
  params:
    source: task53_milk_asset_geometry_analysis_20260824
evidence:
  tasks:
    - libero_90 task53 pick up the milk and put it in the basket
    - libero_90 task54 pick up the orange juice and put it in the basket
  episodes:
    - online_skill_regression_task53_wrong_object_intent_20260824
---

## Intent

This skill selects a top-down grasp along the horizontal long axis of a fallen
HOPE drink carton. It assumes the carton should be picked from its current
fallen pose, not reoriented first.

It only contributes a grasp profile. Recovery timing, target binding, and
inside-basket geometry remain separate skills.
