---
id: place_wine_bottle_bowl_drop_budget
name: Wine bottle bowl drop budget
kind: recovery_hint
track: fail_only
scope: place
priority: 47
when_to_apply: When recovery has picked the wine bottle and must lower it into
  the black bowl inner-floor proxy.
when_not_to_apply: Do not use for non-wine-bottle targets, non-bowl goal surfaces,
  or tasks whose failure is still a target binding or grasp issue.
failure_signature:
- The wine bottle is tall relative to the shallow bowl, so the inner-floor goal
  needs enough hover/drop budget to reach a low release pose.
recovery_point: After the planner has selected the bowl inner-floor Place step.
applies_to:
  all:
  - task_language_matches: wine bottle.*in.*bowl|put.*wine bottle.*in.*bowl
  - target_name_matches: wine_bottle|wine bottle
  - goal_name_matches: akita_black_bowl|bowl
  - bddl_goal_surface_matches: akita_black_bowl|bowl
recovery_hints:
  params:
    place_profile: wine_bottle_bowl_drop_budget_v1
    source: libero_goal_task03_w1_wrong_object_inner_floor
evidence:
  tasks:
  - 'libero_goal_task task03: put the wine bottle in the bowl'
  episodes:
  - probe_forced_q3_seed51_55 ep00-ep04
---
This hint only contributes executor-side place budget after grounding and
geometry have selected the bowl inner-floor target.
