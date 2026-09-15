---
id: book_pick_approach_recovery
name: Generic book pick approach recovery
kind: repair
track: pair
hook: after_pi0_query
priority: 72
when_to_apply: When the parsed target is a book, the hand is empty, and the VLA
  has approached the target book closely enough for recovery to take over before
  a late empty-close stall.
when_not_to_apply: Do not use for grocery boxes, cartons, bowls, mugs, or
  wrong-object approaches where the trajectory intent points away from the book.
failure_signature:
  - LIBERO-90 book tasks outside the caddy-compartment family had no repair
    trigger even when the target book was approached with an empty hand.
  - In task81/task82/task84, caddy-specific recovery only fired when the strict
    nearest-target condition happened to hold; nearby target-book approaches
    were otherwise left to VLA.
recovery_point: During target-book approach with an empty hand, before the
  first close or push destabilizes the book.
applies_to:
  all:
    - target_name_matches: "book|black_book|yellow_book"
    - target_name_excludes: "cream_cheese|butter|carton|milk|juice|can|mug|bowl|alphabet_soup|tomato_sauce"
trigger:
  all:
    - aperture_gt: 0.025
    - holding_status_is: handempty_or_unconfirmed
    - target_ee_distance_lt: 0.30
  any:
    - nearest_pickable_is_target: true
    - intent_object_is_target: true
    - target_future_min_xy_distance_lt: 0.12
backend: cutamp_recover
evidence:
  tasks:
    - libero_90 task81 pick up the book and place it in the right compartment of the caddy
    - libero_90 task87 pick up the book in the middle and place it on the cabinet shelf
    - libero_90 task89 pick up the book on the right and place it on the cabinet shelf
  episodes:
    - online_skill_regression_tasks81_90_scopefix_20260829 task89 ep00 target-book approach without a matching repair
---

## Intent

This repair only opens a recovery entry point for target-book approaches. It
does not select a book grasp or a placement target. Book grasping remains owned
by `grasp_book_upright_topdown`, and placement grounding or geometry remains
owned by the active grounding/geometry hint skills.

The caddy-specific book repair keeps higher priority, so known
book-to-compartment cases can still use their narrower trigger first.
