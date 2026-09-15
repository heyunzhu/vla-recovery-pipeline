# generated_v1 Skill Pack

This pack mirrors the generated-task scratch skill library.

Use it for generated benchmark mining runs that should not load historical
LIBERO-90 online skills:

```bash
python scripts/recovery/skill_pipeline/run_mining_lane.py \
  --skill_pack generated_v1 \
  ...
```

Pass the pack explicitly on every generated-benchmark run. This repository does
not provide the old root-level `skills_scratch` compatibility path.
