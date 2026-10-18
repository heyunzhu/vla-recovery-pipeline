---
id: desk_caddy_compartment_grounding
name: Desk-caddy compartment grounding
kind: recovery_hint
track: pair
scope: grounding
priority: 48
when_to_apply: When an already-triggered recovery must place a book into a named front, back, left, or right compartment of the desk caddy.
when_not_to_apply: Do not use for baskets, drawers, cabinets, table regions, or generic caddy placement without an explicit named compartment.
failure_signature:
  - The BDDL goal names a desk_caddy contain region such as desk_caddy_1_left_contain_region, which is not a live scene object.
  - The semantic fallback can bind the target to desk_caddy_1_main without preserving the compartment intent.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - task_language_matches: "(front|back|left|right) compartment.*caddy|caddy.*(front|back|left|right) compartment"
    - target_name_matches: "book|black_book"
    - goal_name_matches: "desk_caddy|caddy"
    - bddl_goal_surface_matches:
        - "*desk_caddy*_*_contain_region"
recovery_hints:
  params:
    grounding_profile: desk_caddy_compartment_v1
evidence:
  tasks:
    - libero_90 task74 pick up the book and place it in the front compartment of the caddy
    - libero_90 task75 pick up the book and place it in the left compartment of the caddy
  episodes:
    - online_skill_regression_tasks31_32_37_38_70_71_74_75_20260826 task74/task75
---

## Intent

This policy contributes only target grounding for named desk-caddy
compartments. It preserves the BDDL compartment surface and lets the paired
geometry policy compile that container region into an executable inner-floor
placement proxy.

It does not create planner geometry, choose a grasp, or decide when recovery
should start.
