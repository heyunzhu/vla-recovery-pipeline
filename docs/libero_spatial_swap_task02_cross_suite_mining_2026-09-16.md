# LIBERO Spatial-Swap Task02 Cross-Suite Mining Report

Date: 2026-09-16

Suite: `libero_spatial_swap`

Task: `libero_spatial_swap` task02

Language (from BDDL `:language`): `Pick the akita black bowl next to the ramekin and place it on the plate`

Goal: `(And (On akita_black_bowl_1 plate_1))` — object goal, no region fold

Status: `covered` by the inherited pack (W0 = 12/15 = 0.80 >= 0.6); zero writes

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task02_newtree_20260916`

Local archive: `remote_outputs/libero_spatial_swap_task02_newtree_20260916`

## Suite task_id -> BDDL -> language map (read from the suite, authoritative)

Read directly from the `LIBERO_SPATIAL_SWAP` benchmark class (`from libero.libero import benchmark`), not inferred from filenames or the preview list. This table is the reference for the rest of the suite campaign.

| task | bddl file | `:language` |
| --- | --- | --- |
| t1 | pick_up_the_black_bowl_between_the_plate_and_the_ramekin_and_place_it_on_the_plate.bddl | Pick the akita black bowl between the plate and the ramekin and place it on the plate |
| t2 | pick_up_the_black_bowl_next_to_the_ramekin_and_place_it_on_the_plate.bddl | Pick the akita black bowl next to the ramekin and place it on the plate |
| t3 | pick_up_the_black_bowl_from_table_center_and_place_it_on_the_plate.bddl | Pick the akita black bowl from table center and place it on the plate |
| t4 | pick_up_the_black_bowl_on_the_cookie_box_and_place_it_on_the_plate.bddl | Pick the akita black bowl on the cookie box and place it on the plate |
| t5 | pick_up_the_black_bowl_in_the_top_drawer_of_the_wooden_cabinet_and_place_it_on_the_plate.bddl | Pick the akita black bowl in the top drawer of the wooden cabinet and place it on the plate |
| t6 | pick_up_the_black_bowl_on_the_ramekin_and_place_it_on_the_plate.bddl | Pick the akita black bowl on the ramekin and place it on the plate |
| t7 | pick_up_the_black_bowl_next_to_the_cookie_box_and_place_it_on_the_plate.bddl | Pick the akita black bowl next to the cookies box and place it on the plate |
| t8 | pick_up_the_black_bowl_on_the_stove_and_place_it_on_the_plate.bddl | Pick the akita black bowl on the stove and place it on the plate |
| t9 | pick_up_the_black_bowl_next_to_the_plate_and_place_it_on_the_plate.bddl | Pick the akita black bowl next to the plate and place it on the plate |
| t10 | pick_up_the_black_bowl_on_the_wooden_cabinet_and_place_it_on_the_plate.bddl | Pick the akita black bowl on the wooden cabinet and place it on the plate |

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

`black_bowl_next_to_plate_wrong_object_handoff` does NOT hit (t2 is "next to the ramekin", not "next to the plate"), matching the supervisor's pre-computation. The full 10x10 matrix against the authoritative language list is identical to the one in the task01 report with corrected column labels (t1 between-plate-ramekin, t2 next-ramekin, t3 table-center, t4 on-cookie-box, t5 top-drawer-cabinet, t6 on-ramekin, t7 next-cookie-box, t8 on-stove, t9 next-plate, t10 on-cabinet).

## W0 Firing Ledger (attribution)

Exactly one skill fires on this task —

```text
bowl_plate_pick_lost_or_wrong_intent (GS09, inherited)
episodes: all 15 (seeds 51-65), 21 recovery calls total
first query indices: q8-q9 (retries at q10 on seed54, q19 on seed58, q8 on seed65)
```

No other skill became winner.

## Paired Decomposition (baseline vs W0, aligned by seed)

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | none | 0 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | 51, 52, 53, 55, 56, 57, 59, 60, 61, 62, 63, 65 | 12 |
| `regression` | none | 0 |
| `still_failing` | 54, 58, 64 | 3 |

Attribution: all 12 gain episodes fired GS09; the gain belongs entirely to the inherited GS09 family, no new artifacts this round. Seeds 54/58/64 also fired GS09 (up to 3 calls each) but recovery did not convert them.

## Offline Scan + Admission (mandatory gates)

Not applicable: zero writes this round.

## Artifacts

- Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task02_newtree_20260916`
- Launch script (server, LF): `/mnt/nas/gezuhao/xinghanbo/logs/launch_ss_t02_lane_20260916_lf.sh`
- Local archive: `remote_outputs/libero_spatial_swap_task02_newtree_20260916` (209 files, 35.4 MB, frames dirs excluded)

## Conclusion

Task02 is covered on arrival by the inherited GS09 family: baseline 0/15, W0 12/15 (>= 0.6), zero writes, zero regressions, clean object-goal grounding. Same cross-suite reuse pattern as task01.