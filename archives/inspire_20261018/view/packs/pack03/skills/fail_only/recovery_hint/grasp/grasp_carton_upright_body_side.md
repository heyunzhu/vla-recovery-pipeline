---
id: grasp_carton_upright_body_side
name: Upright carton body-side grasp, fingers parallel to the gable ridge
kind: recovery_hint
track: fail_only
scope: grasp
priority: 60
when_to_apply: When recovery must pick an upright milk or orange-juice carton (the object-basket tasks) and the generic top-down sampler closes on the narrowing gable roof instead of the flat body sides. Scope is target_name + orientation only, matching the repo's grasp canary contract; the trigger already establishes the basket task.
when_not_to_apply: Do not use for flat boxes, cans, bottles, bowls, cream cheese, butter, sauces
  or chocolate pudding, and not for a fallen or tilted carton.
failure_signature:
- Seeds 1-50 with the withdrawn tall-carton hint, and 51-55 before it, show the generic sampler
  placing its whole candidate set at one height, z = half_height - 0.02 = 0.1112 m, which is
  1.7 mm above the 0.1095 m body top and therefore on the gable slope.
- Failed attempts close through the carton (aperture 0.0033 m) while the object never leaves the
  table (object_lift_m ~ 1e-4 m); successful attempts clamp at aperture 0.0269 m and lift the
  carton 0.021 m.
- Diagonal arm orientations fail far more often than axis-aligned ones (13 of 15 diagonal picks),
  because a diagonal straddle needs ~7.4 cm across the 5.25 cm body.
recovery_point: After a matching wrong-object trigger enters recovery, sample top-down grasps on
  the flat body sides, below the shoulder, with the closing axis parallel to the gable ridge.
applies_to:
  all:
  - target_name_matches: milk|orange_juice|orange juice
  - target_orientation_is: upright
  - target_name_excludes: alphabet_soup|cream_cheese|salad_dressing|bbq_sauce|ketchup|tomato_sauce|butter|chocolate_pudding|basket
recovery_hints:
  grasp_profile: carton_upright_body_side_v1
  target: target
  params:
    source: supervisor_carton_profile_round_20260920
evidence:
  tasks:
  - 'libero_object_task task05: Pick the milk and place it in the basket'
  - 'libero_object_task task07: Pick the orange juice and place it in the basket'
  - 'libero_object_swap task08: Pick the milk and place it in the basket'
  - 'libero_object_swap task10: Pick the orange juice and place it in the basket'
  geometry:
  - 'assets/stable_hope_objects/milk/milk.xml: body box 0.0525 x 0.0525 x 0.1095 m, gable roof to 0.1312 m, ridge cap 5.9 mm'
  episodes:
  - codex_validation_cartonrevert/libero_object_task_object_task_carton_revert_seed1_50/task05 (38/50)
  - codex_validation_cartonrevert/libero_object_swap_object_swap_carton_revert_seed1_50/task08 (23/50)
---
This hint changes only the grasp sampling for upright cartons: it adds height bands on the body and
pins the closing axis parallel to the gable ridge. Triggers, placement and the flat-box profile are
untouched. Height fractions are a module constant in code/grasp_profiles.py
(`CARTON_GRASP_HEIGHT_FRACTIONS`) so they can be swept as separate trial packs.
