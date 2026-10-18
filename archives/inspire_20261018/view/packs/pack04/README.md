FROZEN 2026-09-18 - campaign record, do not edit.
Working pack for the next campaign: skill_packs/libero_object_task_from_spatial_swap_mining_base_20260918

# libero_goal_task_from_goal_swap_v1

Isolated LIBERO-Pro `libero_goal_task` mining pack seeded from the previous
`libero_goal_swap` mining packs. It is a separate pack so goal-task mining can
reuse goal-swap experience without mutating the original suite-specific packs.

Initial inherited assets:

- goal-swap task09 bowl-on-plate early handoff and hollow-bowl grasp hint.
- goal-swap task05/task07 cabinet-top trigger/geometry pieces that are safe to
  keep as fail-only mining context.

Candidate skills written during mining should first land under `skills/fail_only/`
and only move to `skills/pair/` after validation and admission gates pass.
