---
id: book_caddy_pick_approach_recovery
name: Book-to-caddy early pick approach recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 74
when_to_apply: A book-to-desk-caddy compartment task is still before a confirmed
  grasp, the gripper is open and empty, the parsed book is the nearest pickable
  object, and the end effector has approached close enough that cuTAMP can take
  over before the VLA knocks the book into a late empty-close failure.
when_not_to_apply: Do not use for bowls, grocery boxes, mugs, drawer tasks, or
  generic caddy placement without a named front/back/left/right compartment.
failure_signature:
  - Forced early recovery on task74 could pick the book and produce feasible
    book-to-caddy plans, while late online recovery fired through a bowl stall
    repair and often failed before lifting the book.
  - In failed task74 online runs, the target book was already the nearest
    pickable object during the approach, but the generic bowl empty-close
    trigger waited until q13-q16.
recovery_point: During the open-hand approach to the parsed book, before the
  first empty closed-gripper stall or late VLA disturbance.
applies_to:
  all:
    - task_language_matches: "(front|back|left|right) compartment.*caddy|caddy.*(front|back|left|right) compartment"
    - target_name_matches: "book|black_book"
    - goal_name_matches: "desk_caddy|caddy"
    - bddl_goal_surface_matches:
        - "*desk_caddy*_*_contain_region"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - nearest_pickable_is_target: true
    - target_ee_distance_lt: 0.29
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task74 pick up the book and place it in the front compartment of the caddy
    - libero_90 task75 pick up the book and place it in the left compartment of the caddy
  episodes:
    - task74_two_site_geometry_20260828 force_recovery_query=5
    - online_skill_regression_tasks74_80_footprint_tol1mm_20260828 task74 late bowl-stall misfire
---

## Intent

This skill only decides when to enter the existing `cutamp_recover` backend for
book-to-desk-caddy compartment tasks. It intentionally carries no grasp,
grounding, geometry, or executor entry hints. Those remain owned by
`grasp_book_upright_topdown`, `desk_caddy_compartment_grounding`,
`desk_caddy_compartment_geometry`, and `place_caddy_held_object_xy_align`.

The trigger captures the useful part of the previous forced-q5 ablation without
hard-coding a query index: the hand is still empty and open, the parsed book is
the nearest pickable object, and the approach has reached the neighborhood where
the recovery planner can start from a clean state.
