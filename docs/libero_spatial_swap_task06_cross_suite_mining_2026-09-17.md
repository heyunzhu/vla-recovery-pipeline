# LIBERO Spatial-Swap Task06 Cross-Suite Mining Report

Date: 2026-09-18

Suite: `libero_spatial_swap`

Task: task06

Filename: `pick_up_the_black_bowl_on_the_ramekin_and_place_it_on_the_plate.bddl`

Language: `Pick the akita black bowl on the ramekin and place it on the plate`

Goal: `(And (On akita_black_bowl_1 plate_1))` - object goal, no region fold

Status: `covered-by-W0` (baseline 0/15; W0 15/15; W1 not run because no new skill was needed; zero effective writes; deployed pack untouched, remote `_index.yaml` md5 pre/post `ed2f95715177a83b3078381ed8b01ec5`)

Run code checkout: `8e948289a3787c308e792f3a63e6f39b5994e7c5` on `feature/recovery-mining-campaign`. Remote worktree note: only dirty bit was executable mode on `scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh` (`100644 -> 100755`), no content diff.

Pack: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/vla-recovery-pipeline/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916`

Remote run root: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/libero_spatial_swap_task06_newtree_20260918`

Evidence summary: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/libero_spatial_swap_task06_newtree_20260918/status/task06_evidence_summary.json`

Local archive: not pulled this round; file-backed evidence remains on Inspire shared disk under the run root above.

## Infrastructure

This round ran on Inspire notebook `xinghanbo-eval` in workspace `可上网GPU资源` while the instance was `RUNNING`.

- GPU: single RTX 4090, `CUDA_VISIBLE_DEVICES=0`, `XLA_PYTHON_CLIENT_PREALLOCATE=false`.
- Environment: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi` verified usable (`import libero`, `import mujoco`, JAX CUDA device visible).
- Suite source: public `LIBERO-PRO` clone already present at `/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo/LIBERO-PRO`; no old 4090 inference server was used. The run-local `libero_config/config.yaml` points `benchmark_root`, `bddl_files`, `init_states`, and `assets` to the LIBERO-PRO tree / shared assets.
- Runner setup: SSD was full for new outputs, so all run artifacts were written to HDD under the run root. A tiny run-local Python shim was used only to make the LIBERO-PRO nested `libero.libero` package import ahead of the installed LIBERO package.
- BDDL check: task06 `:language` matches the authoritative map, and the goal atom is exactly `on(akita_black_bowl_1, plate_1)`.

## Probe

The requested small probe answered the task04-family concern before burning full time.

| lane | config | result | conclusion |
| --- | --- | ---: | --- |
| probe baseline | seeds 51-55, skills off, mrs200 | 0/5 = 0.000 | policy alone fails |
| probe W0 | seeds 51-55, pack on, mrs200 | 2/5 = 0.400 | W0 can fire and convert, so this is not task04's structural `target_ee_distance_lt: 0.16` blocker |

Probe artifacts:

- `probe_baseline_task06_seed51_55_mrs200/summary.json`
- `probe_w0_task06_seed51_55_mrs200/summary.json`

## Formal Outcome

Formal lanes used seeds 51-65, `max_recovery_steps=200`, `real_cutamp_grasp_dof=6`, run-local LIBERO config, and the same real cuTAMP backend settings as the prior spatial-swap campaign.

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off | 0/15 = 0.000 | all seeds 51-65 failed |
| W0 | deployed pack on | **15/15 = 1.000** | `bowl_plate_pick_lost_or_wrong_intent` converted every seed |
| W1 | not run | - | no write needed because W0 already reached 15/15 |

Formal artifacts:

- `formal_baseline_task06_seed51_65_mrs200/summary.json`
- `formal_w0_task06_seed51_65_mrs200/summary.json`
- per-episode `query_trace.jsonl` and `recovery_trace.jsonl` under each lane
- compact evidence digest: `status/task06_evidence_summary.json`

## Structural Trigger Check

The task04 hypothesis does not hold for task06. In formal W0, the actual recovery firing distances all satisfy the inherited GS09 `target_ee_distance_lt: 0.16` gate:

```text
fired target_ee_distance_m:
min=0.0787, p25=0.1151, median=0.1277, p75=0.1406, max=0.1518
```

Across all W0 queries, target-to-EE distance ranged from `0.0787` to `0.2934` m, but the successful trigger windows occurred below 0.16 m. The probe therefore correctly escalated to formal W0 rather than stopping as a blocker.

## W0 Firing Ledger

Only one skill became the winner:

```text
bowl_plate_pick_lost_or_wrong_intent
unique recoveries: 16 across 15 episodes
successful episodes: 15/15
```

Per-seed ledger from the episode log and de-duplicated recovery trace:

| seed | result | recoveries | winner query / fired distance |
| ---: | --- | ---: | --- |
| 51 | success | 1 | q5 / 0.135 m |
| 52 | success | 1 | q5 / 0.144 m |
| 53 | success | 1 | q5 / 0.152 m |
| 54 | success | 1 | q5 / 0.140 m |
| 55 | success | 1 | q5 / 0.111 m |
| 56 | success | 1 | q5 / 0.107 m |
| 57 | success | 1 | q5 / 0.098 m |
| 58 | success | 1 | q5 / 0.125 m |
| 59 | success | 1 | q5 / 0.133 m |
| 60 | success | 2 | q6 / 0.116 m; q7 / 0.079 m |
| 61 | success | 1 | q4 / 0.148 m |
| 62 | success | 1 | q5 / 0.119 m |
| 63 | success | 1 | q5 / 0.130 m |
| 64 | success | 1 | q4 / 0.142 m |
| 65 | success | 1 | q5 / 0.120 m |

Note: seed60's `recovery_trace.jsonl` contains duplicate rule JSON lines for q6/q7; the evidence summary de-duplicates by `(episode, query, skill)`, matching the episode log's 16 total recovery calls.

## Four-Component Decomposition

Paired baseline vs W0 over seeds 51-65:

```text
policy_only=0
unnecessary_handoff=0
recovery_gain=15
regression=0
still_failing=0
```

Interpretation: every success is a recovery gain; there were no policy-only successes and no W0 regressions.

## Collision Matrix

Runtime collision matrix for non-zero rows in formal W0:

| skill id | applies_to query count | would-fire query count | unique recovery success count | interpretation |
| --- | ---: | ---: | ---: | --- |
| `bowl_plate_pick_lost_or_wrong_intent` | 90 | 16 | 16 | intended applicable skill; fires under GS09's close-target bowl-to-plate gate |
| `bowl_cabinet_target_holding_handoff` | 0 | 1 | 0 | trigger predicates could pass once, but `applies_to` rejects task language and BDDL goal surface; no collision |

All other loaded W0 skills had zero applicable+would-fire overlap on this task. The dominant non-applicable reasons in the diagnostics are task-language mismatch, target-name mismatch, or BDDL goal-surface mismatch; the full counts are in `status/task06_evidence_summary.json`.

## Two Gates / Admission Roots

No new skill was authored, promoted, or admitted in this round.

- Admission roots: not applicable (`none`)
- 60-task offline trigger scan: not run because there was no candidate write
- Admission winner check: not run because there was no candidate write
- Pack md5 pre-run: `ed2f95715177a83b3078381ed8b01ec5`
- Pack md5 post-run: `ed2f95715177a83b3078381ed8b01ec5`

## Conclusion

Task06 is covered by the existing deployed pack. The requested structural probe showed task06 is not the task04-style unreachable-trigger blocker: the inherited bowl-to-plate GS09 trigger reaches the target within the 0.16 m gate and W0 converts the full formal set. Baseline remains 0/15, W0 is 15/15, W1/admission are intentionally skipped because no new write is needed. Stop here for supervisor review; do not start task07 in this task06 request.
