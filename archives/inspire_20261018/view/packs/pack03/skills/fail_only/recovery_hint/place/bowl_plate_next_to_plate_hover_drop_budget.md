---
id: bowl_plate_next_to_plate_hover_drop_budget
name: Bowl plate next-to-plate hover drop budget
kind: recovery_hint
track: fail_only
scope: place
priority: 62
when_to_apply: Use when task3 recovery has picked the target akita black bowl and
  is placing it on the plate, but execution needs extra lift, hover, and release budget
  to settle the bowl instead of handing back to VLA too early.
when_not_to_apply: Do not use if the pick never reaches confirmed holding, if the
  target binding is wrong, or outside the task3 next-to-plate black-bowl-to-plate
  task. Do not use for task1 not-between wording.
failure_signature:
- W1 full validation reached 6/15. Some failures reached the place stage but returned
  place_lift_too_low or late hover/drop instability.
- W1 seed55 fired the task3 trigger, grasped the target bowl, then place returned
  place_lift_too_low and handed back to VLA.
- The existing task1 bowl_plate_hover_drop_budget uses similar executor knobs but
  does not match task3 wording, so task3 currently has no scoped place budget.
- A conservative place-only probe on seed54-58 reached 3/5, improving over W1's 1/5
  on the same seed window; the broader region-grounding probe was rejected because
  it caused a long pick-only/generic loop.
recovery_point: After cuTAMP has a holding plan for akita_black_bowl_2_main and before
  release over the plate.
applies_to:
  all:
  - task_language_matches: black bowl.*next to.*plate.*place.*plate|black bowl.*next
      to the plate.*on the plate|next to.*plate.*on the plate
  - target_name_matches: akita_black_bowl_2|black_bowl|bowl
  - goal_name_matches: plate
  - bddl_goal_surface_matches: plate
recovery_hints:
  params:
    executor:
      place_lift_max_steps: 70
      place_lift_reached_m: 0.014
      place_lift_min_clearance_m: 0.03
      place_hover_clearance_m: 0.055
      place_hover_max_steps: 90
      place_hover_reached_m: 0.014
      place_drop_max_steps: 120
      place_drop_reached_m: 0.018
      place_release_z_max_m: 0.1
      place_open_dwell_steps: 8
    source: libero_spatial_task03_w2_place_only_seed54_58_probe
    notes: Conservative task3-scoped place budget only; no grounding, geometry, grasp,
      or trigger changes.
evidence:
  tasks:
  - 'libero_spatial_task task3: Pick the akita black bowl next to the plate and place
    it on the plate'
  - libero_90 task03 Pick the akita black bowl next to the plate and place it on the
    plate
  episodes:
  - task3_w1_seed55_place_lift_too_low
  - task3_probe_w2_place_seed54_success
  - task3_probe_w2_place_seed55_success
  - task3_probe_w2_place_seed58_success
  - task3_ep2_seed53
  - task3_ep7_seed58
  - task3_ep9_seed60
---
This is the W2 conservative place hint. It gives the existing task3 repair trigger enough local place budget without changing target binding, geometry, grasp sampling, or trigger timing.
