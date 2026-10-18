# Frozen 50-episode native MMDetection recovery protocol

This directory preserves the selected ten tasks, five initial states each, native reference images/results, runtime asset checksums, and the server-side setup/resume scripts for the 2026-10-18 experiment. It accompanies the [full protocol](../../docs/results/rgbd_native_mmdet_20261018.md) and [LFS checkpoint](../../models/rgbd_dino_full_20261018/README.md).

- `requested_cases.json`: all 50 exact case IDs, BDDL hashes, initial-state indices and policy seeds.
- `tasks.json`: ten task descriptions.
- `golden/`: two fixed raw RGB inputs, their text queries, native training-server outputs and provenance. These are interface parity checks, not recovery evaluation results.
- `setup_and_run.py`: scoped environment setup, model/assets SHA256 validation, native reference parity, DINO-to-SAM2 adapter check, and batch startup.
- `resume_remote.py`: checks this run's process identity and restores its policy/setup after platform preemption; completed episodes remain reusable by the scheduler.
- `reference_native.py`: original training-server command logic used to generate the fixed native outputs.
- `package_status.json`: exact transferred environment/assets archive hashes. Runtime binaries are external and not checked into Git.
- `status_at_commit.json`: a timestamped operational snapshot, **not live status**. Episode evaluation had not started at this snapshot.

The setup scripts retain the authorized server paths and frozen historical runtime dependencies; they are reproducibility records for that deployment, not a standalone installer for a new machine. Check the protocol's prerequisites before execution. Local account/session files, transfer credentials, cached environments, and temporary downloads remain outside Git.
