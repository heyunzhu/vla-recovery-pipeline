# Repository layout

This repository keeps reusable runtime code separate from learned or authored
benchmark assets.

| Path | Owner | Contains | Must not contain |
| --- | --- | --- | --- |
| `experiments/robot/libero/skill_pipeline/` | core runtime | traces, matcher, admission, mining, validation, harness | task-specific rules |
| `experiments/robot/libero/tiptop_repro/` | planning runtime | scene model, generic primitives, cuTAMP bridge, executor | benchmark-specific profile branches |
| `scripts/recovery/skill_pipeline/` | operations | CLI, remote launch, probes, reports, agent orchestration | reusable domain logic |
| `skill_packs/<pack>/` | benchmark asset | skills, profiles, capabilities, pack-local adapters | modifications outside the pack |
| `benchmarks/` | benchmark asset | task specs, manifests, train/validation splits | rollout outputs |
| `docs/` | documentation | current specifications and selected retrospectives | bulk logs and copied workspaces |

## External assets

The following are runtime inputs and must remain outside Git:

- Pi0/OpenPI checkpoints;
- LIBERO and LIBERO-Pro repositories and assets;
- the Python 3.11 eval environment;
- the Python 3.10 cuTAMP/cuRobo environment;
- rollout traces, videos, planner debug files, and mining work directories.

## Skill-pack states

The pack directory is the physical isolation boundary. `pack.yaml` describes how
to load it; `capabilities.yaml` declares what it may use; `profiles/` and `code/`
implement benchmark-specific behavior; `skills/_index.yaml` decides what is
online. `skill_packs/catalog.yaml` records repository-level maturity and lineage.

Runs with skills enabled must pass `--skill_pack` or `--skill_index` explicitly.
This is deliberately stricter than the original workspace's root `skills/`
fallback.

## Historical source

The original OpenVLA files, archived recovery launchers, large remote outputs,
and ad-hoc temporary tools remain in the source workspace tagged
`pre-core-extraction-20260915`. They are not dependencies of this repository.
