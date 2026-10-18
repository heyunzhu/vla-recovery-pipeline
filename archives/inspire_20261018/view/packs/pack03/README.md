# libero_object_task_from_spatial_swap_mining_base_20260918

LIBERO-Pro `libero_object_task` mining pack, copy-forwarded from the spatial-swap
campaign pack (`libero_spatial_swap_from_goal_task_mining_base_20260916`) on
2026-09-18, before that pack was frozen.

Why a new pack: suite-specific mining must not mutate the previous campaign's record.

Inherited assets (25 fail-only): 11 triggers, 3 geometry hints, 4 grasp hints,
2 grounding hints, 4 place hints, plus `code/`, `profiles/`, `diagnostics/`.

Context entering this campaign (24-task baseline/W0 screening, seeds 51-65):

- `libero_spatial_swap` t7 0/15 -> 10/15, t8 0/15 -> 14/15, t9 13/15 -> 11/15,
  t10 0/15 -> 12/15 (all covered); t6 covered-by-W0 (15/15); t4/t5 blockers.
- `libero_object_swap` t1-t10: 0/15 -> 0/15 (no inherited trigger fires/converts).
- `libero_object_task` t2: 14/15 -> 14/15 (already covered by the policy alone);
  the other nine tasks: 0/15 -> 0/15 - these are this campaign's mining targets.

Candidate skills written during mining land under `skills/fail_only/` first and move to
`skills/pair/` only after the admission gate and the full 300-episode offline scan pass.
