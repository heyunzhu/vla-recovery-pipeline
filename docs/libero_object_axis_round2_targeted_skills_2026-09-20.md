# LIBERO-Pro object axes: round 2 - targeted skills (2026-09-20)

Follows `libero_object_axis_grasp_round_2026-09-19.md`. The transfer run on
`libero_object_task` ended at 35/50 with two kinds of open item: cream cheese never entered
recovery on that axis, and tomato/milk/orange-juice/butter fired but did not fully convert. This
round diagnoses both and adds the two skills the evidence supports.

## Per-predicate diagnosis (cream cheese on libero_object_task t01)

Language, target and basket scope all match; the blockers are geometric:

- `wrong_object_intent_persist_queries_gte: 4` - **0/280 query rows pass**, the observed maximum
  persistence is 2;
- `intent_min_xy_distance_lt: 0.05` - **0/280 rows pass**, the minimum observed is 0.051640 m;
- `vla_pick_target_status_is: non_target_intent` is only briefly present in 3 of the 5 episodes, so
  it cannot be a condition shared by all five.

## Recovery-chain classification for the partial tasks

| object | finding |
| --- | --- |
| tomato sauce | 2 of 3 failures never triggered; 1 entered recovery and died on Pick trajectory tracking |
| milk | one failure was a pure grasp that never lifted; another grabbed air, succeeded on the second attempt, then failed Place hover alignment |
| orange juice | both failures were grasps that never lifted |
| butter | the flat-box profile is active and 9/9 solves are planner-feasible; failures lose bilateral contact after closing (gripper nearly closed) - not a trigger, planning or Place problem, **so no further grasp hint was written** |

## Candidates added

1. `skills/fail_only/trigger/object_basket_cream_tomato_q5_wrong_intent_window.md` - a narrow q5
   wrong-intent window for cream cheese and tomato sauce with a six-query history gate. The first
   version (no history gate) matched the first frames of older `object_swap` episodes and produced
   64 `q<5` early fires; it was rejected and its evidence kept as the `scan_run1` counter-example.
   The final trigger hits t01 5/5 at q5 with **early-fire(q<5) = 0** and a success fire rate of
   1/63 = 1.59%.
2. `skills/fail_only/recovery_hint/grasp/grasp_object_basket_tall_carton_topdown_deep.md` - a
   dimension-scaled deep top-down grasp for the milk and orange-juice cartons, reusing the
   registered `cream_cheese_flat_box_topdown_deep_v1` profile. Evidence: failed carton recoveries
   are planner-feasible but the first lift probe reports `object_followed=false`,
   `bilateral_contact=false` and lift below 0.003 m, while successful probes retain 0.021-0.023 m;
   the carton AABB is about 0.0525 x 0.0531 x 0.1312 m against a generic candidate width of about
   0.0821 m.

## Offline scan (600-episode corpus, both object axes)

| candidate | libero_object_task failures | libero_object_swap failures | success firings | early-fire(q<5) |
| --- | --- | --- | ---: | ---: |
| q5 wrong-intent window (cream cheese) | 15/30 | 6/30 | - | 0 |
| q5 wrong-intent window (tomato sauce) | 24/28 | 2/30 | - | 0 |
| tall-carton grasp hint (milk) | 30/30 | 30/30 | - | 0 |
| tall-carton grasp hint (orange juice) | 30/30 | 30/30 | - | 0 |
| new trigger totals | - | - | 1/63 = 1.59% | 0 |

The new trigger is complementary to the existing cream-cheese and tomato triggers; recall is not an
admission gate.

## Immutability record

`skills/_index.yaml` md5 `714e331697d751864fb28875c4cfaa95` (32 entries):
`object_basket_cream_tomato_q5_wrong_intent_window.md` md5 `8684cbe318dc23def8eeeffd30361284`,
`grasp_object_basket_tall_carton_topdown_deep.md` md5 `4565c9756012ef529c11b3c3e63eef4a`.

## Next step (queued when this was committed)

Full 50-seed validation on both object axes (`libero_object_swap`, `libero_object_task`,
seed 1-50, 50 episodes per task) with this pack, on the Inspire instance. Evidence for this round:
`remote_outputs/object_task_skill_round_20260920/` (report, diagnostic_evidence.json,
scan_breakdown.json, drafts, scan_run1 counter-example, scan_run2 five-piece set).
