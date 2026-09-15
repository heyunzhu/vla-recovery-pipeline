# Core extraction manifest (2026-09-15)

## Source checkpoint

- Source workspace: `E:/VLA_recovery_workspace/openvla-oft`
- Source commit: `1dd363d`
- Recovery tag: `pre-core-extraction-20260915`
- Source branch pushed before extraction: `feature/agentic-skill-recovery`

The source workspace remains the historical archive. Its untracked design notes
were not staged or modified during extraction.

## Included

- `experiments/robot/libero/skill_pipeline/`: runtime, evidence, mining,
  admission, validation, and harness code.
- `experiments/robot/libero/tiptop_repro/`: generic planning and execution
  bridge used by the recovery runtime.
- `scripts/recovery/skill_pipeline/`: supported command-line entrypoints and
  operational tools.
- `skill_capabilities/`: capability schemas and registries.
- `skill_packs/`: the released LIBERO-90 pack plus retained validated,
  experimental, and mining packs listed in `skill_packs/catalog.yaml`.
- `benchmarks/`: generated benchmark definitions and splits.
- `docs/`: current specifications, authoring rules, and selected retrospectives.

## Excluded

- legacy OpenVLA training and inference code (`prismatic`, ALOHA, and old
  OpenVLA evaluation helpers);
- duplicated root-level `skills/` and `skills_scratch/` compatibility trees;
- archived and one-off launchers that are not imported by the supported flow;
- `remote_outputs`, rollout logs, videos, planner debug files, and daemon work;
- model checkpoints, LIBERO assets, Python environments, and external cuTAMP or
  OpenPI installations.

## Boundary changes

- Skill-enabled commands require an explicit `--skill_pack` or
  `--skill_index`; there is no implicit root skill library.
- Retained packs have unique internal names.
- The harness applies the same explicit-pack rule.
- Admission no longer defaults to the old `skills_scratch` tree.
- Runtime repository defaults refer to this repository, while the external
  model, simulator, and planner environments remain deployment inputs.

## Verification

- Python unit/static suite: `481` tests passed.
- Pack code checks: all `11` retained packs passed.
- Extracted source and documentation: approximately `6.3 MB` across `885`
  files before Git metadata, excluding ignored bytecode caches.
- No model, dataset, video, or file larger than 1 MiB is included.

The extraction has not yet been deployed as a new directory for a GPU rollout.
The source checkpoint had already passed the relevant remote smokes; the new
repository still needs one explicit-pack deployment smoke before the old
workspace can be treated as archive-only.
