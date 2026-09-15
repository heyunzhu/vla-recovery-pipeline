# pi0_libero_openpi Inspire Known-Good Eval Profile

This profile records the first Inspire run where the JAX `pi0_libero_openpi`
checkpoint, online skills, and real cuTAMP recovery were verified end to end.

## Remote Context

- Platform notebook: `xinghanbo-eval`
- Workspace: `可上网GPU资源`
- Account: `25012`
- Remote workspace root:
  `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo`
- Remote repo:
  `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/code/openvla-oft`
- Python:
  `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/bin/python`
- Model:
  `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/models/pi0_libero_openpi`

## Harness Spec

The reusable registered spec is:

```bash
python scripts/recovery/skill_pipeline/harness_run.py \
  --benchmark pi0_libero_openpi_inspire_known_good \
  --workspace_root /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo \
  --repo_root /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/code/openvla-oft \
  --python_bin /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/envs/rlinf-openpi/bin/python \
  --log_root /inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs \
  --start
```

Core settings:

- `config_name: pi0_libero`
- `model: pi0_libero_openpi`
- `skills: online`
- `skill_pack: libero90_legacy`
- `real_cutamp.enabled: true`
- `real_cutamp.grasp_dof: 6`
- `real_cutamp.serialize_trajectories: true`
- `real_cutamp.curobo_plan: true`
- `real_cutamp.prefer_executable_plan: true`
- `real_cutamp.require_executable_plan: true`
- `real_cutamp.table_proxy_profile: thin_clipped_lowered`
- `diagnostic_signals.statuses: [shadow, online]`
- `save_video: true`
- `export_annotated: true`

## Reference Result

Reference run:

`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/harness_tasks48_60_pi0_libero_jax_skills_inspire_20260905_r1`

Outcome:

- `65` episodes
- `44` successes
- success rate `0.677`
- `51` recovery calls
- `65` raw videos
- `65` annotated videos
- `global_exit_code=0`
- `postprocess_exit_code=0`

## Harness Smoke Canary

This small run is the first CI-style canary for the persistent harness itself.
It intentionally uses only two tasks so that admission and trace replay can be
checked quickly after code or skill changes.

Run:

`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/pi0_libero_openpi_inspire_known_good_fcf9a4d_20260905_083835`

Local lightweight artifact:

`remote_outputs/harness_smoke_task47_48_pi0_inspire_known_good_20260905`

Local offline trigger corpus:

`analysis_outputs/offline_trigger_corpus/pi0_libero_openpi_inspire_known_good_fcf9a4d_20260905_083835`

Outcome:

- `10` episodes
- `6` successes
- success rate `0.600`
- `8` recovery calls
- `10` raw videos
- `10` annotated videos
- `global_exit_code=0`
- `postprocess_exit_code=0`

Per-task result:

| task | success | success rate | recovery calls | repair winners |
|---|---:|---:|---:|---|
| `task47` | `2/5` | `0.400` | `3` | `vla_closed_near_non_target_pick`, `vla_wrong_object_progress_recovery` |
| `task48` | `4/5` | `0.800` | `5` | `vla_wrong_object_intent_conservative` |

Postprocess artifacts verified:

- `harness_summary.json`
- `harness_gates.json`
- `harness_report.md`
- `offline_skill_scan/offline_skill_scan.md`
- `analysis_outputs/offline_trigger_corpus/.../manifest.json`

## Generated Validation Generalization Probe

The generated benchmark is frozen at:

`benchmarks/libero90_generated_v1_envfiltered_304`

The reusable spec for a small validation probe is:

`generated_validation_generalization_pi0_known_good`

Selected validation rows:

| row | generated task id | template | language |
|---:|---|---|---|
| 1 | `libero_90_gen_t014_pick_place_on_surface_6d0267cf` | `pick_place_on_surface` | pick up the akita black bowl and place it on the plate |
| 3 | `libero_90_gen_t023_pick_place_on_surface_3333bd03` | `pick_place_on_surface` | pick up the akita black bowl and place it on the wine rack |
| 4 | `libero_90_gen_t030_pick_place_on_surface_e0cda06e` | `pick_place_on_surface` | pick up the ketchup and place it on the plate |
| 10 | `libero_90_gen_t050_put_inside_container_7989aa4b` | `put_inside_container` | pick up the cream cheese and place it in the basket |
| 12 | `libero_90_gen_t052_put_inside_container_ffa2efb8` | `put_inside_container` | pick up the orange juice and place it in the basket |
| 15 | `libero_90_gen_t061_put_inside_container_55584e10` | `put_inside_container` | pick up the new salad dressing and place it in the wooden tray |
| 18 | `libero_90_gen_t065_put_inside_container_240b4540` | `put_inside_container` | pick up the akita black bowl and place it in the wooden tray |
| 19 | `libero_90_gen_t066_pick_place_on_surface_9d69eb8c` | `pick_place_on_surface` | pick up the red coffee mug and place it on the plate |
| 22 | `libero_90_gen_t070_pick_place_on_surface_95e3b12f` | `pick_place_on_surface` | pick up the porcelain mug and place it on the plate |
| 25 | `libero_90_gen_t076_caddy_compartment_38e811a5` | `caddy_compartment` | pick up the white yellow mug and place it in the front compartment of the caddy |
| 29 | `libero_90_gen_t077_caddy_compartment_06dd6160` | `caddy_compartment` | pick up the black book and place it in the left compartment of the caddy |
| 35 | `libero_90_gen_t082_caddy_compartment_04e625ea` | `caddy_compartment` | pick up the black book and place it in the back compartment of the caddy |

Rows with synthetic `in microwave` goals are left out of this small probe for
now: the generated BDDL can load, but LIBERO's native success predicate raises
on some microwave-inside variants, so they are not good harness canaries yet.

Latest generated validation probe:

`/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/generated_validation_generalization_pi0_known_good_inspire_20260905_r2`

Outcome:

- `24` episodes
- `11` successes
- success rate `0.458`
- `21` recovery calls
- `24` raw videos
- `24` annotated videos
- `global_exit_code=0`
- `postprocess_exit_code=0`
