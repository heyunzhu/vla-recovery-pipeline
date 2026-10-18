---
id: top_drawer_container_grounding
name: Top drawer container grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 46
when_to_apply: When an already-triggered recovery must put an object in the top drawer of a cabinet.
when_not_to_apply: Do not use for placing on top of a cabinet, closing drawers, handles, doors, middle drawers, bottom drawers, or generic cabinet-body placement.
failure_signature:
  - Top-drawer placement can be coarsely bound to the cabinet body, e.g. white_cabinet_1_main.
  - The semantic target should be the top drawer container link rather than the whole cabinet body or the cabinet-top support surface.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "top drawer.*cabinet|cabinet.*top drawer"
recovery_hints:
  params:
    grounding_profile: top_drawer_container_v1
evidence:
  tasks:
    - libero_90 task33 put the ketchup in the top drawer of the cabinet
  episodes:
    - gpu1_selected_online_mining_clean_task33_20260823
---

## Intent

This policy contributes only target grounding. It maps coarse cabinet-body
inside goals for top-drawer language onto the explicit top drawer container
link.

It does not create a planner surface. The paired
`top_drawer_inner_floor_geometry` policy owns the virtual inner-floor region.
