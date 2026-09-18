# LIBERO Batch Screening Status

Date: 2026-09-18

Status: paused because Inspire notebook `xinghanbo-eval` changed from `RUNNING` to `PENDING` during A-group screening.

## Scope

Batch screening request:

- A: `libero_spatial_swap` t7-t10
- B: `libero_object_swap` t1-t10
- C: `libero_object_task` t1-t10

Rules in force: baseline + W0, 15 episodes each, seeds 51-65, no probe before formal lanes; lightweight mining only if both baseline and W0 are below 9/15.

## Completed before pause

- Previous task06 remains complete: baseline 0/15, W0 15/15, commit `161cc0439e749f58f610302bb9b2237b6d12bf91`.
- For the new 24-task batch: no valid lane summary completed before the instance went `PENDING`.

## A-group run state

Suite: `libero_spatial_swap`

Run root:

`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/libero_screening_20260918/libero_spatial_swap`

Pack:

`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/vla-recovery-pipeline/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916`

Pack `_index.yaml` md5 recorded pre-run:

`ed2f95715177a83b3078381ed8b01ec5`

Progress:

- Initial launch failed immediately before any evaluation because the runner path was mistyped as `scripts/eval/run_skill_eval.py`; no summary was produced.
- Script was corrected to `scripts/recovery/skill_pipeline/run_skill_eval.py` and relaunched.
- Corrected run started `t7 baseline` (`task07_baseline_seed51_65_mrs200`) at remote timestamp `2026-09-18T03:05:34+00:00`.
- Last readable log tail showed only policy setup / benchmark load warnings, no episode result and no `summary.json`.
- While checking progress, `inspire notebook exec` reported: Notebook `xinghanbo-eval` is `PENDING`.

Remote files to inspect when the instance is RUNNING again:

- `$RUN_ROOT/status/progress.tsv`
- `$RUN_ROOT/status/run_suite_screen.pid`
- `$RUN_ROOT/task07_baseline_seed51_65_mrs200.log`
- any `$RUN_ROOT/*/summary.json`

## Resume plan

When `xinghanbo-eval` is `RUNNING` again:

1. Check notebook status first.
2. Inspect `$RUN_ROOT/status/progress.tsv` and existing `summary.json` files.
3. If no valid summary exists for `task07_baseline_seed51_65_mrs200`, rerun A group from t7 baseline using the corrected script.
4. Continue A group t7-t10 baseline/W0 screening, then write `docs/libero_spatial_swap_baseline_w0_screen_2026-09-18.md` and commit once for that suite.
5. Then continue B and C suites.

Do not poll while the notebook is `PENDING`.
