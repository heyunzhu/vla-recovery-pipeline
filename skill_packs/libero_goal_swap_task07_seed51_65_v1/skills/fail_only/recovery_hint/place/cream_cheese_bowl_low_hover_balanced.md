---
id: cream_cheese_bowl_low_hover_balanced
name: Cream cheese bowl low-hover balanced place
kind: recovery_hint
track: fail_only
scope: place
priority: 44
when_to_apply: When recovery is placing cream cheese into the black bowl and the earlier
  high-hover place budget either exhausts XY/drop budget or leaves the object above
  the release band.
when_not_to_apply: Do not use for non-cream-cheese targets, non-bowl goal surfaces,
  caddy compartments, trays, baskets, shelves, cabinets, or table-side placement.
failure_signature:
- W2 improved task07 validation from 6/15 to 8/15, but remaining failures still exhausted
  place hover/XY alignment budget or missed the release z band.
- In W2 ep00, ep05, and ep11 the hover phase consumed most of the remaining 200-step
  recovery budget, leaving no effective correction/drop window.
- In W2 ep03 the object was within the bowl opening in XY but remained about 10.8
  cm above support because no drop budget remained.
- The cream cheese is a flat box and the goal is an open bowl, so the task should
  not need the default 8 cm vessel-style hover clearance.
recovery_point: After the existing cream-cheese wrong-object repair enters recovery
  and the planner reaches the final Place step over the black bowl.
applies_to:
  all:
  - task_language_matches: cream cheese.*bowl|bowl.*cream cheese
  - target_name_matches: cream_cheese|cream cheese
  - goal_name_matches: bowl|akita_black_bowl
recovery_hints:
  params:
    place_profile: cream_cheese_bowl_low_hover_balanced_v1
    source: libero_goal_swap_task07_seed51_65_w3
evidence:
  tasks:
  - 'libero_goal_swap task07: put the cream cheese in the bowl'
  - libero_90 task07 put the cream cheese in the bowl
  episodes:
  - task7_ep0_seed51
  - task7_ep1_seed52
  - task7_ep3_seed54
  - task7_ep5_seed56
  - task7_ep6_seed57
  - task7_ep11_seed62
  - task7_ep12_seed63
  - task7_ep2_seed53
  - task7_ep4_seed55
  - task7_ep7_seed58
  - task7_ep8_seed59
  - task7_ep9_seed60
  - task7_ep10_seed61
  - task7_ep13_seed64
  - task7_ep14_seed65
---
This hint supersedes the W2 high-hover place budget through higher priority.
It lowers only the task-local bowl hover and balances the finite 200-step
recovery budget across lift, hover, XY correction, drop, and release.
