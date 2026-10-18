#!/usr/bin/env bash
set -euo pipefail
RUN=/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008
OUT=$RUN/analysis_bundle
rm -rf "$OUT"
mkdir -p "$OUT/t0" "$OUT/t6"
cp "$RUN/snapshot/summary.json" "$OUT/t0/summary.json"
cp "$RUN/snapshot/agentview/rgbd.npz" "$OUT/t0/rgbd.npz"
cp "$RUN/snapshot/detector/grounding_boxes.json" "$OUT/t0/joint_boxes.json"
cp "$RUN/snapshot/detector_per_category/grounding_boxes.json" "$OUT/t6_placeholder_unused.json" || true
cp "$RUN/snapshot/detector_per_category/grounding_boxes.json" "$OUT/t0/per_boxes.json"
cp "$RUN/snapshot/detector_per_category/detections.json" "$OUT/t0/detections.json"
cp "$RUN/snapshot/detector_per_category/detections.npz" "$OUT/t0/detections.npz"
cp "$RUN/snapshot/detector_per_category/scene_refusal.json" "$OUT/t0/scene_refusal.json"
cp "$RUN/snapshot_t6/summary.json" "$OUT/t6/summary.json"
cp "$RUN/snapshot_t6/agentview/rgbd.npz" "$OUT/t6/rgbd.npz"
cp "$RUN/snapshot_t6/detector/grounding_boxes.json" "$OUT/t6/per_boxes.json"
cp "$RUN/snapshot_t6/detector/detections.json" "$OUT/t6/detections.json"
cp "$RUN/snapshot_t6/detector/detections.npz" "$OUT/t6/detections.npz"
cp "$RUN/snapshot_t6/detector/scene_refusal.json" "$OUT/t6/scene_refusal.json"
rm -f "$OUT/t6_placeholder_unused.json"
tar -C "$RUN" -czf "$RUN/analysis_bundle.tgz" analysis_bundle
ls -lh "$RUN/analysis_bundle.tgz"
