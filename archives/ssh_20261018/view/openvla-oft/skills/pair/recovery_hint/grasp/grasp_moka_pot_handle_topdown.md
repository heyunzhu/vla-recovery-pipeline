---
id: grasp_moka_pot_handle_topdown
name: Moka-pot handle top-down grasp
kind: recovery_hint
track: pair
scope: grasp
priority: 55
when_to_apply: When an already-triggered recovery is manipulating a moka pot target.
when_not_to_apply: Do not use for frypans, stove regions, bowls, mugs, cans, boxes, cartons, or non-moka-pot objects.
failure_signature:
  - Moka-pot recovery should grasp the handle rather than the pot body, spout, or AABB center.
  - The moka-pot AABB includes non-graspable protrusions, so generic top-down samples can put the close pose on the wrong part.
recovery_point: After a repair/trigger skill has already decided to call recovery.
applies_to:
  all:
    - target_name_matches: "moka_pot|moka pot"
    - target_name_excludes: "frypan|stove|bowl|mug|cup|can|carton|box"
recovery_hints:
  grasp_profile: moka_pot_handle_topdown_v1
  target: target
  params:
    source: task20_moka_pot_handle_grasp_analysis_20260826
evidence:
  tasks:
    - libero_90 task20 put the moka pot on the stove
    - libero_90 task39 put the right moka pot on the stove
  episodes:
    - task20_moka_pot_geometry_viz_20260826
---

## Intent

This skill contributes a moka-pot handle grasp profile only. It restricts
recovery pick candidates to the local positive-Y handle side and removes generic
center, body, and spout samples.

It does not decide when recovery should start, bind the stove target region, or
change planner geometry.
