---
id: cream_cheese_bowl_support_geometry
name: Cream cheese bowl support geometry
kind: recovery_hint
track: fail_only
scope: geometry
priority: 44
when_to_apply: When recovery must place a cream-cheese box onto the goal bowl surface.
when_not_to_apply: Do not use for plates, baskets, trays, caddies, shelves, cabinets, or non-bowl goal surfaces.
failure_signature:
  - The goal surface in task07 is a movable bowl object rather than a fixed table region.
  - cuTAMP needs the bowl registered as a temporary support surface before it can plan the final place step.
recovery_point: After a matching repair trigger enters recovery, register the goal bowl as a movable support surface in the planner world.
applies_to:
  all:
    - task_language_matches: "cream cheese.*bowl|bowl.*cream cheese"
    - target_name_matches: "cream_cheese|cream cheese"
    - goal_name_matches: "bowl|akita_black_bowl"
recovery_hints:
  params:
    geometry_profile: cream_cheese_bowl_support_geometry_v1
evidence:
  tasks:
    - "libero_goal_swap task07: put the cream cheese in the bowl"
  episodes:
    - task07_seed51_ep00
    - task07_seed52_ep01
---
This hint contributes only planner geometry. It does not decide when to recover
and does not change the cream-cheese grasp sampler.
