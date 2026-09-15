---
id: task01_ignore_non_goal_static_context_for_plate
name: Task01 ignore non-goal static context for plate placement
kind: recovery_hint
track: pair
scope: collision_world
priority: 72
when_to_apply: When task01 recovery needs a Pick+Place plan for akita_black_bowl_2_main onto plate_1_main in the cluttered spatial scene.
when_not_to_apply: Do not apply to other bowls, other goal surfaces, or tasks where the ignored static objects are themselves targets or supports.
failure_signature:
  - Full static collision world produced no satisfying full-goal particles at forced q6.
  - Disabling static-context collisions produced a full Pick+Place executable plan in the q6 ablation.
recovery_point: During cuTAMP problem construction for the recovery call.
applies_to:
  all:
    - target_name_matches: "akita_black_bowl_2"
    - bddl_goal_surface_matches: "plate_1"
recovery_hints:
  params:
    collision_world_profile: task01_ignore_non_goal_static_context_for_plate_v1
evidence:
  tasks:
    - libero_spatial_task task01 pick the akita black bowl not between the plate and the ramekin and place it on the plate
  episodes:
    - forced_q6_empty_pack_seed71_73_n3
    - forced_q6_static_none_seed71_n1
---

## Intent

This hint records the ablation-backed collision-world choice as a named profile
instead of inlining executor options in the skill. It keeps target and goal
objects out of the ignore list, and relaxes only non-goal static clutter.
