# LIBERO Spatial-Swap Task03 Cross-Suite Mining Report

Date: 2026-09-16

Suite: `libero_spatial_swap`

Task: `libero_spatial_swap` task03

Language (from BDDL `:language`): `Pick the akita black bowl from table center and place it on the plate`

Goal: `(And (On akita_black_bowl_1 plate_1))` — object goal, no region fold

Status: `covered` by the inherited pack (W0 = 12/15 = 0.80 >= 0.6); zero writes

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task03_newtree_20260916`

Local archive: `remote_outputs/libero_spatial_swap_task03_newtree_20260916`

## Suite task_id -> BDDL -> language map (read from the suite, authoritative)

Read directly from the `LIBERO_SPATIAL_SWAP` benchmark class (`from libero.libero import benchmark`), not inferred from filenames or the preview list. This table is the reference for the rest of the suite campaign.

| task | bddl file | `:language` |
| --- | --- | --- |


Note: t7's filename says "cookie box" while its `:language` says "cookies box"; the matrix uses `:language`.

## Outcome

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off, `max_recovery_calls=0`, mrs200 | 0/15 = 0.000 | seeds 51-65 |
| W0 | pack, mining, `max_recovery_steps=200` | **12/15 = 0.800** | >= 0.6 gate -> covered, zero writes |
| W1 | not run | - | no write, no admission |

Same runner/config family as task01 (run-local LIBERO config, `grasp_dof=6`, bddl language sources, explicit `--skill_pack`).

## Grounding Conclusion

Baseline `query_trace.jsonl` first rows, 15/15 episodes:

```text
target_name        = akita_black_bowl_1_main
goal_name          = plate_1_main
bddl_goal_surfaces = [plate_1_main]
bddl_goal_atoms    = on(akita_black_bowl_1_main, plate_1_main)
```

Object goal, no fold.

## Language Collision (pre-check verified)

Programmatic check of all 10 pack triggers against t2's actual language: exactly one hit —

```text
bowl_plate_pick_lost_or_wrong_intent   (bowl.*plate|plate.*bowl)
```

`black_bowl_next_to_plate_wrong_object_handoff` does NOT hit (t2 is "next to the ramekin", not "next to the plate"), matching the supervisor's pre-computation. The full 10x10 matrix against the authoritative language list is identical to the one in the task01 report with corrected column labels (t1 between-plate-ramekin, t2 table-center, t3 table-center, t4 on-cookie-box, t5 top-drawer-cabinet, t6 on-ramekin, t7 next-cookie-box, t8 on-stove, t9 next-plate, t10 on-cabinet).

## W0 Firing Ledger (attribution)

Exactly one skill fires on this task —

```text
bowl_plate_pick_lost_or_wrong_intent (GS09, inherited)
episodes: all 15 (seeds 51-65), 25 recovery calls total
first query indices: q5-q6 (retries on seeds 58/59/61/63 up to 4 calls)
```

No other skill became winner.

## Paired Decomposition (baseline vs W0, aligned by seed)

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | none | 0 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | 51, 52, 53, 54, 55, 56, 57, 59, 60, 62, 64, 65 | 12 |
| `regression` | none | 0 |
| `still_failing` | 58, 61, 63 | 3 |

Attribution: all 12 gain episodes fired GS09; the gain belongs entirely to the inherited GS09 family, no new artifacts this round. Seeds 58/61/63 also fired GS09 (3-4 calls each) but recovery did not convert them.

## Offline Scan + Admission (mandatory gates)

Not applicable: zero writes this round.

## Artifacts

- Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task03_newtree_20260916`
- Launch script (server, LF): `/mnt/nas/gezuhao/xinghanbo/logs/launch_ss_t02_lane_20260916_lf.sh`
- Local archive: `remote_outputs/libero_spatial_swap_task03_newtree_20260916` (225 files, 37.7 MB, frames dirs excluded)

## Conclusion

Task03 is covered on arrival by the inherited GS09 family: baseline 0/15, W0 12/15 (>= 0.6), zero writes, zero regressions, clean object-goal grounding. Third consecutive same-pattern coverage in this suite.