# LIBERO Spatial-Swap Task01 Cross-Suite Mining Report

Date: 2026-09-16

Suite: `libero_spatial_swap` (first task mined in this suite; suite never mined before this round)

Task: `libero_spatial_swap` task01

BDDL file: `pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.bddl`

Language (from BDDL `:language`): `Pick the akita black bowl between the plate and the ramekin and place it on the plate`

Goal: `(And (On akita_black_bowl_1 plate_1))` — object goal, no `*_region` fold involved

Status: `covered` by the inherited pack (W0 = 12/15 = 0.80 >= 0.6); zero writes

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916` (working copy created 2026-09-16 from the frozen goal-task pack; 23 fail_only skills; local and deployed copies LF-normalized identical, sampled md5s verified)

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task01_newtree_20260916`

Local archive: `remote_outputs/libero_spatial_swap_task01_newtree_20260916`

## Outcome

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off, `max_recovery_calls=0`, mrs200 | 1/15 = 0.067 | only seed64 |
| W0 | new pack, mining, `max_recovery_steps=200` | **12/15 = 0.800** | >= 0.6 gate -> covered, zero writes |
| W1 | not run | - | no write, no admission |

Both runs: new-tree runner, run-local `libero_config/config.yaml` (LIBERO-PRO), `real_cutamp_grasp_dof=6`, `task_language_source=bddl`, `engine_language_source=bddl`, seeds 51-65 (15 episodes), `max_recovery_calls=2` for W0, explicit `--skill_pack`.

W1 probe / small experiment: not needed (coverage gate met at W0).

## Grounding Conclusion

Baseline `query_trace.jsonl` first rows, 15/15 episodes:

```text
target_name        = akita_black_bowl_1_main
goal_name          = plate_1_main
bddl_goal_surfaces = [plate_1_main]
bddl_goal_atoms    = on(akita_black_bowl_1_main, plate_1_main)
```

Object goal, no region-to-parent fold. W0 recovery rule rows repeat the same binding (`operation=pick`, target/goal from bddl).

## Language Collision Matrix

Computed with the runtime rule `re.search(pattern, language, re.I)` over YAML-parsed frontmatter, against the **actual BDDL `:language` strings** (note: the pre-flight preview list used different wording — "pick up the black bowl ..." — while the BDDL says "Pick the akita black bowl ..."; the matrix below uses the real strings. Structural conclusion is unchanged: GS09 hits everything).

Column order: between-plate-ramekin (t1), table-center, top-layer-cabinet, next-cookies, next-plate, next-ramekin, on-cookies, on-ramekin, on-stove, on-cabinet.

| trigger | t1 | t2 | t3 | t4 | t5 | t6 | t7 | t8 | t9 | t10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | . | . | X | . | . | . | . | . | . | X |
| `black_bowl_next_to_plate_wrong_object_handoff` | . | . | . | . | X | . | . | . | . | . |
| `black_bowl_not_between_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | . | . | X | . | . | . | . | . | . | X |
| `bowl_cabinet_target_holding_handoff` | . | . | X | . | . | . | . | . | . | X |
| `bowl_plate_pick_lost_or_wrong_intent` | X | X | X | X | X | X | X | X | X | X |
| `cream_cheese_bowl_wrong_object_intent` | . | . | . | . | . | . | . | . | . | . |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | . | . | . | . | . | . | . | . | X | . |
| `wine_bottle_bowl_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `wine_bottle_plate_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |

Correction vs the supervisor's pre-flight table: `plate_stove_open_wrong_intent_pregrasp_handoff` hits the **on-stove** wording (`plate.*stove|stove.*plate`), not "next to the plate". Everything else matches. `black_bowl_not_between_wrong_object_handoff` hits nothing because spatial_swap says "between ..." without "not".

## W0 Firing Ledger (attribution)

From `recovery_trace.jsonl` rule rows: exactly one skill fires on this task —

```text
bowl_plate_pick_lost_or_wrong_intent (GS09, inherited from goal_swap task09)
episodes: all 15 (seeds 51-65), 27 recovery calls total
first query indices: q6 (most episodes), q7 (seeds 62-64), q9/q10 retries on seeds 58/60/64
```

No other skill became winner. The successful chain (e.g. seed51 ep00): rule -> pick trajectories -> `grasp_close_precheck` -> `grasp_close_dwell` -> `grasp_lift_probe` (confirmed) -> place lift/hover/xy/yaw align/drop/release -> `Place(..., plate_1_main, ...)`.

## Paired Decomposition (baseline vs W0, aligned by seed)

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | 64 | 1 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | 51, 52, 53, 54, 55, 56, 57, 58, 62, 63, 65 | 11 |
| `regression` | none | 0 |
| `still_failing` | 59, 60, 61 | 3 |

Attribution: every recovery_gain episode fired `bowl_plate_pick_lost_or_wrong_intent`; the gain belongs entirely to the inherited GS09 skill family, **not** to any new artifact (there are none this round). Seed64 succeeded in both lanes (policy_only, GS09 also fired but did not regress it). Seeds 59/60/61 fired GS09 too (q6-q9, up to 3 calls each) but the recovery did not convert them.

## Offline Scan + Admission (mandatory gates)

Not applicable: zero writes this round. No skill entered the pack, so neither the full offline trigger scan nor admission was required. If a later task in this suite requires a write, both gates must run with:
- offline scan roots: explicit, including all 60 units of the 300-episode corpus (6 cells x 10 tasks x 5 seeds);
- admission roots: corpus (300) + current run root, `--current-task-id <n>`, `non-current success winner matches = 0` required.

## Artifacts

- Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task01_newtree_20260916` (baseline, W0, cutamp_debug)
- Launch script (server, LF): `/mnt/nas/gezuhao/xinghanbo/logs/launch_ss_lane_20260916_lf.sh`
- Local archive: `remote_outputs/libero_spatial_swap_task01_newtree_20260916` (summaries, episode/query/recovery traces, logs, videos; frames dirs excluded)
- Pack setup this round (supervisor-provided, committed with this report): new working pack `libero_spatial_swap_from_goal_task_mining_base_20260916`, goal-task pack frozen (`README` FROZEN note + `catalog.yaml` archived status)

## Conclusion

Task01 is covered on arrival by the inherited GS09 family: baseline 1/15, W0 12/15 (>= 0.6), zero writes, zero regressions. Grounding is clean (object goal `plate_1_main`, 15/15). This is expected cross-suite reuse — the goal_swap task09 skill family was authored for exactly this "black bowl onto plate" language/goal shape.