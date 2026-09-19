# LIBERO-Pro object axes: trigger round (2026-09-19)

Suites: `libero_object_task` and `libero_object_swap` (10 tasks each, 20 total).
Every task is the same template - `Pick the <object> and place it in the basket` - with the
same BDDL goal shape `(And (In <object>_1 basket_1_contain_region))`; the ten objects are the
same set, only permuted between the two axes.

## Starting point (why the pack did nothing)

Screening on 2026-09-18 (seeds 51-65, baseline + W0) left 19 of 20 tasks at 0/15; only
`libero_object_task` t02 (alphabet soup) reached 14/15. A trace audit of all 600 screening
episodes then showed the real cause:

- `recovery_calls` is 0 in **all 600** episodes and every `recovery_trace.jsonl` is empty;
- an offline replay scan of the pack's 11 triggers reports **0 matching queries**;
- the existing triggers' language scopes cover bowl/plate, cabinet, cookie box, stove, wine
  bottle and cream-cheese-in-bowl - **none of them matches a basket task**.

So these failures were never "recovery fired and failed"; recovery never started.

## Round 1 - offline trigger tuning (no GPU)

Corpus: the same 600 episodes (572 failed, 28 successful), read-only, plus the isolated pack
copy. Five fail-only triggers were derived by grid-searching the safety gates rather than by
guessing, and each was validated with `scan_skill_triggers.py`:

| trigger | target scope | failed coverage | first hit q | success misfires |
| --- | --- | ---: | --- | ---: |
| `object_basket_persistent_wrong_intent_group_a` | alphabet soup, butter, chocolate pudding, ketchup, milk | 270/572 | median q5 | 0/28 |
| `object_basket_tomato_persistent_wrong_intent` | tomato sauce | 48/572 | median q5 | 0/28 |
| `object_basket_bbq_orange_precontact_wrong_intent` | bbq sauce, orange juice | 120/120 | q5-q10 (median 6) | 0/28 |
| `object_basket_cream_cheese_precontact_wrong_intent` | cream cheese | 28/60 | q5-q7 (median 7) | 0/28 |
| `object_basket_salad_dressing_precontact_wrong_intent` | salad dressing | 60/60 | q5-q9 (median 7) | 0/28 |

Union coverage 526/572 = 91.96% of the failures, zero success misfires, every first hit at
q>=5, and at every first hit the wrongly-intended object had moved at most 2 mm.

Iteration record (`iteration_comparison.csv`): the loose supervisor probe covered 100% of
failures but fired on 100% of successes and before q5 (rejected); an all-targets variant with
`persist>=4` reached 92.8% but produced 115 early fires (rejected); the per-group split above
passes every gate.

Open item: `salad dressing` has an always-empty `wrong_object_intent_margin` field, so that
draft substitutes a bounded distance separation. It passed the gates and was used in the trial
run below, but it is a protocol exception and remains flagged for review.

## Round 2 - first GPU trial (object_swap, 10 tasks x 5 episodes)

Run root: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/object_swap_trend_20260919`
(`object_swap_w0_trigger_5ep`, seeds 51-55, `--enable_mining_skills --max_recovery_calls 2`,
`--save_video`, one lane on GPU 0 next to the running pack evaluation).

Pack used: `skill_packs/libero_object_task_from_spatial_swap_mining_base_20260918` plus the five
triggers above, in an isolated copy (`skills/_index.yaml` md5 `670c83d793ce922a1f4347e4a61d408e`).

| task | object | result | recoveries | trigger that fired | dominant failure |
| --- | --- | ---: | ---: | --- | --- |
| t01 | alphabet soup | 5/5 | 5 | `group_a` | - |
| t02 | cream cheese | 0/5 | 5 | `cream_cheese_precontact` | `optimized_motion_tracking_stalled` |
| t03 | salad dressing | 5/5 | 5 | `salad_dressing_precontact` | - |
| t04 | bbq sauce | 5/5 | 5 | `bbq_orange_precontact` | - |
| t05 | ketchup | 5/5 | 5 | `group_a` | - |
| t06 | tomato sauce | 5/5 | 5 | `tomato_persistent` | - |
| t07 | butter | 0/5 | 10 | `group_a` | `No satisfying particles` |
| t08 | milk | 3/5 | 7 | `group_a` | `goal_atoms_not_yet_satisfied` |
| t09 | chocolate pudding | 0/5 | 10 | `group_a` | `No satisfying particles` |
| t10 | orange juice | 4/5 | 7 | `bbq_orange_precontact` | `goal_atoms_not_yet_satisfied` |

Total **32/50 = 0.640**, against a baseline of 0/15 for all ten tasks (and 0/15 with the old
pack). All 50 episodes fired recovery.

Failure taxonomy (18 failures): 10x `real_cutamp_no_feasible_goal`, 5x
`optimized_motion_tracking_stalled` (all on cream cheese), 3x `goal_atoms_not_yet_satisfied`
(milk 2, orange juice 1).

Trace signatures separate cleanly: every success walks `Pick(...) -> Place(...)`, every failure
stops inside `Pick` or in planning. **No failure sits in the placement stage**, so the shared
basket placement works as-is for the objects that can be picked.

## What this round establishes

1. The trigger gap is closed: 50/50 episodes fire, and ten previously-zero tasks now produce
   32/50.
2. `place` / `grounding` / `geometry` showed no defect on this axis: the default placement into
   `basket_1_contain_region` succeeded for every object whose grasp plan was feasible.
3. The remaining work is **grasp**, and it is concentrated: cream cheese (0/5), butter (0/5) and
   chocolate pudding (0/5) fail before placement, i.e. the default samplers cannot produce a
   feasible grasp/plan for those shapes; milk and orange juice need light tuning.

Evidence kept with this document:

- codex draft scan outputs: `remote_outputs/object_trigger_scan_20260919/`
  (`PRECONTACT_DRAFT_REPORT.md`, `precontact_draft_summary.csv`, `iteration_comparison.csv`)
- trial run artifacts (summary, per-episode traces and videos):
  `E:/VLA_recovery_workspace/remote_outputs/object_swap_trend_20260919/`
