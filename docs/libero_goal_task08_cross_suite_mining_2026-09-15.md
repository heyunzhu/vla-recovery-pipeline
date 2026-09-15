# LIBERO Goal Task08 Cross-Suite Mining Report

Date: 2026-09-15

Task: `libero_goal_task` task08

BDDL file: `turn_on_the_stove.bddl`

Language: `Turn off the stove`

Goal: `(And (Turnoff flat_stove_1))`

Status: `covered`

Pack: `/mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914`

Remote run root: `/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task08_cross_suite_newtree_20260915`

Local archive: `E:\VLA_recovery_workspace\vla-recovery-pipeline\remote_outputs\libero_goal_task08_cross_suite_newtree_20260915`

## Outcome

Task08 is covered by the base policy, not by a recovery skill. The initial expectation was that `Turnoff` would be a recovery-domain blocker, and that remains true for forced recovery, but it does not block this task because the policy itself solves 13/15 validation episodes.

| lane | result | notes |
| --- | ---: | --- |
| baseline | 13/15 = 0.867 | seeds 51-65, `max_recovery_calls=0` |
| W0 | 12/15 = 0.800 | seeds 51-65, existing pack, no recovery calls |
| forced probe | 2/3 = 0.667 | seeds 51-53, `force_recovery_query=5` |
| W1 | not run | baseline and W0 both exceeded the 0.6 gate |

Decision: covered, zero writes. No mining lane was started, no artifact was written, and the pack was not modified.

## New-Tree Setup

The eval used the extracted repository:

```text
repo = /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706
runner = scripts/recovery/skill_pipeline/run_skill_eval.py
cuTAMP runner = scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh
```

The same run-local LIBERO-PRO config pattern as task07 was used. The global config still points at `LIBERO_src`, so this task wrote a private config under:

```text
/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task08_cross_suite_newtree_20260915/libero_config/config.yaml
```

No global config was modified. All formal runs recorded:

```text
task_language_source = bddl
engine_language_source = bddl
real_cutamp_grasp_dof = 6
skill_pack = /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/skill_packs/libero_goal_task_from_goal_swap_spatial_mining_base_20260914
```

The baseline launch also printed:

```text
runner_import /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/experiments/robot/libero/skill_pipeline/runner.py
cutamp_runner_import /mnt/nas/gezuhao/xinghanbo/vla-recovery-pipeline-smoke-f143706/experiments/robot/libero/skill_pipeline/runner.py
```

## Formal Runs

Baseline:

```text
exp_name = baseline_task08_seed51_65_skills_off
task_suite_name = libero_goal_task
task_ids = 8
episode_seed_start = 51
num_trials_per_task = 15
max_recovery_calls = 0
enable_skills = false
enable_mining_skills = false
real_cutamp_grasp_dof = 6
```

W0:

```text
exp_name = w0_task08_seed51_65_existing_pack
task_suite_name = libero_goal_task
task_ids = 8
episode_seed_start = 51
num_trials_per_task = 15
max_recovery_calls = 2
enable_mining_skills = true
real_cutamp_grasp_dof = 6
```

Baseline successes:

```text
51, 52, 53, 55, 56, 57, 58, 59, 60, 61, 63, 64, 65
```

Baseline failures:

```text
54, 62
```

W0 successes:

```text
51, 52, 53, 55, 56, 57, 58, 59, 60, 61, 64, 65
```

W0 failures:

```text
54, 62, 63
```

W0 had zero recovery calls in all 15 episodes.

## Paired Decomposition

The baseline and W0 runs are aligned by seed.

| category | seeds | count |
| --- | --- | ---: |
| `policy_only` | 51, 52, 53, 55, 56, 57, 58, 59, 60, 61, 64, 65 | 12 |
| `unnecessary_handoff` | none | 0 |
| `recovery_gain` | none | 0 |
| `regression` | 63 | 1 |
| `still_failing` | 54, 62 | 2 |

The seed63 regression is not skill-caused: W0 had `recovery_calls=0` and an empty recovery trace for every episode. It should be treated as rollout variance, the same way zero-fire paired regressions were interpreted in task06.

## W0 Firing Ledger

Actual firing was determined from `recovery_trace.jsonl`.

```text
actual_firing_skill_ids = {}
total_recovery_calls = 0
```

No existing skill became winner on task08. This matches the language collision matrix below.

## Policy Evidence

The policy can turn off the stove without recovery:

- Baseline succeeded in 13/15 episodes with `recovery_calls=0`.
- Successful baseline episodes terminated early in 44-57 environment steps.
- The two baseline failures, seeds 54 and 62, ran to the full 300-step limit.
- `query_trace.jsonl` consistently targeted `flat_stove_1_main`.
- In successful baseline episodes the minimum EE-to-stove distance was about 0.026-0.063 m.

The query trace does not expose a direct stove on/off scalar, but the LIBERO task checker accepted the goal in 13 episodes and ended those episodes early. That is the available logged evidence that the stove state changed.

## Static Recovery-Domain Evidence

`experiments/robot/libero/tiptop_repro/cutamp_domain.py` builds executor-supported schemas for:

```text
pick
place_on
retreat
open_gripper_for_recovery
retreat_to_safe_pose
move_to_pregrasp
```

It also constructs unsupported schemas for:

```text
place_in -> executor_gap: place_in primitive not implemented
open     -> executor_gap: open articulated primitive not implemented
close    -> executor_gap: close articulated primitive not implemented
```

Relevant lines:

```text
47  name="pick"
70  supported_by_executor=(pred == "place_on")
71  executor_gap: place_in primitive not implemented
77  name="open"
82  supported_by_executor=False
83  executor_gap: open articulated primitive not implemented
88  name="close"
93  supported_by_executor=False
94  executor_gap: close articulated primitive not implemented
109 name="open_gripper_for_recovery"
123 name="retreat_to_safe_pose"
135 name="move_to_pregrasp"
```

A code/pack search over `experiments`, `scripts`, and `skill_packs` found no executable `turnoff`, `turn_off`, or `turn off` implementation. The only current repository hits are report text, not runtime code.

Interpretation: recovery does not have a real `Turnoff` action schema. This is a recovery-stack capability gap, but not a task-level blocker because policy already covers the task.

## Forced-Recovery Probe

I used `force_recovery_query=5` instead of q20 because successful task08 episodes typically end by q9-q12; q20 would not be reached for seeds 51-53 and therefore would not probe recovery.

Probe:

```text
exp_name = probe_force_q5_seed51_53_existing_pack
seeds = 51, 52, 53
force_recovery_query = 5
max_recovery_calls = 1
result = 2/3
```

All three forced episodes entered recovery once. The rule layer produced:

```text
operation = manipulate
target_name = flat_stove_1_main
goal_name = null
bddl_target = flat_stove_1_main
bddl_goal = null
bddl_goal_atoms = []
semantics_target = flat_stove_1_main
semantics_goal = flat_stove_1_burner
required_final_atoms = on(flat_stove_1_main, flat_stove_1_burner)
```

The plan layer then failed in all three episodes:

```text
label = real_cutamp_no_feasible_goal
error = No satisfying particles found after optimizing all 1 plan(s)
num_satisfying = 0
```

The generated cuTAMP problem confirms the proxy failure mode:

```text
goal_atoms = on(flat_stove_1_main, flat_stove_1_burner), handempty()
required_final_atoms = on(flat_stove_1_main, flat_stove_1_burner), handempty()
movables_len = 0
schema_names = close, move_to_pregrasp, open, open_gripper_for_recovery, pick, place_in, place_on, retreat, retreat_to_safe_pose
```

Thus forced recovery does not execute a turnoff primitive. It falls back to a pick/place-style proxy goal involving a non-movable stove object, then fails to find satisfying particles. The two successful forced episodes are therefore not evidence that cuTAMP supports turnoff; they are consistent with the policy continuing to finish the task after the failed recovery attempt.

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

Task08 has no language hit in the current pack.

## Admission Roots

No new artifact was written, so no admission run was required. If a write had been attempted, explicit roots would have been:

Current roots:

```text
/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task08_cross_suite_newtree_20260915/baseline_task08_seed51_65_skills_off
/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task08_cross_suite_newtree_20260915/w0_task08_seed51_65_existing_pack
/mnt/nas/gezuhao/xinghanbo/logs/libero_goal_task08_cross_suite_newtree_20260915/probe_force_q5_seed51_53_existing_pack
```

Non-current roots:

```text
/mnt/nas/gezuhao/xinghanbo/logs/liberopro_6cell_baseline_seed51_55_n5_20260914/corpus
```

For task08 admission, the corpus exclusion would be `libero_goal_task/task08` seeds 51-55, leaving 295 non-current corpus episodes.

## Artifacts

The local archive contains 33 videos across baseline, W0, and forced-probe lanes. No pack file, profile, trigger, or capability registry was changed.

## Conclusion

Task08 should be marked covered with zero writes. The policy solves the task at 13/15, W0 remains above threshold at 12/15, and no existing skill fires. The recovery stack still lacks a native `Turnoff` representation/executor path, as shown by the forced probe, but mining a trigger would not help this already-covered task.
