# Native MMDetection recovery: 10 tasks × 5 episodes

## Scope and reproducibility

Requested 2026-10-18: replace the detector's HF export path with the trained native MMDetection checkpoint and evaluate complete episodes on Inspire. Only `xinghanbo-eval` in `可上网GPU资源` is used. Runtime installation is private to this experiment; no global environments are modified.

- Branch: `feature/rgbd-recovery`; local baseline HEAD: `62e4bc8410bcf1211c8b86dc8263746f2c8a6795` plus the uncommitted experiment changes. This HEAD alone does **not** reproduce this experiment. The server freezes the runnable source under `code/`, with changed-file SHA256 values in `protocol_manifest.json`.
- Run: `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_native_mmdet_20261018`.
- Model: native `best_coco_bbox_mAP_epoch_10.pth`, SHA256 `735b0e3ca9f8a44ad97dbaec97d15c61f18248e01d3e1479d0556d50f3388edd`.
- Source checkpoint: `/mnt/nas/gezuhao/xinghanbo/models/rgbd_dino_full_20261018/training/best_coco_bbox_mAP_epoch_10.pth`.
- The model receives RGB and configured text prompts. Depth remains an input to downstream observed geometry. No HF weight conversion is used for DINO. SAM2 retains its previous runtime.
- Native inference uses MMDetection `init_detector` and `inference_detector`, the training test pipeline with annotation loading removed, `custom_entities=True`, and score threshold 0.25. All qualifying instances are retained; integer labels map to the requested caption entities.

## Protocol

Full VLA + existing C4 skill triggering + RGB-D recovery, with the prior controller, recovery limits, prompts, camera resolution, and collision/geometry settings. Simulator success remains authoritative. This retains the previous benchmark's skill-triggering protocol; it is not a claim of a completely ground-truth-free controller.

50 episodes, two concurrent simulations, one shared policy server, serialized native planning. Each task uses episode indices 0–4, physical seeds 1–5, policy seeds 90–94. Exact BDDL paths, hashes, language, and initial-state indices are frozen in `requested_cases.json`. LIBERO-PRO substitution tasks can retain original BDDL filenames while their registered language/object changes; use the manifest rather than infer the actual object from the filename.

| Suite | Task (1-based) | Goal |
| --- | --- | --- |
| libero_spatial_swap | 1 | bowl between plate and ramekin → plate |
| libero_object_task | 2 | ketchup → basket |
| libero_object_task | 4 | salad dressing → basket |
| libero_object_task | 7 | butter → basket |
| libero_object_task | 8 | chocolate pudding → basket |
| libero_object_task | 9 | tomato sauce → basket |
| libero_object_task | 10 | bbq sauce → basket |
| libero_object_swap | 1 | alphabet soup → basket |
| libero_object_swap | 8 | orange juice → basket |
| libero_goal_task | 8 | cream cheese → rack |

Compare these same 50 cases against `/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_core60_20261017`; report episode success separately from success during recovery and from detection/binding failures. This selected set exercises multiple new categories and a previous recovery reference; it does not estimate an unbiased Core-60 success rate.

One additional correctness fix is included: unsuccessful cuboid fitting is recorded and rejected before canonical-box conversion. This avoids a missing-rotation `KeyError`; geometry acceptance thresholds remain unchanged. Failure-stage labels can therefore differ from the earlier run even when the fit is still rejected.

## Startup, validation, and artifacts

`setup_and_run.py` waits for transferred assets, verifies their SHA256 values and the checkpoint, creates a private native environment, rewrites only the local BERT path in the detector config, and runs two checks:

1. Two fixed RGB frames must match native training-server results: same ordered labels, maximum box coordinate difference ≤1 pixel and score difference ≤0.01. Saved as `native_parity.json`.
2. The actual native-DINO-to-SAM2 adapter must produce detections and masks. Saved as `adapter_preflight.json`.

Only after both pass does it start the scheduler. Two first episodes exercise different suites before releasing the rest; invalid episodes, resource exhaustion, or infrastructure failures pause this startup gate. Neither a detector check nor valid episode creation is counted as task success.

Scheduler command, after the setup checks and shared policy startup:

```bash
ROOT=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo
RUN="$ROOT/logs/rgbd_native_mmdet_20261018"
"$ROOT/envs/rlinf-openpi/bin/python" -u \
  "$RUN/code/scripts/recovery/skill_pipeline/run_rgbd_core60_batch.py" \
  --root "$ROOT" --run "$RUN" --workers 2 --expected-cases 50 --timeout 2400
```

The scheduler requires the prepared `runtime_overlay`, `sensor_support`, configs, and shared policy service. Use the saved `policy_launch.json` and each case's `command.json` for complete arguments and environment. Do not publish `policy_endpoint.json` credentials.

Progress/artifacts: `setup_status.json`, `setup_error.txt` if present, `batch_launch.json`, `progress.json`, `batch_results.json`, `startup_blocked.json` if present, `finished.json`, `cases/<case_id>/driver.log`, episode JSON, recovery outputs, and saved videos. A waiting setup process is not evidence that episodes have started: require `batch_launch.json` and running case status.

Local verification: 14 unit tests passed across native worker label mapping/routing, GroundedSAM2 backend behavior, and batch resume/error classification. End-to-end success numbers must come from the actual run artifacts.

## Platform interruption

At 2026-10-18 12:12:22 CST, platform events explicitly reported that this low-priority pod was preempted and evicted by another scheduled task. The notebook returned to `PENDING`; no evaluation episodes had started. The policy service had warmed before preemption, but that process cannot be assumed to survive reassignment.

A local background workload dispatcher (`analysis_outputs/rgbd_native_mmdet_20261018/dispatch.py`) waits for this same notebook to become `RUNNING`, resumes asset transfer, and invokes `resume_remote.py`. That script checks scoped process identities before restarting this run's policy service and setup. It never changes priority or touches another notebook. The dispatcher exits on batch completion, a startup/setup error needing inspection, or a 48-hour deadline. Its status is saved locally as `dispatch_state.json`, with transfer output in `dispatch_upload.log`. It requires the local computer/WSL to remain running until staging completes; actual episode execution is detached on the server after launch. These queued intentions are not results.

## Git snapshot

The 2026-10-18 progress submission includes the actual native checkpoint through Git LFS at `models/rgbd_dino_full_20261018/best_coco_bbox_mAP_epoch_10.pth`, its training config/taxonomy/checksum manifest, and the frozen protocol plus native reference inputs/outputs under `benchmarks/rgbd_native_mmdet_20261018`. The earlier baseline HEAD above identifies the parent of this accumulated work, not the resulting progress commit. The commit containing this section identifies the saved source snapshot.

At this submission check, `xinghanbo-eval` was `RUNNING` on `qb-prod-4090-gpu098`; transfers had resumed. There was still no verified launch or result for the 50-episode batch. Use live run artifacts for subsequent status.

Snapshot verification: all 886 tests in `experiments/robot/libero/skill_pipeline/tests` passed locally. The staged snapshot also passed Python syntax checks (90 files), JSON parsing (117 files), and credential-pattern checks. These local checks do not replace native GPU adapter or episode validation on Inspire.
