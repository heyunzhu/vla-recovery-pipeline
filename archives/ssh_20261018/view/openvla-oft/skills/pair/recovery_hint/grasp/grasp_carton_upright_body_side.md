---
id: grasp_carton_upright_body_side
name: Carton upright body-side grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 58
when_to_apply: When recovery is manipulating an upright HOPE drink carton such as milk or orange juice.
when_not_to_apply: Do not use after the carton has been knocked down, or for cans, flat boxes, bowls, mugs, baskets, and trays.
failure_signature:
  - Milk or orange juice recovery needs a body grasp but default or old carton profiles close across the gable ridge and slip.
  - The target carton remains upright according to simulator pose.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "milk|orange_juice|orange juice|juice|carton"
    - target_name_excludes: "cream_cheese|butter|alphabet_soup|tomato_sauce|ketchup|bowl|mug|can"
    - target_orientation_is: upright
recovery_hints:
  grasp_profile: carton_upright_body_side_v1
  target: target
  params:
    source: task53_milk_gable_rotated_grasp_analysis_20260824
evidence:
  tasks:
    - libero_90 task53 pick up the milk and put it in the basket
    - libero_90 task54 pick up the orange juice and put it in the basket
  episodes:
    - online_skill_regression_task53_wrong_object_intent_20260824
---

## Intent

This skill selects a conservative top-down body grasp for upright HOPE drink
cartons. LIBERO milk and orange juice have a gable ridge near the top; closing
across that ridge can slip without lifting the carton. The sampler therefore
keeps the simple upright body samples and applies a 90-degree yaw rotation so
the fingers close on the carton side walls instead of the ridge.

It only contributes a grasp profile. Recovery timing, target binding, and
inside-basket geometry remain separate skills.
