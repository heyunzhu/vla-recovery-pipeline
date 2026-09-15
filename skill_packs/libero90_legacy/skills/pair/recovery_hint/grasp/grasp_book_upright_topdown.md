---
id: grasp_book_upright_topdown
name: Book upright top-down grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 54
when_to_apply: When an already-triggered recovery is manipulating a standing book and the default 12 cm close-height precheck rejects a reachable top-down pinch.
when_not_to_apply: Do not use for grocery boxes, cartons, cans, bowls, mugs, or non-book objects.
failure_signature:
  - A standing LIBERO book is about 13 cm tall, so a top-down close leaves the Panda EE 14-15 cm above the book center.
  - The default grasp_close_max_above_m of 0.12 then skips close as grasp_target_not_near even when XY tracking succeeded.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "book|black_book"
    - target_name_excludes: "cream_cheese|butter|carton|milk|juice|can|mug|bowl|alphabet_soup|tomato_sauce"
recovery_hints:
  grasp_profile: flat_box_topdown_short_side_book_v1
  target: target
  params:
    executor:
      grasp_close_max_above_m: 0.20
    source: task74_75_book_lower_topdown_20260827
evidence:
  tasks:
    - libero_90 task74 pick up the book and place it in the front compartment of the caddy
    - libero_90 task75 pick up the book and place it in the left compartment of the caddy
  episodes:
    - caddy_book_close_precheck_force_q5_online_20260827
---

## Intent

This policy keeps a top-down short-side pinch for a standing book, but closes
a few centimeters below the crown instead of the 4-7 mm flat-box edge. It also
raises the executor close-height precheck for that target. It does not switch
to a mid-body side grasp.

It does not decide when to recover and does not define placement goals or
planner geometry.
