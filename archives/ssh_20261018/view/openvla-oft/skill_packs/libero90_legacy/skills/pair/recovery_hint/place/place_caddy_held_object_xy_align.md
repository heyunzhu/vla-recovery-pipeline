---
id: place_caddy_held_object_xy_align
name: Caddy held-object XY alignment before release
kind: recovery_hint
track: pair
scope: place
priority: 48
when_to_apply: When recovery is placing a book into a named front, back, left, or right compartment of the desk caddy and the book footprint may drift outside the compartment opening after hover-yaw alignment.
when_not_to_apply: Do not use for non-caddy containers, table-relative left/right regions, drawers, cabinets, or tasks whose target object is not a book.
failure_signature:
  - cuTAMP produces a feasible pick/place plan for a caddy compartment, but the executor reaches release with one edge of the held book slightly outside the compartment opening.
  - After hover yaw, the held book footprint center can remain centimeters away from the safe compartment center even though the edge violation is small.
  - If this alignment fails, returning control to VLA while the book is still held causes the episode to degrade instead of completing the planned place.
recovery_point: After a repair/trigger skill has already decided to call recovery and after the executor has completed place hover-yaw alignment.
applies_to:
  all:
    - task_language_matches: "(front|back|left|right) compartment.*caddy|caddy.*(front|back|left|right) compartment"
    - target_name_matches: "book|black_book"
    - goal_name_matches: "desk_caddy|caddy"
    - bddl_goal_surface_matches:
        - "*desk_caddy*_*_contain_region"
recovery_hints:
  params:
    place_profile: caddy_book_compartment_align_budget_v1
evidence:
  tasks:
    - libero_90 task74 pick up the book and place it in the front compartment of the caddy
    - libero_90 task75 pick up the book and place it in the left compartment of the caddy
  episodes:
    - task74_two_caddy_crop_20260828 showed feasible plans and correct caddy-front XY, but place_drop still stalled and release remained unstable.
    - book_caddy_budget_ab_20260830 showed that increasing executor alignment/drop budget reduced caddy-place aborts and improved task74/75/76/78/79/80/81/82/83/84 from 26/50 to 38/50.
---

## Intent

This policy contributes only executor-side place alignment through the
`caddy_book_compartment_align_budget_v1` place profile. It does not change
grounding, geometry generation, or grasp sampling. When the executor has
already hovered over a named caddy compartment and completed the yaw policy,
it reads the current held book footprint from the live object geometry and
nudges the end effector at the current hover height so the footprint center
is aligned with the safe compartment center while the whole footprint
remains inside the safe opening before the final vertical drop and release.
A final footprint edge violation up to 1 mm is accepted as release
tolerance. If live footprint geometry is unavailable, it falls back to the
older center-alignment behavior.

The correction is intentionally small and bounded: it keeps the gripper
closed, keeps the current orientation, clips each XY correction step, and
only applies to caddy compartment placements. During the final descent it
uses short vertical slices and re-runs the footprint alignment after each
slice, so small tracking drift during drop can still be corrected before
release. The formal budget allows up to 12 alignment steps per iteration
and 80 closed-loop drop steps; these values were validated in the
book-caddy A/B run on 2026-08-30. For book-into-caddy placement, a failed
release geometry check is
treated as an episode abort instead of handing the held book back to VLA.
