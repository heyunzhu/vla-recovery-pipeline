# VLA Recovery Pipeline

This repository contains the recovery-skill system extracted from the original
OpenVLA-OFT workspace. The online policy remains an external Pi0/OpenPI model.
This code records rollout evidence, matches recovery skills, invokes cuTAMP,
validates candidates, and maintains benchmark-specific skill packs.

## Architecture

```text
Online evaluation
Pi0/OpenPI -> runner -> hook/matcher -> skill pack -> cuTAMP -> executor -> Pi0

Offline mining
rollout traces -> agent diagnosis -> candidate skill/profile/adapter
               -> static admission -> offline trigger scan
               -> same-init validation -> pack index
```

The repository is intentionally split into four ownership boundaries:

- `experiments/robot/libero/skill_pipeline/`: reusable runtime, trace,
  admission, mining, validation, and harness logic.
- `experiments/robot/libero/tiptop_repro/`: scene construction, cuTAMP bridge,
  motion planning, and recovery execution.
- `scripts/recovery/skill_pipeline/`: command-line and remote orchestration.
- `skill_packs/`: benchmark-specific skills, profiles, and adapters.

Generated rollout data, model weights, LIBERO assets, and Python environments do
not belong in this repository.

## Local Checks

The static/unit test suite does not require a GPU:

```powershell
python -m unittest discover `
  -s experiments/robot/libero/skill_pipeline/tests `
  -p "test_*.py"
```

Check one skill pack before a remote run:

```powershell
python scripts/recovery/skill_pipeline/run_skill_quality_gate.py `
  --skill-pack libero90_legacy
```

## Runtime Contract

Skill-enabled runs must select their assets explicitly with `--skill_pack` (or
the lower-level `--skill_index`). There is no root-level default skill library.
This prevents a LIBERO-90 pack from leaking into a different benchmark.

The GPU runtime is external and currently uses two isolated environments:

- Python 3.11: OpenPI/JAX, LIBERO or LIBERO-Pro, MuJoCo, and the eval runner.
- Python 3.10: cuTAMP/cuRobo, launched through
  `scripts/recovery/skill_pipeline/cutamp_runner_py310_overlay.sh`.

See [the pipeline specification](docs/agentic_skill_recovery_pipeline.md),
[the mining loop](docs/skill_pipeline_mining_loop.md), and
[the repository layout](docs/repository_layout.md) before changing behavior.

## Skill Assets

`skill_packs/catalog.yaml` is the inventory of retained packs and their maturity.
Only paths listed under a pack's `skills/_index.yaml: online` are production
online skills. A historical rollout success does not by itself promote a
`fail_only` artifact.

## Provenance

This extraction was created from `openvla-oft` commit `1dd363d`. The source
workspace was tagged `pre-core-extraction-20260915` before extraction.
