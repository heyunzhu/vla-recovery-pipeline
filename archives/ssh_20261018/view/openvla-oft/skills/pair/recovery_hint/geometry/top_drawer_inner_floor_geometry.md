---
id: top_drawer_inner_floor_geometry
name: Top drawer inner-floor geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 45
when_to_apply: When an already-triggered recovery must place an object inside the top drawer of a cabinet.
when_not_to_apply: Do not use for cabinet-top placement, middle drawers, bottom drawers, closing drawers, handles, doors, or non-drawer containers.
failure_signature:
  - The top drawer container may be a valid semantic goal but not a directly executable place_in target.
  - Recovery should expose an inner-floor placement proxy so existing place_on planning can target the drawer interior.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "top drawer.*cabinet|cabinet.*top drawer"
recovery_hints:
  params:
    geometry_profile: top_drawer_inner_floor_geometry_v1
evidence:
  tasks:
    - libero_90 task33 put the ketchup in the top drawer of the cabinet
  episodes:
    - gpu1_selected_online_mining_clean_task33_20260823
---

## Intent

This policy contributes only planner geometry. It creates a virtual
`*_inner_floor` support surface inside the grounded top drawer and compiles the
inside placement into a place-on-inner-floor recovery goal.

It does not decide when to recover, does not bind the semantic target by itself,
and does not implement a new `place_in` executor.
