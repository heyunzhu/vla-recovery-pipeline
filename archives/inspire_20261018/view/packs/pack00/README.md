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

> **FROZEN 2026-09-16** - campaign record for libero_goal_task (10/10 tasks: t3/t9 passed, t7/t8 covered, six blockers). Do not modify; the working pack moved to libero_spatial_swap_from_goal_task_mining_base_20260916.
