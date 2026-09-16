# LIBERO Spatial-Swap Task05 Cross-Suite Mining Report

Date: 2026-09-16

Suite: `libero_spatial_swap`

Task: task05

Language: `Pick the akita black bowl in the top layer of the wooden cabinet and place it on the plate` (suite map: task02 report; filename says "top drawer", `:language` says "top layer")

Goal: `(And (On akita_black_bowl_1 plate_1))` - object goal, no region fold

Status: `blocker-with-diagnostics` (baseline 0/15; W0 0/15 - first W0 attempt invalidated by planner CUDA OOM, clean-GPU rerun 0/15 with real recovery attempts; best place-budget probe 0/5; zero effective writes; deployed pack untouched, `_index.yaml` md5 `941d3d6c435fb96a377103747a8e4c0e`)

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task05_newtree_20260916`

Local archive: `remote_outputs/libero_spatial_swap_task05_newtree_20260916`

## Outcome

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off, mrs200 | 0/15 = 0.000 | seeds 51-65 |
| W0 (attempt 1, GPU1) | pack, mining, mrs200 | 0/15 INVALID | all 30 recovery plans died with CUDA OOM (GPU contention; lane shared card with roaming 34 GB workers) - kept as `w0_task05_seed51_65_new_pack_oom_gpu1` for the record |
| W0 (clean rerun, GPU2) | same | **0/15 = 0.000** | GS09 fired 15/15 (q5-q26); 13/15 reached close->lift_probe->place; place execution failed |
| W1 probe | draft pack + place-budget hint, seeds 51-55 | 0/5 | hint applied and advanced sub-stages (hover_xy became correct) but no conversion; 3 pick-hold failures (`gripper_closed_but_not_holding`) |
| W1 | not run | - | probe 0/5 -> no effective write |

## Grounding Conclusion

Baseline first rows, 15/15: `target_name=akita_black_bowl_1_main`, `goal_name=plate_1_main`, `bddl_goal_surfaces=[plate_1_main]`, atoms `on(akita_black_bowl_1_main, plate_1_main)` - clean object goal.

## Static Prior Checks (as requested)

1. Drawer state: the BDDL `:init` contains `(Open wooden_cabinet_1_top_region)` - **the drawer starts OPEN**. No `open` articulated primitive is needed; the goal_task `open`-primitive gap does NOT apply here. The bowl starts `(In akita_black_bowl_1 wooden_cabinet_1_top_region)`.
2. Trigger language hits on t5 (verified programmatically): `black_bowl_cabinet_top_to_plate_wrong_object_handoff`, `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff`, `bowl_cabinet_target_holding_handoff`, `bowl_plate_pick_lost_or_wrong_intent`. Unlike task04, the GS09 approach window IS satisfiable here (the drawer opening brings the EE within 0.16 m).

## W0 Firing Ledger (clean rerun)

```text
bowl_plate_pick_lost_or_wrong_intent (GS09, inherited)
episodes: all 15 (seeds 51-65), 2 recovery calls each, first fire q5-q26
```

No other skill became winner (the cabinet-language triggers' predicates did not match before GS09).

## Failure Chain (clean W0, file-backed)

- 13/15 episodes: rule -> pick from drawer -> `grasp_close_precheck` -> `grasp_close_dwell` -> `grasp_lift_probe` (confirmed holding) -> place chain reached.
- Place-stage failures: `place_hover_xy_not_aligned` (13), `trajectory_tracking_budget_exhausted` (15), tracking stalls (10), `place_release_geometry_not_met` (3); plus pick-side `optimized_motion_tracking_stalled` (9) / budget exhausted (6), `gripper_closed_but_not_holding` (2).
- Interpretation: the backend can extract the bowl from the open drawer, but the long cabinet-to-table held transfer cannot finish hover/drop under default budgets, and the deep drawer pick occasionally loses the hold.

## Small Experiment (place budget, draft-only)

Draft `place_bowl_cabinet_drawer_to_plate_hover_budget` (archived at `remote_outputs/.../mine/drafts/`): t5-scoped language `bowl.*top (layer|drawer).*wooden cabinet.*place.*plate`, goal plate, executor budget family proven by the sibling `bowl_plate_*` hints (lift 70/0.014/0.03, hover 0.055/90/0.014, drop 120/0.018, release_z 0.1, dwell 8).

Probe (seeds 51-55, GPU2, clean): **0/5**. The hint verifiably applied (recovery_hints in query trace) and moved episodes further (4/5 reached hover/drop; `place_hover_xy_correct` events appear), but drop still failed, and 3 attempts regressed to `gripper_closed_but_not_holding` at pick. No conversion -> per the round rules (0 conversions -> blocker), no effective write was attempted; the deployed pack was never modified this round (verified md5 above).

## Two Gates

Not applicable: zero effective writes this round (the draft never left the probe pack). The two-gate requirement remains armed for any future write.

## Paired Decomposition (baseline vs clean W0)

policy_only=0, unnecessary_handoff=0, recovery_gain=0, regression=0, still_failing=15 (both lanes 0/15; W0 fired GS09 on every episode but converted none).

## Artifacts

- Remote run root: baseline, OOM-W0 (kept), clean W0 rerun, probe lane, cutamp_debug
- Draft skill (not in pack): `remote_outputs/libero_spatial_swap_task05_newtree_20260916/mine/drafts/place_bowl_cabinet_drawer_to_plate_hover_budget.md`
- Launch script (server): `/mnt/nas/gezuhao/xinghanbo/logs/launch_ss_t05_lane_20260916_lf.sh`
- Local archive: 1194 files, 246.1 MB (frames excluded)

## Conclusion

Task05 is a place-execution blocker, not a grounding or trigger blocker: the drawer starts open (BDDL `:init`), grounding is clean, and GS09 fires on 15/15 - the chain reliably picks the bowl out of the open drawer (13/15 confirmed holding) but cannot finish the held cabinet-to-table transfer (hover alignment, drop budget, release geometry), and the deep-drawer pick hold is intermittently unstable. A proven place-budget family moved sub-stages forward but did not convert (0/5). Zero effective writes; pack unchanged.
