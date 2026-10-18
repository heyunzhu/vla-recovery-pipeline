# generated_v1 Skill Pack

This pack mirrors the generated-task scratch skill library.

Use it for generated benchmark mining runs that should not load historical
LIBERO-90 online skills:

```bash
python scripts/recovery/skill_pipeline/run_mining_lane.py \
  --skill_pack generated_v1 \
  ...
```

The old `skills_scratch/generated_v1/_index.yaml` entrypoint remains available
for compatibility.
