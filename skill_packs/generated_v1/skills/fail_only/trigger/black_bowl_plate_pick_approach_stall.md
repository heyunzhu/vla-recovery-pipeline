---
id: black_bowl_plate_pick_approach_stall
name: Black bowl plate pick approach stall
kind: trigger
track: fail_only
hook: after_pi0_query
priority: 45
when_to_apply: In generated black-bowl-on-plate tasks, when the VLA has committed
  the empty gripper toward the target black bowl, the predicted target approach is
  already close in XY, and the end effector stalls before a reliable grasp is established.
when_not_to_apply: Do not promote directly to online. Do not use when the hand already
  holds an object, when intent is not on the target object, or when the task is not
  a black-bowl-to-plate placement.
failure_signature:
- Skills-off selector023 failed 5/5 with no recovery events.
- Same-init selector030 validation w0 missed ep00 and ep01 because the VLA hovered
  over the target bowl with an empty hand while the 3D target distance stayed just
  above the earlier trigger threshold.
- Same-init selector030 validation w1 reached 2/5 with the mixed diagonal rim
  profile; ep02 still failed grasp confirmation after the bowl had been disturbed.
- Same-init selector030 validation w2 tried a radial-only rim profile and regressed
  to 0/5, so the radial-only profile is not kept in the scratch library.
recovery_point: Call cuTAMP once the empty gripper has made a target-directed approach,
  the planned future motion passes close to the bowl in XY, and the EE has nearly
  stopped for three query samples.
applies_to:
  all:
  - task_language_matches: akita black bowl.*plate|black bowl.*plate
  - target_name_matches: akita_black_bowl|black_bowl|bowl
  - bddl_goal_surface_matches: plate
trigger:
  all:
  - holding_status_is: handempty_or_unconfirmed
  - intent_object_is_target: true
  - target_ee_distance_lt: 0.205
  - target_future_min_xy_distance_lt: 0.05
  - ee_stalled:
      window: 3
      max_disp_m: 0.003
backend: cutamp_recover
recovery_hints:
  grasp_profile: bowl_rim_diagonal_mixed_topdown_v1
  target: target
  params:
    source: generated_scratch_task30_w1_best_observed
evidence:
  tasks:
  - libero_90 generated selector030 libero_90_gen_t032_pick_place_on_surface_ddcaf567
    pick up the akita black bowl and place it on the plate
  - libero_90 generated selector023 libero_90_gen_t029_pick_place_on_surface_629c0b88
    pick up the akita black bowl and place it on the plate
  - libero_90 generated selector003 libero_90_gen_t029_pick_place_on_surface_629c0b88
    pick up the akita black bowl and place it on the plate
  - libero_90 generated selector001 libero_90_gen_t029_pick_place_on_surface_629c0b88
    pick up the akita black bowl and place it on the plate
  - libero_90 generated selector001 libero_90_gen_t032_pick_place_on_surface_ddcaf567
    pick up the akita black bowl and place it on the plate
  episodes:
  - libero_90_gen_t032_pick_place_on_surface_ddcaf567_ep02_seed194
  - task1_ep0_seed194
  - task1_ep1_seed194
  - libero_90_gen_t029_pick_place_on_surface_629c0b88_ep00_seed194
  - libero_90_gen_t029_pick_place_on_surface_629c0b88_ep01_seed194
  - libero_90_gen_t029_pick_place_on_surface_629c0b88_ep02_seed194
  - libero_90_gen_t029_pick_place_on_surface_629c0b88_ep03_seed194
  - libero_90_gen_t029_pick_place_on_surface_629c0b88_ep04_seed194
  - task3_ep0_seed194
  - task3_ep1_seed194
  - task3_ep2_seed194
  - task3_ep3_seed194
  - task3_ep4_seed194
  - task1_ep2_seed194
---
## Intent

This draft keeps the generated black-bowl-on-plate fail-only trigger that first
covered selector023 and partially covered selector030.

Validation w1 reached 2/5 on selector030 with
`bowl_rim_diagonal_mixed_topdown_v1`. The remaining selected failure entered
recovery at the right time, but the close/lift confirmation did not establish a
stable hold after the VLA had already nudged or tilted the bowl.

Validation w2 tried switching to `bowl_rim_radial_topdown_v1`; that regressed to
0/5 and is intentionally not retained as the active scratch skill. The best
observed version remains the mixed diagonal profile until a lower or more
outward bowl-rim profile is added in code.

## Validation Notes

This is still a fail-only mining draft, not an online skill. It should pass only
if selector030 same-init validation reaches at least 3/5 without increasing the
trigger beyond the current task/intent/stall guards. The current task is marked
system-blocked after w2 because the next meaningful fix is outside the markdown
trigger surface.
