# LIBERO-Pro object axes: grasp round (2026-09-19)

Follows `libero_object_axis_trigger_round_2026-09-19.md`. That round closed the trigger gap
(50/50 episodes firing, 32/50 on `libero_object_swap`); this round adds the grasp work for the
objects whose grasp plan was infeasible, and checks transfer to the other object axis.

## Diagnosis (trace + cuTAMP debug, no GPU)

- **cream cheese** (`object_swap` t02): planning was feasible in 8/12 solves (21-27 satisfying
  particles) but all five failed episodes ended on `Pick(cream_cheese_1_main, grasp1, q1)` with
  `optimized_motion_tracking_stalled`; the generic sampler is too wide and too shallow.
- **butter / chocolate pudding**: 20/20 solves produced **zero satisfying particles** with the
  generic 36-candidate top-down set at 0.085 m gripper width, while the object short sides are
  0.03954 m / 0.04632 m and both sit nearly flush with the table.
- **milk / orange juice** (`goal_atoms_not_yet_satisfied`) actually masked "the grasp never lifted
  the object"; one milk episode additionally failed a Place hover trajectory, i.e. not a basket
  geometry problem.

## Candidate

`skills/fail_only/recovery_hint/grasp/grasp_object_basket_flat_box_topdown_deep.md` - one shared
recovery hint scoped by language (`pick the (cream cheese|butter|chocolate pudding) and place it in
the basket`), target name and `bddl_goal_surface_matches: basket`, selecting the existing
geometry-parameterised profile `cream_cheese_flat_box_topdown_deep_v1`. The profile derives depth,
orientation, offsets and gripper width from the runtime target AABB, so the legacy name does not
make it cream-cheese-specific.

Offline replay scan over both object axes (600 episodes): **180/180** target failure episodes
matched, **0/28** success episodes matched, 30/30 per object per suite, no spill-over to the other
seven objects.

## Trial (GPU): object_swap t02/t07/t09 x 5 episodes, seeds 51-55

Run roots: `logs/object_swap_graspcand_20260919/object_swap_w1_graspcand_t020709_5ep` and
`.../object_swap_w1_graspcand_t09_resume_3ep` (the 3 remaining episodes were re-run with
`--episode_index_start 2` after a platform preemption).

| task | object | result | previous round | lift evidence |
| --- | --- | ---: | ---: | --- |
| t02 | cream cheese | **5/5** | 0/5 | `object_followed=True`, `object_lift_m` 0.0226-0.0232 |
| t07 | butter | **4/5** | 0/5 | successes 0.0214-0.0216; the single failure had `object_followed=False`, 0.0033 |
| t09 | chocolate pudding | **5/5** | 0/5 | 0.0218-0.0221; one episode needed 2 recoveries |
| | **total** | **14/15** | 0/15 | |

Execution-layer indicators from `cutamp_debug`:

- `config.grasp_sampler_profile = cream_cheese_flat_box_topdown_deep_v1` (the candidate was applied)
- `diagnostics.grasp_counts.<object> = 24` candidates per object
- gripper widths derived from the runtime AABB: chocolate pudding `0.05211` (predicted 0.0521),
  ketchup `0.04136`, salad dressing `0.03995`, bbq sauce `0.03275`, orange juice `0.05906`,
  alphabet soup `0.07077`, basket `0.075`
- cream cheese: 14 of 15 solves had satisfying particles (16-20)

## Transfer check: libero_object_task, 10 tasks x 5 episodes, seeds 51-55

Run root: `logs/object_task_trend_20260919/object_task_w0_triggers_graspcand_5ep`
(same pack, triggers + this candidate; baseline for those seeds was 5/50).

| task | object | result | baseline | recoveries | trigger that fired |
| --- | --- | ---: | ---: | ---: | --- |
| t01 | cream cheese | **0/5** | 0/5 | **0** | **none - no trigger matched** |
| t02 | alphabet soup | 5/5 | 5/5 | 0 | none (policy alone) |
| t03 | tomato sauce | 2/5 | 0/5 | 3 | `tomato_persistent` |
| t04 | ketchup | 5/5 | 0/5 | 5 | `group_a` |
| t05 | milk | 3/5 | 0/5 | 9 | `group_a` |
| t06 | bbq sauce | 5/5 | 0/5 | 5 | `bbq_orange_precontact` |
| t07 | orange juice | 3/5 | 0/5 | 5 | `bbq_orange_precontact` |
| t08 | butter | 2/5 | 0/5 | 6 | `group_a` |
| t09 | salad dressing | 5/5 | 0/5 | 5 | `salad_dressing_precontact` |
| t10 | chocolate pudding | 5/5 | 0/5 | 5 | `group_a` |
| | **total** | **35/50 = 0.70** | 5/50 | | |

Open items from the transfer run:

1. **cream cheese on `libero_object_task` never enters recovery** (0 recovery calls, no trigger
   matched), although the same object is 5/5 on `object_swap`. This is a trigger-coverage gap, not a
   grasp problem: the grasp candidate never gets a chance to run. The per-predicate diagnosis of
   `cream_cheese_precontact` against that axis is still open.
2. Butter (2/5), milk (3/5), orange juice (3/5) and tomato (2/5) fire but do not fully convert;
   their failures share the `goal_atoms_not_yet_satisfied` signature, which needs the same
   "trigger timing / grasp lift / place" split that was done for the swap axis.

## Immutability record for the 14/15 state

The pack state that produced the trial is reproducible from this commit:
`skills/_index.yaml` md5 `cc1eef1c1d83a48f6212427b1a494544` (30 entries) with the candidate at
`skills/fail_only/recovery_hint/grasp/grasp_object_basket_flat_box_topdown_deep.md`
(md5 `8f10236d263157efbcdba53856d7bafa`). The isolated trial copy lived at
`logs/object_swap_graspcand_20260919/pack` and was unchanged after 14:25 (before the trial);
verifying it against the md5s below detects any later edit.

```
af3d57fa9fefa8a8fbaa2df33c6cfda7  README.md
7956e77d06404b5292a5a58cf3762747  capabilities.yaml
aa3f12677b113f6f66dcd88a75f8c179  code/geometry_profiles.py
be1e38a2a46d3534ed16057a1b0d7365  code/grasp_profiles.py
5be70e4cbe994bc93d909d8887eee9f2  code/grounding_profiles.py
5b9e21b84584076b07c48da2c4b762bf  diagnostics/registry.yaml
0a6d37def0d86fd0dbb669df85713608  pack.yaml
1fbd880a72f0f866e467ac3c71eed15f  profiles/geometry.yaml
d935f38794b3231fd70c60ed4abb1144  profiles/grounding.yaml
d9d98da47ecadc1250bfcd395d5c5275  profiles/place.yaml
16367677f274cf25eaa598ffc3c1acc4  profiles/repair.yaml
a9d532c5cc8041f3b5937f575ae86850  skills/README.md
cc1eef1c1d83a48f6212427b1a494544  skills/_index.yaml
87c2257130a7c70577c3c09da09835a5  skills/fail_only/recovery_hint/geometry/cabinet_top_surface_geometry_explicit.md
3fcaf77cdd8a7c0d1f59944f5cb0bc43  skills/fail_only/recovery_hint/geometry/cream_cheese_bowl_support_geometry.md
4a85e494ed148f4db5e0b6f80475f598  skills/fail_only/recovery_hint/geometry/geometry_wine_bottle_bowl_inner_floor.md
e3a6bb6e505a4316e8412bc452744727  skills/fail_only/recovery_hint/grasp/grasp_bowl_plate_hollow_rim_topdown.md
60d625f2e31d8bd9f411d4bfe9c62f7c  skills/fail_only/recovery_hint/grasp/grasp_cream_cheese_bowl_flat_box_topdown_deep.md
8f10236d263157efbcdba53856d7bafa  skills/fail_only/recovery_hint/grasp/grasp_object_basket_flat_box_topdown_deep.md
4acd161f21bbc57abc6ded91ce8b3124  skills/fail_only/recovery_hint/grasp/grasp_wine_bottle_plate_topdown_close_guard.md
3dbf1056a293bfbf6de6c58757dd265b  skills/fail_only/recovery_hint/grasp/grasp_wine_bottle_topdown_close_guard.md
d34f56192229064c6feaff285031d19c  skills/fail_only/recovery_hint/grounding/cream_cheese_bowl_support_grounding.md
6c1f31f8dbf38e3e7587aa0dd1fcc946  skills/fail_only/recovery_hint/grounding/ground_wine_bottle_bowl_inner_floor.md
e337112ea212494f25b71827d44aaf95  skills/fail_only/recovery_hint/place/bowl_plate_hover_drop_budget.md
d69cdaf87f13da2b7043207549798d85  skills/fail_only/recovery_hint/place/bowl_plate_next_to_plate_hover_drop_budget.md
b1206ab5c201939123bb4312f32ce914  skills/fail_only/recovery_hint/place/cream_cheese_bowl_hover_drop_budget.md
3450a5eb37a5eaa3ee395876867862b0  skills/fail_only/recovery_hint/place/place_wine_bottle_bowl_drop_budget.md
e7a02c14370efcf1e6c5227549fe566f  skills/fail_only/trigger/black_bowl_cabinet_top_to_plate_wrong_object_handoff.md
284f675dab8da1af28231fb8b3f482b5  skills/fail_only/trigger/black_bowl_next_to_plate_wrong_object_handoff.md
8a6e93997ad4db111149dba3b3ce7d88  skills/fail_only/trigger/black_bowl_not_between_wrong_object_handoff.md
db061de514071a59f319b557a863a096  skills/fail_only/trigger/black_bowl_wooden_cabinet_top_to_plate_early_wrong_object_handoff.md
915826e238e05d3b69433e1028e31acf  skills/fail_only/trigger/bowl_cabinet_target_holding_handoff.md
a0b0eae9cdae300d1985ff7d820c8b60  skills/fail_only/trigger/bowl_cookie_box_wrong_bowl_handoff.md
ae915698bd779b207eb8603136006ec1  skills/fail_only/trigger/bowl_plate_pick_lost_or_wrong_intent.md
08cdc3d52a2dc8c60805542a93f566f0  skills/fail_only/trigger/cream_cheese_bowl_wrong_object_intent.md
8eb9918e6efafa1704938d4dab541ba1  skills/fail_only/trigger/object_basket_bbq_orange_precontact_wrong_intent.md
a009f7e653f27b19b55a4d24e62c9fbe  skills/fail_only/trigger/object_basket_cream_cheese_precontact_wrong_intent.md
d29fa2309a554a671dd0081efdaea3a4  skills/fail_only/trigger/object_basket_persistent_wrong_intent_group_a.md
3eecb6a11a96433352dc0b87da8eb8e5  skills/fail_only/trigger/object_basket_salad_dressing_precontact_wrong_intent.md
a782816d05fab725565cb3151aabfe4f  skills/fail_only/trigger/object_basket_tomato_persistent_wrong_intent.md
41769917298324974409e3227eeb078e  skills/fail_only/trigger/plate_stove_open_wrong_intent_pregrasp_handoff.md
6c9498adce4a73f3b2178ceda6de1898  skills/fail_only/trigger/wine_bottle_bowl_wrong_object_handoff.md
0a14c76afb9c13e0f1a46f7154007552  skills/fail_only/trigger/wine_bottle_plate_wrong_object_handoff.md
68b329da9893e34099c7d8ad5cb9c940  skills/pair/recovery_hint/grasp/.gitkeep
```

Local evidence copies: `remote_outputs/object_grasp_scan_20260919/` (diagnosis + candidate + scan
five-piece set), `remote_outputs/object_swap_trend_20260919/` (trigger-round trial),
`remote_outputs/object_task_trend_20260919/` (transfer run).
