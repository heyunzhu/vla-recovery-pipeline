---
id: container_inside_region
name: Container inside-region geometry
kind: recovery_hint
track: pair
scope: geometry
priority: 44
when_to_apply: When an already-triggered recovery must place an object inside a non-articulated open container such as a basket.
when_not_to_apply: Do not use for cabinet drawers, microwaves, cabinet-top placement, plates, trays, or open/close manipulation.
failure_signature:
  - The semantic goal is inside(obj, container), but native cuTAMP place_in is not executable in the current pipeline.
  - Recovery should expose an inner-floor placement proxy and avoid treating the target container walls as blocking the target approach.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "\\b(in|inside|into)\\b|basket|container"
    - goal_name_matches: "basket|container"
recovery_hints:
  params:
    geometry_profile: container_inside_region_geometry_v1
evidence:
  tasks:
    - libero_90 task48 pick up the cream cheese box and put it in the basket
  episodes:
    - gpu1_selected_online_mining_clean_task48_20260823
---

## Intent

This policy contributes only planner geometry for inside-container placement.
It creates a virtual `*_inner_floor` support surface inside the grounded
container and compiles inside placement into a place-on-inner-floor recovery
goal.

It does not decide when to recover, does not bind the semantic target by
itself, and does not implement a new `place_in` executor.
