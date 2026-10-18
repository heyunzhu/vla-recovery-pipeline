# Generated V1 Scratch Skill Library

This is the scratch skill library for mining on
`benchmarks/libero90_generated_v1_envfiltered_304`.

It intentionally starts empty so generated-task mining does not load the
historical LIBERO-90 online skills from `skills/`.

Use this root with:

```bash
--skills_dir skills_scratch/generated_v1
```

or pass its index directly to the low-level runner:

```bash
--skill_index skills_scratch/generated_v1/_index.yaml
```

The first generated-task screening split is:

```text
benchmarks/libero90_generated_v1_envfiltered_304/category_splits/by_behavior_v1
```

The harness benchmark specs for this scratch library are:

- `generated_phase1_train_scratch_baseline_pi0_known_good`
- `generated_phase1_train_scratch_online_pi0_known_good`
- `generated_phase1_test_scratch_online_pi0_known_good`
