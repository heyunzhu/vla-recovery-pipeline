---
id: cream_cheese_bowl_support_grounding
name: Cream cheese bowl support grounding
kind: recovery_hint
track: fail_only
scope: grounding
priority: 45
when_to_apply: When recovery must put cream cheese in or on a black bowl and the BDDL
  goal surface is the bowl object.
when_not_to_apply: Do not use for plate-side, basket, tray, caddy, shelf, cabinet,
  or bowl-stack tasks.
failure_signature:
- The task instruction says `put the cream cheese in the bowl`, while the BDDL atom
  is `on(cream_cheese_1_main, akita_black_bowl_1_main)`.
- The bowl is a movable scene object, so recovery should explicitly treat it as the
  intended support object.
recovery_point: After a matching repair trigger has entered recovery, mark the goal
  bowl as the support surface for the final placement.
applies_to:
  all:
  - task_language_matches: cream cheese.*bowl|bowl.*cream cheese
  - target_name_matches: cream_cheese|cream cheese
  - goal_name_matches: bowl|akita_black_bowl
recovery_hints:
  params:
    grounding_profile: cream_cheese_bowl_support_v1
    grounding_hints:
      support_object:
        intent: stack_support
        object_class: bowl
        relation: true
        predicates:
        - true
evidence:
  tasks:
  - 'libero_goal_swap task07: put the cream cheese in the bowl'
  - libero_90 task07 put the cream cheese in the bowl
  episodes:
  - task07_seed51_ep00
  - task07_seed52_ep01
  - task7_ep0_seed51
  - task7_ep1_seed52
  - task7_ep2_seed53
  - task7_ep3_seed54
  - task7_ep4_seed55
  - task7_ep5_seed56
  - task7_ep6_seed57
  - task7_ep7_seed58
  - task7_ep8_seed59
  - task7_ep9_seed60
  - task7_ep10_seed61
  - task7_ep11_seed62
  - task7_ep12_seed63
  - task7_ep13_seed64
  - task7_ep14_seed65
---
This hint contributes only goal binding semantics. The paired geometry hint owns
creation of the temporary support surface.
