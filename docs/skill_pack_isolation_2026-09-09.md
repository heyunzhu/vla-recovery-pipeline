# Skill Pack Isolation

This note began as the first isolation record and now documents the extracted
repository's explicit-pack contract.

## Goal

Keep benchmark-specific skill libraries physically separable. Skill-enabled
commands must select a pack explicitly; old root path defaults are not retained.

Before this change, most entrypoints selected skills through one of these
paths:

- `skills/_index.yaml`
- `skills_scratch/generated_v1/_index.yaml`
- a separate capability registry path
- the core diagnostic signal registry

That made it easy to accidentally evaluate one library while prompting,
ingesting, or scanning another. A skill pack now groups these runtime resources:

- skill markdown directory
- skill index
- capability registry
- diagnostic signal registry
- grasp / grounding / geometry / place profile registries
- pack-local profile adapters, when a profile needs benchmark-specific code

## Current Packs

`skill_packs/libero90_legacy`

- Mirrors the historical LIBERO-90 skill library.
- Its index points to pack-local `capabilities.yaml`.
- Its legacy grasp, grounding, and geometry specializations live under pack-local
  `code/` adapters, so profile-specific implementation details are selected
  only when this pack is loaded.
- Use for reproducing LIBERO-90 runs and legacy skill analysis.

`skill_packs/generated_v1`

- Mirrors the generated-task scratch skill library.
- Starts with no online skills and one fail-only draft trigger.
- Starts with profile registries but no benchmark-specific code adapters. If
  mining adds generated-task-specific grasp / grounding / geometry / place
  code, add the adapter under `skill_packs/generated_v1/code/` and expose it
  from `pack.yaml` or `skills/_index.yaml` in the same change.
- Use for generated benchmark mining without loading LIBERO-90 online skills.

Campaign-specific packs, such as `skill_packs/libero_goal_swap_task09_seed51_65_v1`,
follow the same contract. They should start from an empty or deliberately
minimal online index, then grow only through that mining run's admitted drafts.
Do not seed a new benchmark pack with `libero90_legacy` online skills unless the
experiment explicitly says it is testing legacy transfer.

The old `skills/` and `skills_scratch/generated_v1/` compatibility directories
remain only in the tagged source workspace. They are intentionally absent here.

## Entrypoints

These commands now accept `--skill_pack` and `--skill-pack`:

- `experiments.robot.libero.skill_pipeline.runner`
- `scripts/recovery/skill_pipeline/run_skill_eval.py`
- `scripts/recovery/skill_pipeline/run_skill_mine.py`
- `scripts/recovery/skill_pipeline/run_mining_lane.py`
- `scripts/recovery/skill_pipeline/run_skill_admission.py`
- `scripts/recovery/skill_pipeline/run_skill_quality_gate.py`
- `scripts/recovery/skill_pipeline/scan_skill_triggers.py`
- `scripts/recovery/skill_pipeline/check_grasp_skills.py`
- `scripts/recovery/skill_pipeline/run_code_admission.py`
- `scripts/recovery/skill_pipeline/run_codex_actor.py`
- `scripts/recovery/skill_pipeline/harness_run.py`

Harness YAML specs may also set `skill_pack`.

Explicit path arguments still override pack defaults. For example, a command
may pass both `--skill_pack libero90_legacy` and `--skill_index some/_index.yaml`;
in that case the explicit index wins.

## Profile Isolation

The runner loads profile registries through the resolved skill pack:

- grasp profiles plus `code/grasp_profiles.py`
- `profiles/grounding.yaml` plus `code/grounding_profiles.py`
- `profiles/geometry.yaml` plus `code/geometry_profiles.py`
- `profiles/place.yaml` plus `code/place_policies.py`

Core planner files keep only generic primitives such as top-down grasp sampling,
table-region grounding, preferred support/container binding, fixed table
rectangles, inner-floor proxies, and movable support surfaces. A pack adapter
maps benchmark-specific profile names onto those primitives. For example,
`libero90_legacy/code/grounding_profiles.py` maps
`desk_caddy_compartment_v1` to `container_region_surface`, and
`libero90_legacy/code/geometry_profiles.py` maps
`desk_caddy_compartment_inner_floor_v1` to `inner_floor`.

Engine-consumed names are centralized in
`experiments/robot/libero/tiptop_repro/engine_capabilities.py`:

- executor option keys;
- place candidate policies;
- place yaw policies;
- release modes;
- grounding planner primitives;
- geometry planner primitives;
- generic geometry descriptor shapes.

The pack capability registry is narrower: it says which of those engine
capabilities a given skill pack is allowed to use. A key can be supported by
the engine but still unavailable to a pack until that pack registers it.

This is still an incremental isolation step: shared primitives remain in the
runner/planner/executor, while LIBERO-90 profile catalogs and adapters live in
the LIBERO-90 pack.

At runtime, `SkillRuntime` merges the winning repair with matching
recovery-hint skills, expands named grounding / geometry / repair / place
profiles, audits the merged hints against the active capability registry, and
then attaches the grasp adapter path for the selected `grasp_profile`.

## Extension Boundary

For ordinary mining, benchmark-specific changes should stay in the active pack:

| change | pack-local files |
| --- | --- |
| new repair entry behavior | `profiles/repair.yaml` |
| new grasp sampling | `code/grasp_profiles.py` and the grasp profile registry |
| new grounding binding | `profiles/grounding.yaml` and `code/grounding_profiles.py` |
| new geometry measurement / crop | `profiles/geometry.yaml` and `code/geometry_profiles.py` |
| new place behavior selection | `profiles/place.yaml` and `code/place_policies.py` |
| new allowed capability | `capabilities.yaml` |

If a task cannot be expressed through the existing generic primitives, the
agent should write a blocker / engineering action. A shared engine change is
allowed only when it adds a benchmark-independent primitive or executor action,
with tests and a `code_patch_manifest.yaml`. It should not be smuggled in as a
task-specific skill patch.

## Examples

Run online recovery with the legacy pack:

```bash
python -m experiments.robot.libero.skill_pipeline.runner \
  --enable_skills \
  --skill_pack libero90_legacy \
  ...
```

Run mining on the generated scratch pack:

```bash
python scripts/recovery/skill_pipeline/run_mining_lane.py \
  --skill_pack generated_v1 \
  ...
```

Prepare a harness run with a pack override:

```bash
python scripts/recovery/skill_pipeline/harness_run.py \
  --benchmark libero90_smoke \
  --skill_pack libero90_legacy
```

## Validation

The first implementation was checked with:

```bash
python -m unittest \
  experiments.robot.libero.skill_pipeline.tests.test_skill_pack \
  experiments.robot.libero.skill_pipeline.tests.test_grasp_static \
  experiments.robot.libero.skill_pipeline.tests.test_harness \
  experiments.robot.libero.skill_pipeline.tests.test_capabilities \
  experiments.robot.libero.skill_pipeline.tests.test_schema

python scripts/recovery/skill_pipeline/check_grasp_skills.py --skill_pack generated_v1
python scripts/recovery/skill_pipeline/check_grasp_skills.py --skill_pack libero90_legacy
python scripts/recovery/skill_pipeline/run_skill_eval.py --help
```
