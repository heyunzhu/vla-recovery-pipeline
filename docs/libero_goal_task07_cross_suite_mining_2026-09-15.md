# LIBERO Goal Task07 Cross-Suite Mining Report

Date: 2026-09-15

Task: `libero_goal_task` task07

Language: `put the wine bottle in the bowl`

Goal: `On(wine_bottle_1, akita_black_bowl_1)`

Status: `covered`

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914`

Local archive: `E:\VLA_recovery_workspace\vla-recovery-pipeline\remote_outputs\libero_goal_task07_cross_suite_newtree_20260915`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task07_cross_suite_newtree_20260915`

## Outcome

Task07 is covered by the existing task03 wine-bottle-to-bowl skill family. No new mining lane was started, no artifact was written, and the pack was not modified.

| lane | result | notes |
| --- | ---: | --- |
| smoke | 0/1 | seed 51, skills off, new-tree import check |
| baseline | 0/15 = 0.000 | seeds 51-65, `max_recovery_calls=0` |
| W0 | 14/15 = 0.933 | seeds 51-65, existing pack |
| W1 | not run | W0 already exceeded the 0.6 gate |

Decision: because W0 reached 14/15, task07 is covered by the current pack. This is expected because task03 and task07 have identical language and BDDL goal.

Pack writes: 0

Pack modified: false

## New-Tree Smoke

The eval was run from the extracted repository, not the archived `openvla-oft` tree.

Repository:

```text
local repo  = E:\VLA_recovery_workspace\vla-recovery-pipeline
remote repo = /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706
```

Import checks:

```text
direct_runner_import  /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/experiments/robot/libero/skill_pipeline/runner.py
overlay_runner_import /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/experiments/robot/libero/skill_pipeline/runner.py
```

The run used the new tree runner:

```text
scripts/recovery/skill_pipeline/run_skill_eval.py
scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
```

The first preflight showed that the global LIBERO config still points at `LIBERO_src`, whose benchmark registry does not contain `libero_goal_task`. I created a run-local config under the task07 log root that points `benchmark_root`, `bddl_files`, `init_states`, and `assets` at `LIBERO-PRO`; no global config or environment file was modified. With that run-local config, the smoke episode completed and recorded:

```text
task_language_source = bddl
engine_language_source = bddl
real_cutamp_grasp_dof = 6
skill_pack = /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914
```

## Formal Runs

Baseline:

```text
exp_name = baseline_task07_seed51_65_skills_off
task_suite_name = libero_goal_task
task_ids = 7
episode_seed_start = 51
num_trials_per_task = 15
max_recovery_calls = 0
enable_skills = false
enable_mining_skills = false
real_cutamp_grasp_dof = 6
real_cutamp_runner_python = /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
```

W0:

```text
exp_name = w0_task07_seed51_65_existing_pack
task_suite_name = libero_goal_task
task_ids = 7
episode_seed_start = 51
num_trials_per_task = 15
max_recovery_calls = 2
enable_mining_skills = true
real_cutamp_grasp_dof = 6
real_cutamp_runner_python = /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
```

## Paired Decomposition

The baseline and W0 runs are aligned by seed.

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | none | 0 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, 62, 63, 64, 65 | 14 |
| `regression` | none | 0 |
| `still_failing` | 57 | 1 |

Interpretation: the base policy solved none of the 15 validation episodes. The existing pack rescued 14 episodes and did not regress any baseline success episode.

## W0 Firing Ledger

Actual W0 firing was determined from `recovery_trace.jsonl`.

| skill_id | episodes | first query indices |
| --- | --- | --- |
| `wine_bottle_bowl_wrong_object_handoff` | seeds 51, 52, 53, 54, 55, 56, 58, 59, 60, 61, 62, 63, 64, 65 | 7, 6, 6, 6, 7, 6, 4, 7, 7, 7, 6, 5, 6, 8 |

No other skill became the W0 winner. Seed57 had no recovery call and remained failing.

The selected recovery path used the task03 family of hints, including the `wine_bottle_bowl_inner_floor_v1` grounding/geometry profile. This is the intended cross-task coverage: task03 and task07 are semantically identical in this suite.

## Language Collision Matrix

Matrix computed with the runtime rule `re.search(pattern, language, re.I)` after YAML frontmatter folding.

Goal-task languages:

```text
t1  open the bottom drawer of the cabinet
t2  Put the plate on the stove
t3  put the wine bottle in the bowl
t4  Open the top layer of the drawer and put the cream cheese inside
t5  Put the plate on the top of the drawer
t6  Push the cream cheese to the front of the stove
t7  put the wine bottle in the bowl
t8  Turn off the stove
t9  Put the wine bottle on the plate
t10 Put the cream cheese on the rack
```

| trigger | t1 | t2 | t3 | t4 | t5 | t6 | t7 | t8 | t9 | t10 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `black_bowl_not_between_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_next_to_plate_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_cabinet_top_to_plate_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff` | . | . | . | . | . | . | . | . | . | . |
| `bowl_cabinet_target_holding_handoff` | . | . | . | . | . | . | . | . | . | . |
| `bowl_plate_pick_lost_or_wrong_intent` | . | . | . | . | . | . | . | . | . | . |
| `cream_cheese_bowl_wrong_object_intent` | . | . | . | . | . | . | . | . | . | . |
| `plate_stove_open_wrong_intent_pregrasp_handoff` | . | X | . | . | . | . | . | . | . | . |
| `wine_bottle_bowl_wrong_object_handoff` | . | . | X | . | . | . | X | . | . | . |

The task07 hit on `wine_bottle_bowl_wrong_object_handoff` is unavoidable and desired because t3 and t7 have the same language and the same goal. The `plate_stove_open_wrong_intent_pregrasp_handoff` language hit remains isolated to t2.

## Admission Roots

No new artifact was written, so no new admission run was required. The explicit roots for a hypothetical new write in this task would have been:

Current roots:

```text
/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task07_cross_suite_newtree_20260915/baseline_task07_seed51_65_skills_off
/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task07_cross_suite_newtree_20260915/w0_task07_seed51_65_existing_pack
```

Non-current roots:

```text
/mnt/nas/gezuhao/xinghanbo/logs/liberopro_6cell_baseline_seed51_55_n5_20260914/corpus
```

For task07 admission, the corpus exclusion would be `libero_goal_task/task07` seeds 51-55, leaving 295 non-current corpus episodes. Since W0 already passed and there were no writes, this remained a control definition rather than an executed admission scan.

## Conclusion

Task07 should be marked covered with zero writes. The result is not a new capability discovery; it is successful reuse of the task03 wine-bottle-to-bowl repair and hint family on the structurally identical task07.
