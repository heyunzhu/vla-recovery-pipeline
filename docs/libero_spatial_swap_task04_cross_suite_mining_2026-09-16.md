# LIBERO Spatial-Swap Task04 Cross-Suite Mining Report

Date: 2026-09-16

Suite: `libero_spatial_swap`

Task: task04

Language: `Pick the akita black bowl on the cookie box and place it on the plate` (suite map: see task02 report; note `:language` says "cookies box", filename says "cookie box")

Goal: `(And (On akita_black_bowl_1 plate_1))` - object goal, no region fold

Status: `not passed / blocker-with-diagnostics` (baseline 0/15, W0 0/15 with zero GS09 fires; best candidate failed admission recall; zero effective writes; pack reverted to canonical 23-skill state, `_index.yaml` md5 `941d3d6c435fb96a377103747a8e4c0e`)

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_spatial_swap_from_goal_task_mining_base_20260916`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task04_newtree_20260916`

Local archive: `remote_outputs/libero_spatial_swap_task04_newtree_20260916`

## Outcome

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off, mrs200 | 0/15 = 0.000 | seeds 51-65 |
| W0 | pack, mining, mrs200 | 0/15 = 0.000 | ZERO recovery calls - GS09's `target_ee_distance_lt: 0.16` never holds in this scene (min EE-bowl distance 0.19-0.26 m) |
| W1 probes x4 | draft pack, seeds 51-55 | 0/5, 1/5, 0/5, 1/5 | probe1/3: planner CUDA OOM (infra); probe2/4 clean windows: 2 full-chain successes, 2 physical failures, rest no-window |
| W1 | not run | - | admission failed twice -> no effective write; draft reverted |

## Grounding Conclusion

Baseline first rows, 15/15: `target_name=akita_black_bowl_1_main`, `goal_name=plate_1_main`, `bddl_goal_surfaces=[plate_1_main]`, atoms `on(akita_black_bowl_1_main, plate_1_main)` - clean object goal.

## Failure Analysis (static + dynamic + visual)

Two failure families in baseline (15/15 fail, `target_motion_m=0` everywhere):

1. **Wrong-bowl fixation (9/15 episodes)**: the scene has two identical black bowls; the target sits ON the cookie box while the policy's dominant intent is `akita_black_bowl_2_main` (on the cabinet side). Admission-safe q13-q47 wrong-object windows exist under t9-family predicates. This family IS trigger-expressible.
2. **Correct-intent hover-no-grasp (6/15 episodes)**: policy aims at the right bowl but hovers (~0.19-0.26 m) and never closes. NO window under any wrong-object predicate combination; no registered predicate expresses "correct intent, target static, open hand, no progress" without target-approach-as-failure (banned).

Visual QA (glm_vision, sheet in `visual_qa/t04_base_ep00_sheet.jpg`, baseline ep00): first half hovers over the decoy bowl, second half over the target bowl on the box, neither bowl ever moves, plate stays empty - matches both trace families.

## Candidate Write and the Two Gates (why it did not count)

Candidate: `bowl_cookie_box_wrong_bowl_handoff` (draft preserved at `remote_outputs/.../mine/drafts/`): language `bowl.*on the cookies? box.*plate` (does NOT match t7 "next to the cookies box"), target/goal/surface anchors, t9-family predicates (persist>=4, margin>0.03, npd<0.25, teed<0.35), entry-lift repair profile.

Gate 1 - full offline trigger scan (PASS):
```text
tool: scripts/recovery/skill_pipeline/scan_skill_triggers.py
run-dirs: /mnt/nas/gezuhao/xinghanbo/logs/liberopro_6cell_baseline_seed51_55_n5_20260914/corpus (all 60 units = 6 cells x 10 tasks x 5 seeds = 300 episodes)
          + current run root (50 episodes)
outputs: /mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task04_newtree_20260916/mine/offline_scan_w1/{offline_skill_scan.json,episode_skill_scan.csv,...}
per-cell result: new-skill winners ONLY in the spatial_swap cell (task04, 3 corpus episodes, all FAILURES); zero hits in goal_swap / goal_task / object_swap / object_task / spatial_task cells; the only 2 success winners are same-task probe episodes (allowed)
non-current success winner matches = 0
```

Gate 2 - admission (FAIL, twice):
```text
tool: scripts/recovery/skill_pipeline/run_skill_admission.py
scan-root: the 300-episode corpus; fallback-scan-root: run root (v1) then formal-lanes-only subset baseline+W0 (v3); --current-task-id 4
outputs: .../mine/admission_w1/ and .../mine/admission_w1_v3/
v1: current failed recall 0.56 < 0.60 (scan diluted by 20 same-seed diagnostic probe duplicates)
v3: current failed recall 0.533 = 16/30 < 0.60 (baseline 9/15 + W0 7/15 windows; the other episodes have no wrong-object window at ANY threshold)
```

Since the wrong-object family ceiling is 16/30 = 0.533, no predicate relaxation can reach 0.60; covering family-2 needs runner predicates that do not exist (see Failure Analysis). Per the rules (admission fail -> not an effective write), the deployed pack was reverted and verified (`_index.yaml` md5 back to `941d3d6c...`, 23 fail_only entries).

## Physics Evidence (what works and what does not)

Clean-GPU probe windows (probe2 GPU0, probe4 GPU3): 2/2 fired-and-planned episodes completed the full chain (rule -> entry lift -> pick -> close -> lift probe confirmed -> place -> success). The 2 physical failures were `optimized_motion_tracking_stalled` during pick plus `Motion planning failed n/n` on replans - the same bowl-on-box pick difficulty family seen on t9-seed53. So the backend CAN solve this task; the blockers are trigger-family coverage (family-2) and pick-execution variance.

Infrastructure note: probes 1 and 3 failed purely from planner CUDA OOM - transient 34 GB workers from another user's dataset-collection job roam all 4 GPUs and collide with the cuTAMP planning subprocess. These are infra failures, not physics; documented per the t9 mrs80 precedent.

## W0 Firing Ledger

Empty: zero recovery calls in all 15 W0 episodes. GS09's approach-window predicate (`target_ee_distance_lt: 0.16`) is structurally unsatisfiable in this scene (min distance 0.19-0.26 m), so the inherited family that covered t1-t3 does not fire on t4.

## Paired Decomposition (baseline vs W0)

policy_only=0, unnecessary_handoff=0, recovery_gain=0, regression=0, still_failing=15.

## Artifacts

- Remote run root (baseline, W0, 4 probe lanes, offline scan, admission v1/v3): `/mnt/nas/gezuhao/xinghanbo/logs/libero_spatial_swap_task04_newtree_20260916`
- Draft skill (not in pack): `remote_outputs/.../mine/drafts/bowl_cookie_box_wrong_bowl_handoff.md`
- Launch script (server): `/mnt/nas/gezuhao/xinghanbo/logs/launch_ss_t04_lane_20260916_lf.sh`
- Local archive: 429 files, 179.5 MB (frames excluded; `mine/current_formal_lanes` copy excluded)

## Conclusion

Task04 is NOT covered (W0 0/15, zero fires) and the round produced no effective write. Root causes, file-backed: (a) the inherited GS09 family cannot fire here by construction (0.16 m approach window unreachable for a bowl on a box); (b) the wrong-object trigger family that rescues 9/15 baseline episodes tops out at 0.533 current-failure recall, below the 0.60 admission floor, because the remaining 6/15 episodes are correct-intent hover-no-grasp with no expressible failure predicate; (c) when it does fire with a clean GPU, the backend converts (2/2), with residual pick-stall variance. Verdict: blocker pending either a runner-side predicate for the correct-intent-stuck family or a policy-side fix for the bowl-on-box grasp.
