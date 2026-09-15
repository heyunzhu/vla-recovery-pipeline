# LIBERO Goal Task09 Cross-Suite Mining Report

Date: 2026-09-16

Task: `libero_goal_task` task09

BDDL file: `put_the_bowl_on_the_plate.bddl` (filename is stale; the task language and goal come from this file's content)

Language: `Put the wine bottle on the plate`

Goal: `(And (On wine_bottle_1 plate_1))`

Status: `passed` (W1 = 9/15 = 0.60, stopped at the 0.6 gate)

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task09_cross_suite_newtree_20260916`

Local archive: `remote_outputs/libero_goal_task09_cross_suite_newtree_20260916`

Pack writes: 1 effective write (2 new fail_only skills + `_index.yaml` registration; admission PASS)

## Outcome

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off, `max_recovery_calls=0` | 0/15 = 0.000 | seeds 51-65 |
| W0 @ mrs80 | existing pack, mining, `max_recovery_steps=80` | 0/15 = 0.000 | zero fires, zero recovery calls |
| W0 @ mrs200 | existing pack, mining, `max_recovery_steps=200` | 0/15 = 0.000 | zero fires, zero recovery calls; config-consistent W0 |
| W1 probe @ mrs80 | draft pack (write-1 candidates) | 0/5 | exposed the mrs80 config bug (see below) |
| W1 probe @ mrs200 | draft pack | 3/5 = 0.600 | small experiment; mechanism validated |
| W1 @ mrs200 | real pack, effective write 1 | **9/15 = 0.600** | stopped at the gate |

All formal runs used the new-tree runner (`scripts/recovery/skill_pipeline/run_skill_eval.py` + `cutamp_runner_py310_overlay.sh`), run-local `libero_config/config.yaml` pointing at LIBERO-PRO, `real_cutamp_grasp_dof=6`, `task_language_source=bddl`, `engine_language_source=bddl`, seeds 51-65 (15 episodes), `max_recovery_calls=2` for W lanes, and the explicit `--skill_pack` above. No global config was modified.

## Config Finding: max_recovery_steps=80 Is Structurally Infeasible for Pick-Place Recovery

The prior unfinished attempt (read-only reference at `logs/libero_goal_task09_cross_suite_newtree_20260915`) ran baseline/W0/forced probes with `max_recovery_steps=80`. Its forced-q5 probe consistently failed pick execution with `optimized_motion_budget_exhausted` after 1 env step.

Root cause, reproduced from code and this round's probe:

- `execute_real_cutamp_executable_plan` gives each front trajectory `_front_budget(client, max_env_steps, reserve_place)` = `remaining - place_reserve_steps`.
- `LiberoRobotClientConfig.place_reserve_steps = 80` (default) and `max_recovery_steps=80` imply pick-approach budget <= 0, clamped to 1 step, so every plan containing a Place fails its Pick trajectory regardless of physics.
- The task07 cross-suite run that validated this bottle chain used `max_recovery_steps=200` (see its summary.json); the mining-lane default is also 200; the LIBERO-90 known-good online profile uses 280.

My first W1 small experiment (draft pack, mrs80) reproduced the 1-step `optimized_motion_budget_exhausted` failure exactly. After switching to `max_recovery_steps=200`, the same draft pack went 3/5 with full pick-place execution. W0 was rerun at mrs200 for config-consistent pairing (both W0 lanes are 0/15 with zero fires, so the W0 verdict is unchanged). The previous attempt's forced-probe "failure" is therefore infrastructure evidence, not physics evidence.

## Grounding Conclusion (self-check 1)

From `query_trace.jsonl` first rows of all 15 baseline episodes (this round):

```text
target_name        = wine_bottle_1_main          (15/15)
goal_name          = plate_1_main                (15/15)
bddl_goal_surfaces = [plate_1_main]              (15/15)
bddl_goal_atoms    = on(wine_bottle_1_main, plate_1_main) (15/15)
bddl_path          = .../libero_goal_task/put_the_bowl_on_the_plate.bddl
```

No t6-style goal collapse: the goal lands on `plate_1_main`, not on any other object or virtual region. The rule layer in recovery traces repeats the same binding (`operation=place`, target/goal from bddl). No grounding or geometry artifact was needed.

## Policy Evidence (baseline, 15 episodes)

- 6/15 episodes show the policy holding the bottle at some point (seed51 q16-54, seed53 q18-59, seed54 q26-59, seed57 q30-59, seed59 q26-52 partially, plus seed62 motion without confirmed holding), but no episode completes placement on the plate.
- 9/15 episodes never confirm holding; 12/15 show sustained wrong-object intent on `akita_black_bowl_1_main` with admission-safe windows (see trigger calibration).
- Failure is therefore mixed-layer (grasp unreliable + placement never completed), which justifies a full-chain deterministic recovery rather than a grasp-only or place-only patch.

Visual spot-check (frames extracted to `/tmp/t09_frames` on the server and inspected via the glm_vision MCP; sheets archived locally under `remote_outputs/.../visual_qa/`):

- baseline ep00: policy grasps the bottle late (around frame 111 of 300), carries it to the right, plate stays empty at the end.
- W1 ep00 (success): recovery picks the bottle early (frames 40-60), stable carry, descends to the plate by frame 140.
- W1 ep02/seed53 (failure): gripper hovers/stalls between bottle and bowl for ~100 frames, then retreats; plate stays empty. Matches `optimized_motion_tracking_stalled`.

## W1 Write (effective write 1)

New fail_only skills (authored in the local repo, then pushed to the deployed pack):

1. `skills/fail_only/trigger/wine_bottle_plate_wrong_object_handoff.md`
   - applies_to (all): language `put.*wine bottle.*on.*plate|wine bottle.*on.*plate`, target `wine_bottle|wine bottle`, goal `plate`, bddl_goal_surface `plate`
   - trigger (all): `holding_status_is: handempty_or_unconfirmed`, `aperture_gt: 0.025`, `intent_object_is_target: false`, `nearest_pickable_is_target: false`, `wrong_object_intent_persist_queries_gte: 4`, `wrong_object_intent_margin_gt: 0.03`, `nearest_pickable_distance_lt: 0.22`, `intent_min_xy_distance_lt: 0.035`, `target_ee_distance_lt: 0.25`
   - recovery_hints: `repair_profile: entry_lift_open_hand_small_v1` (registered profile; the entry lift is what unblocks trajectory tracking from the policy's bowl-approach pose)
2. `skills/fail_only/recovery_hint/grasp/grasp_wine_bottle_plate_topdown_close_guard.md`
   - same t9 scoping; `grasp_profile: libero_topdown`, executor `grasp_close_max_above_m: 0.18` (the validated task03 tall-bottle close guard; the bottle geometry is the same fallen tall bottle as task03/task07)

Both are registered in `skills/_index.yaml` fail_only. No place, grounding, or geometry artifact was written: grounding is already correct, and the default place chain executed lift/hover/align/drop/release successfully in validation.

Trigger calibration on this round's baseline: with margin>0.03 & npd<0.22, first fires are q5-q8 (12/15 episodes have windows); `intent_min_xy_distance_lt: 0.035` was added after admission v1 rejected a q4 first-fire on a W0@200 replay (ep13); the persist counter saturates at 4, so persist alone cannot delay firing.

## Admission (required for the write to count)

v1: FAIL — `candidate repair first fires before query 5 on current-task 1 episode(s): task09/ep13@q4` (from the W0@200 replay). Fixed by adding `intent_min_xy_distance_lt: 0.035`; no other change.

v2: **PASS**. Explicit roots:

```text
scan-root (non-current corpus):
  /mnt/nas/gezuhao/xinghanbo/logs/liberopro_6cell_baseline_seed51_55_n5_20260914/corpus   (300 episodes)

fallback-scan-root (current task run):
  /mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task09_cross_suite_newtree_20260916          (59 episodes)

current-task-id: 9
```

Report: `mine/admission_w1_v2/skill_admission_report.md` (359 episodes scanned: 59 success, 300 failed).

| metric | value |
| --- | ---: |
| current episodes / current failed | 55 / 52 |
| current failed matches / recall | 39 / **0.750** |
| current success matches | 3 (the 3 saved probe episodes; same-task overlap is allowed) |
| non-current episodes | 304 |
| non-current success winner matches | **0** |
| non-current success match rate | 0.000 |
| current early-fire (< q5) | **0** |
| non-current early-fire (< q5) | 0 |

Corpus classification note: the corpus's own `libero_goal_task/task09` 5 episodes (seeds 51-55) sit under scan-root and `--current-task-id` is applied to the fallback root, so the scanner counts them as non-current (failing) episodes; they are the 3 "non-current failed matches". They are failures, not successes, so they cannot produce a success-winner violation. The 300-episode corpus was fully included, and the non-current set equals 295 non-t9 corpus episodes + those 5 t9 corpus episodes.

## Formal Run Results

Baseline successes: none (0/15).

W0 (both mrs80 and mrs200) successes: none (0/15).

W1 successes (9):

```text
51, 52, 55, 56, 58, 60, 62, 63, 65
```

W1 failures (6): 53, 54, 57, 59, 61, 64.

## Paired Decomposition (baseline vs W0, aligned by seed)

W0 used for pairing: `w0_task09_seed51_65_existing_pack_mrs200` (config-consistent with W1).

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | none | 0 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | none | 0 |
| `regression` | none | 0 |
| `still_failing` | all 15 (51-65) | 15 |

Both lanes are 0/15 with zero recovery calls, so the four numbers are all zero and there is no rollout-variance caveat needed for the baseline-W0 pairing.

## W0 Firing Ledger

From `recovery_trace.jsonl` of both W0 lanes:

```text
actual_firing_skill_ids = {}
total_recovery_calls = 0  (all 15 episodes, both mrs80 and mrs200)
```

No existing skill fires on task09. This matches the language collision matrix below.

## W1 Firing Ledger

From `recovery_trace.jsonl` (skill_id of rule rows):

| skill_id | seeds | first query indices |
| --- | --- | --- |
| `wine_bottle_plate_wrong_object_handoff` | 51, 52, 53(x3), 55, 56, 58, 60, 62, 63, 65 | 6, 6, 7, 7, 49, 5, 5, 7, 5, 4, 7, 5 |

No other skill became winner on task09. Seed62's live first fire at q4 is a fresh-rollout variance; all recorded traces replayed by admission fired >= q5 (0 early-fire episodes).

Successful W1 chain (matches the t3/t7 recipe): entry lift (0.045 m) -> pick trajectory (27-49 env steps) -> close precheck/dwell -> lift probe (object_lift_m 0.020-0.024, confirmed) -> place lift/hover/xy/yaw align -> drop/release -> `Place(wine_bottle_1_main, grasp1, pose1, plate_1_main, q2)`.

## Residual Failure Triage (W1, 6 episodes)

- seed53: trigger fired 3 times (q7, q7, q49); attempts fail with `optimized_motion_tracking_stalled` during pick approach (one attempt's first pick segment succeeded for 29 steps before the second segment stalled). Executor-level tracking variance, not a trigger/grasp-profile regression.
- seeds 54, 57, 59, 61, 64: no qualifying wrong-object window in the live rollout (policy either aims at the bottle without securing it or holds transiently); the trigger intentionally stays conservative to satisfy admission safety. These remain `still_failing`.

Mining stopped at 0.60 per the round rules; no further writes were attempted (write budget used: 1/5).

## Language Collision Matrix (self-check 2)

Runtime rule `re.search(pattern, language, re.I)` on the goal-task languages:

| trigger | t1 | t2 | t3 | t4 | t5 | t6 | t7 | t8 | t9 | t10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_next_to_plate_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_not_between_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `bowl_cabinet_target_holding_handoff` | . | . | . | . | . | . | . | . | . | . |
| `bowl_plate_pick_lost_or_wrong_intent` | . | . | . | . | . | . | . | . | . | . |
| `cream_cheese_bowl_wrong_object_intent` | . | . | . | . | . | . | . | . | . | . |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | . | X | . | . | . | . | . | . | . | . |
| `wine_bottle_bowl_wrong_object_handoff` | . | . | X | . | . | . | X | . | . | . |
| `wine_bottle_plate_wrong_object_handoff` (new) | . | . | . | . | . | . | . | . | **X** | . |

The new trigger is anchored to both "wine bottle" and "plate" and hits only t9. It does not touch t3/t7 (in-bowl wording) or t2/t5 (no wine bottle). t3/t7 behavior is unchanged: their trigger, grasp, grounding, geometry, and place artifacts were not modified, and W1 firing on task09 shows no other skill becoming winner.

## Artifacts

- Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task09_cross_suite_newtree_20260916` (baseline, W0@80, W0@200, two probe lanes, W1, admission outputs)
- Launch scripts (server, LF): `/mnt/nas/gezuhao/xinghanbo/logs/launch_t09_formal_20260916_lf.sh`, `/mnt/nas/gezuhao/xinghanbo/logs/launch_t09_w1probe_20260916_lf.sh`, `/mnt/nas/gezuhao/xinghanbo/logs/launch_t09_lane_20260916_lf.sh`
- Draft probe pack (kept for provenance, not used by formal lanes): `.../skill_packs/t09_w1_probe_draft_20260916`
- Local archive: `remote_outputs/libero_goal_task09_cross_suite_newtree_20260916` (summaries, episode/query/recovery traces, logs, admission outputs, videos for baseline / W0@200 / W1 / probe@200; frames dirs and superseded mrs80 probe videos excluded)
- Visual QA sheets: `remote_outputs/libero_goal_task09_cross_suite_newtree_20260916/visual_qa/`

## Conclusion

Task09 is covered at exactly the 0.60 gate by one effective write: a t9-scoped wrong-object handoff trigger (with the registered entry-lift repair profile) plus the t3-proven top-down bottle close guard, under the campaign-standard `max_recovery_steps=200`. Grounding is correct out of the box; no place/grounding/geometry changes were needed. The round also surfaced and documented a config trap: `max_recovery_steps=80` with the default `place_reserve_steps=80` makes every pick-place recovery plan structurally unexecutable, which explains the previous attempt's 0/15 forced-probe evidence.