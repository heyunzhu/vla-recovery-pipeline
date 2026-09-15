# LIBERO Goal Task10 Cross-Suite Mining Report

Date: 2026-09-16

Task: `libero_goal_task` task10

BDDL file: `put_the_wine_bottle_on_the_rack.bddl` (filename is stale; the task language and goal come from this file's content)

Language: `Put the cream cheese on the rack`

Goal: `(And (On cream_cheese_1 wine_rack_1_top_region))` — a **region goal**, not an object goal

Status: `blocker` (0 effective writes; mining stopped after two 0/5 small experiments reproduced the September capability gap)

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914` (unchanged this round; `_index.yaml` md5 `941d3d6c435fb96a377103747a8e4c0e` identical to the task09 commit)

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task10_cross_suite_newtree_20260916`

Local archive: `remote_outputs/libero_goal_task10_cross_suite_newtree_20260916`

## Outcome

| lane | config | result | notes |
| --- | --- | ---: | --- |
| baseline | skills off, `max_recovery_calls=0`, mrs200 | 0/15 = 0.000 | seeds 51-65 |
| W0 | existing pack, mining, `max_recovery_steps=200` | 0/15 = 0.000 | zero fires, zero recovery calls |
| forced probe | force q5, seeds 51-55, mrs200 | 0/5 | rule layer + planner evidence |
| W1 probe v1 | draft pack (trigger+grounding+geometry+flat-box grasp) | 0/5 | planning partially fixed; execution still fails |
| W1 probe v2 | draft pack (grasp switched to libero_topdown) | 0/5 | 10/10 no satisfying particles (worse) |
| W1 | not run | - | no effective write; both probes 0/5 |

All runs used the new-tree runner, run-local `libero_config/config.yaml` (LIBERO-PRO), `real_cutamp_grasp_dof=6`, bddl language sources, seeds 51-65, and `max_recovery_steps=200` (the campaign standard inherited from the task09 lesson).

## Grounding Conclusion (self-check 1): the fold is real

Static evidence (this round's own files):

- Baseline `query_trace.jsonl` first rows, 15/15 episodes:

```text
target_name        = cream_cheese_1_main
goal_name          = wine_rack_1_main            <- FOLDED to the parent body
bddl_goal_surfaces = [wine_rack_1_top_region]    <- correct at BDDL level
bddl_goal_atoms    = on(cream_cheese_1_main, wine_rack_1_top_region)
```

- Forced-q5 probe rule rows, 5/5 episodes: `operation=place`, `goal_name=wine_rack_1_main`, `bddl_goal_surfaces=[wine_rack_1_top_region]`, followed by `No satisfying particles found after optimizing all 1 plan(s)` in 5/5.

This is the t6-style region-to-parent collapse: BDDL parsing is correct, but the recovery rule layer binds the goal to the coarse rack body. Placing on the coarse body is planner-infeasible.

The pack's registered `wine_rack_top_region_v1` grounding and `wine_rack_top_region_surface_v1` geometry profiles (code alive in `code/grounding_profiles.py` / `code/geometry_profiles.py`) can rewrite the goal back to the region: in probe v1's cuTAMP debug problems, place-form solves carry `goal_atoms = [on(cream_cheese_1_main, wine_rack_1_top_region), handempty()]`. So the fold itself is repairable at pack level; the remaining failures are downstream (below).

## Policy Evidence (baseline)

- `target_motion_m = 0.0` in 15/15 episodes: the policy never moves the cream cheese.
- 6/15 episodes show holding of some object (never the target; the wrong objects are the bowl and the wine bottle).
- `target_ee_distance_m` never goes below 0.163 m: the gripper never reaches the cheese.
- Wrong-object intent (bowl 124 / bottle 88 q-rows in the first 15 queries across episodes) with admission-safe q7+ windows in 15/15 episodes under the draft trigger predicates.

## Language Collision (self-check 2)

Current pack (10 triggers) vs goal-task languages: no trigger has a language hit on task10 (matches the empty W0 firing ledger). The draft trigger pattern `put.*cream cheese.*on.*rack|cream cheese.*rack` matches only t10 — t4 (`...put the cream cheese inside`) and t6 (`Push the cream cheese to the front of the stove`) contain no `rack`. Full matrix (unchanged from task09 for existing skills):

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
| `wine_bottle_plate_wrong_object_handoff` | . | . | . | . | . | . | . | . | X | . |
| `cream_cheese_rack_wrong_object_handoff` (draft, not in pack) | . | . | . | . | . | . | . | . | . | X |

## Formal Run Results

Baseline successes: none (0/15). W0 successes: none (0/15).

### Paired Decomposition (baseline vs W0, aligned by seed)

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | none | 0 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | none | 0 |
| `regression` | none | 0 |
| `still_failing` | all 15 (51-65) | 15 |

### W0 Firing Ledger

From `recovery_trace.jsonl` of all 15 W0 episodes:

```text
actual_firing_skill_ids = {}
total_recovery_calls = 0
```

## Why Blocker (static + dynamic evidence)

Small experiments (draft pack, seeds 51-55, mrs200; probes are not writes):

1. **Draft v1** = trigger (language-anchored, t9-family predicates, entry-lift repair profile) + grounding hint (`wine_rack_top_region_v1`) + geometry hint (`wine_rack_top_region_surface_v1`) + grasp hint (`cream_cheese_flat_box_topdown_deep_v1`): **0/5**.
   - The rewrite works at the problem level (place-form problems carry `on(cream_cheese_1_main, wine_rack_1_top_region)`), and the entry lift executes (2 bridge rows per episode).
   - Remaining failures: place-form solves with `num_satisfying=0` (4), `Motion planning failed for n/n` (3), and pick execution `optimized_motion_tracking_stalled` (12 events; 4 episodes reached execution). Late attempts (after scene perturbation) did find 14-22 satisfying particles but the pick's final approach still stalled.
2. **Draft v2** = same, grasp switched to `libero_topdown`: **0/5**, 10/10 attempts `No satisfying particles` — strictly worse, confirming the flat-box deep sampler was the better of the two available options.

Visual QA (frames from probe-v1 ep03, via glm_vision MCP; sheet in `visual_qa/`): the gripper approaches the white stove board and the bowl instead of cleanly reaching the blue cheese box, gets entangled with the bowl, knocks the wine bottle over, and retreats; the cheese never moves. This matches the `optimized_motion_tracking_stalled` signature at the wrong location.

September cross-check (read-only): the 2026-09-12 campaign spent 3 writes on this task (W0/W1/W2 = 0/5) with the same failure family (`optimized_motion_tracking_stalled`, `No satisfying particles`, `Motion planning failed`, `robot_to_world` / `pos_err`); its assets are quarantined at `/mnt/nas/gezuhao/xinghanbo/openvla-oft/skill_packs/_quarantine_goal_task_residue_20260915` and were only read for reference.

Root-cause statement (two gaps, both beyond current pack-local expression):

1. **Rack-top place planning**: even with the region goal restored and the virtual surface materialized, the optimizer finds zero particles or motion planning fails for all satisfying particles in most attempts — rack collision/reach geometry exceeds the current planner proxies.
2. **Thin-box pick execution in this scene**: available grasp samplers either stall in the final approach (deep flat-box) or cannot produce feasible particles at all (libero_topdown); the approach path interacts with the board/bowl cluster around the cheese.

Because both probes returned 0/5, no effective write was made (writing a 0-value skill family would pollute the pack, as September's quarantine already demonstrated). Drafts are preserved at `remote_outputs/.../mine/drafts/` and on the server inside the probe draft packs for a future engine/planner-level fix.

## Artifacts

- Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task10_cross_suite_newtree_20260916` (baseline, W0, forced probe, two draft-pack probes)
- Launch scripts (server, LF): `/mnt/nas/gezuhao/xinghanbo/logs/launch_t10_lane_20260916_lf.sh`, `/mnt/nas/gezuhao/xinghanbo/logs/launch_t10_probe_20260916_lf.sh`
- Local archive: `remote_outputs/libero_goal_task10_cross_suite_newtree_20260916` (summaries, traces, logs, cutamp debug, videos; frames dirs excluded)
- Diagnostic drafts (not in any pack): `remote_outputs/.../mine/drafts/` (5 files: trigger, grounding, geometry, grasp v1, grasp v2)
- Visual QA sheet: `remote_outputs/.../visual_qa/v1ep03_sheet.jpg`
- September quarantine (read-only reference): `/mnt/nas/gezuhao/xinghanbo/openvla-oft/skill_packs/_quarantine_goal_task_residue_20260915`

## Suite Summary (libero_goal_task, debug seeds 51-65)

| task | language | status | effective writes this campaign | one-line reason |
| --- | --- | --- | ---: | --- |
| t1 | open the bottom drawer of the cabinet | blocker | - | executor lacks an `open` primitive for articulated drawers |
| t2 | Put the plate on the stove | blocker | - | plate pick/place kinematics not solvable with current assets |
| t3 | put the wine bottle in the bowl | passed (14/15) | 1 | wrong-object trigger + topdown bottle grasp + inner-floor grounding/geometry + drop budget |
| t4 | Open the top layer of the drawer and put the cream cheese inside | blocker | - | recovery lacks `place_in` primitive |
| t5 | Put the plate on the top of the drawer | blocker | - | same plate kinematics family as t2 |
| t6 | Push the cream cheese to the front of the stove | blocker | - | goal-surface correction still leaves `pos_err 0/64` + `robot_to_world` planning failures |
| t7 | put the wine bottle in the bowl | covered (14/15) | 0 | identical language/goal to t3; existing pack covers it |
| t8 | Turn off the stove | covered (13/15) | 0 | policy solves it itself; recovery lacks `Turnoff` schema (irrelevant while policy covers) |
| t9 | Put the wine bottle on the plate | passed (9/15) | 1 (this round) | t9-scoped wrong-object trigger + entry lift + bottle close guard; note the mrs80 config trap |
| t10 | Put the cream cheese on the rack | blocker | 0 (this round) | region-goal folds to rack body; rewrite restores region but rack-top planning and thin-box pick execution remain infeasible |

t1-t8 statuses and write counts come from the supervisor's campaign record; t9/t10 are this round's file-backed conclusions (see `docs/libero_goal_task09_cross_suite_mining_2026-09-16.md` and this document).

Inherited rule for future rounds (from task09): always run recovery-enabled lanes with `max_recovery_steps=200`; with the default `place_reserve_steps=80`, `max_recovery_steps=80` structurally starves every pick-place plan (pick budget clamps to 1 step) and masquerades as physics failure.