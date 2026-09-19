SEALED RECORD - do not edit. See SEAL.json.

This is the goal_swap campaign's as-run record (23 fail-only assets, `skills/_index.yaml` md5 `5e40d87b7bd608141cca18115ea120e7`).
It was never committed while the campaign ran; recovered from `/mnt/nas/gezuhao/xinghanbo/openvla-oft/skill_packs/libero_goal_task_from_goal_swap_v1` on 2026-09-19.
13 entries (plate/stove + cream_cheese_rack families) were written during the goal_task campaign and quarantined on 2026-09-14 - they fired in 1 of 500 episodes in the 0.336 run and never in the 0.77 run. A cleaned derivative is published as `libero_goal_task_from_goal_swap_v1_asrun_20260913_clean`.

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
