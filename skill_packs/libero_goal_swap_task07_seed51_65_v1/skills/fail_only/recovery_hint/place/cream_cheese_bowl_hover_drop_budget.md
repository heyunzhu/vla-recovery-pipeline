---
id: cream_cheese_bowl_hover_drop_budget
name: Cream cheese bowl hover/drop budget
kind: recovery_hint
track: fail_only
scope: place
priority: 43
when_to_apply: When recovery has picked the cream cheese and must place it into the
  black bowl, but the executor stalls before reaching hover or release height.
when_not_to_apply: Do not use for non-cream-cheese targets, non-bowl goal surfaces,
  caddy compartments, trays, baskets, shelves, cabinets, or table-side placement.
failure_signature:
- W1 validation for LIBERO-PRO goal-swap task07 reached recovery in every rollout
  and picked the cream cheese, but only 6/15 rollouts succeeded.
- Failed episodes ep00, ep01, ep02, and ep05 exhausted the place hover and hover-XY-correction
  budget with the held cream cheese still 7-13 cm from the bowl opening center.
- Failed episodes ep03, ep12, and ep14 reached the bowl opening in XY, but release
  was blocked because the cream-cheese z delta remained about 7.7-8.7 cm above the
  bowl support while the default release z band was 7 cm.
- Failed episodes ep07 and ep10 handed off after place lift because the default clearance
  guard was too strict for the slightly stalled post-grasp lift.
recovery_point: After the existing cream-cheese wrong-object repair has entered recovery
  and the planner is executing the final Place step over the black bowl.
applies_to:
  all:
  - task_language_matches: cream cheese.*bowl|bowl.*cream cheese
  - target_name_matches: cream_cheese|cream cheese
  - goal_name_matches: bowl|akita_black_bowl
recovery_hints:
  params:
    place_profile: cream_cheese_bowl_hover_drop_budget_v1
    source: libero_goal_swap_task07_seed51_65_w2
evidence:
  tasks:
  - 'libero_goal_swap task07: put the cream cheese in the bowl'
  - libero_90 task07 put the cream cheese in the bowl
  episodes:
  - task7_ep0_seed51
  - task7_ep1_seed52
  - task7_ep2_seed53
  - task7_ep3_seed54
  - task7_ep5_seed56
  - task7_ep7_seed58
  - task7_ep10_seed61
  - task7_ep12_seed63
  - task7_ep14_seed65
  - task7_ep4_seed55
  - task7_ep6_seed57
  - task7_ep8_seed59
  - task7_ep9_seed60
  - task7_ep11_seed62
  - task7_ep13_seed64
---
This hint does not decide when recovery starts and does not change the
cream-cheese grasp sampler or bowl grounding. It only expands a place profile
that gives the executor more hover/drop budget and accepts the observed
slightly high cream-cheese release pose over the bowl.
