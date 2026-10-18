---
id: cream_cheese_wine_rack_top_grounding
name: Cream cheese wine-rack top grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 48
when_to_apply: When the task10 repair entrypoint has already decided to recover and
  the semantic goal must bind to the rack top region.
when_not_to_apply: Do not use for non-rack goals, non-cream-cheese targets, or as
  an independent trigger.
failure_signature:
- The BDDL goal surface is `wine_rack_1_top_region`, while parser-level fallback names
  the rack body `wine_rack_1_main`.
- The fresh forced recovery trace exposes the rack top site in scene metadata but
  does not promote it to a planner surface.
recovery_point: After a repair or trigger skill has already decided to call recovery.
applies_to:
  all:
  - task_language_matches: cream cheese.*rack|rack.*cream cheese
  - target_name_matches: '*cream_cheese*'
  - bddl_goal_surface_matches: '*wine_rack*top_region'
recovery_hints:
  params:
    grounding_profile: cream_cheese_wine_rack_top_v1
evidence:
  tasks:
  - 'libero_goal_task task10: Put the cream cheese on the rack'
  - libero_90 task10 Put the cream cheese on the rack
  episodes:
  - forced_q5_seed51_real
  - task10_ep0_seed51
  - task10_ep1_seed52
  - task10_ep2_seed53
  - task10_ep3_seed54
  - task10_ep4_seed55
  - task10_ep5_seed56
  - task10_ep6_seed57
  - task10_ep7_seed58
  - task10_ep8_seed59
  - task10_ep9_seed60
  - task10_ep10_seed61
  - task10_ep11_seed62
  - task10_ep12_seed63
  - task10_ep13_seed64
  - task10_ep14_seed65
---
## Intent

This policy contributes only semantic target grounding. It rewrites the rack
body fallback to the BDDL top-region name and does not create geometry, choose
a grasp, or decide when recovery starts.
