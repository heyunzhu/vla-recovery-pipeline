# LIBERO Batch Screening Status

Date: 2026-09-18

Status: paused because Inspire notebook `xinghanbo-eval` changed from `RUNNING` to `PENDING` again while the all-suite queue was being installed/launched.

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

## Second resume attempt (2026-09-18 evening)

- `xinghanbo-eval` was confirmed `RUNNING` on node `qb-prod-4090-gpu068` with one RTX 4090.
- The old A-group launcher had attempted `t7 baseline` at `2026-09-18T11:10:51+00:00`, but exited before the first episode with code 1 and produced no `summary.json`.
- Failure signature: MuJoCo/robosuite EGL enumerated zero devices immediately after the notebook resumed (`MUJOCO_EGL_DEVICE_ID ... between 0 and -1`).
- A later short diagnostic succeeded: JAX saw one CUDA device, PyTorch reported one CUDA device, and `mujoco.egl.eglQueryDevicesEXT()` returned one EGL device. This identifies the failure as a transient GPU/EGL initialization window, not a task result.
- Planned all-suite queue root: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/libero_screening_20260918`.
- Planned order: `libero_spatial_swap` t7-t10, then `libero_object_swap` t1-t10, then `libero_object_task` t1-t10; each task baseline then W0, with existing valid `summary.json` files skipped.
- Planned B/C W0 pack: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/vla-recovery-pipeline/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914` (last observed md5 `941d3d6c435fb96a377103747a8e4c0e`).
- The notebook changed to `PENDING` during the remote command that would write and launch `run_all_suites_screen.sh`. Therefore script creation and process launch are **unconfirmed** and must be checked before assuming the batch is running.

Remote files to inspect when the instance is RUNNING again:

- `$RUN_ROOT/status/progress.tsv`
- `$RUN_ROOT/status/run_suite_screen.pid`
- `$RUN_ROOT/task07_baseline_seed51_65_mrs200.log`
- any `$RUN_ROOT/*/summary.json`

## Resume plan

When `xinghanbo-eval` is `RUNNING` again:

1. Check notebook status first.
2. Check whether `$BATCH_ROOT/run_all_suites_screen.sh`, `$BATCH_ROOT/status/master.pid`, and a live matching process exist. The previous creation/launch command did not return successfully.
3. Inspect all existing `summary.json` files. If the master is absent or dead, recreate/relaunch it; it must skip any valid summaries and resume at the first missing lane.
4. Confirm the first lane is actually running by checking one process/GPU snapshot and the first log after policy setup. Do not continuously watch after confirmation.
5. After each suite finishes, write its requested aggregate report and commit once for that suite; then perform at most one lightweight mining attempt for any task whose baseline and W0 are both below 9/15.

Do not poll while the notebook is `PENDING`.

## Third resume attempt (2026-09-18 evening)

- Notebook was confirmed `RUNNING` on `qb-prod-4090-gpu196`; JAX and EGL each saw one GPU/device.
- Remote batch root still had no master script, master PID, master progress file, running evaluator, or valid `summary.json`.
- A complete resumable launcher was prepared locally at `E:\VLA_recovery_workspace\run_all_suites_screen_20260918.sh`.
- During the upload command the notebook changed from `RUNNING` to `CREATING`; the CLI rejected the transfer before launch. Treat the remote master script and process as absent until explicitly verified.
- Next resume: confirm `RUNNING`, upload that prepared launcher to `$BATCH_ROOT/run_all_suites_screen.sh`, normalize line endings, launch it with `nohup setsid`, then confirm one evaluator process and GPU activity once.
