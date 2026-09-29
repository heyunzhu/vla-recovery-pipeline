"""Diagnostic point coverage for visually inspected RGB reference instances."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence

import numpy as np

from .perception_artifact import rgb_sha256
from .rgbd_observation import RGBDObservation
from .rgbd_scene import VisualDetection, mask_conflicts


def load_visual_reference(frame: RGBDObservation, path: str | Path) -> dict[str, Any]:
    reference = json.loads(Path(path).read_text(encoding="utf-8"))
    if (
        reference.get("reference_schema_version") != 1
        or reference.get("episode_id") != frame.episode_id
        or reference.get("env_step") != frame.env_step
        or reference.get("camera_id") != frame.camera_id
        or reference.get("image_shape_hw") != list(frame.rgb.shape[:2])
        or reference.get("rgb_sha256") != rgb_sha256(frame)
    ):
        raise ValueError("visual reference does not match this RGB frame")
    instances = reference.get("instances")
    if not isinstance(instances, list) or not instances:
        raise ValueError("visual reference requires visible instances")
    negative_points = reference.get("negative_points", [])
    if not isinstance(negative_points, list):
        raise ValueError("visual reference negative_points must be a list")
    for items, category_key in ((instances, "category"), (negative_points, "forbidden_category")):
        for item in items:
            if (not isinstance(item, dict) or not isinstance(item.get(category_key), str)
                    or not item[category_key].strip()):
                raise ValueError("invalid visual reference category")
            point = item.get("point_xy")
            if not isinstance(point, list) or len(point) != 2:
                raise ValueError("visual reference point must be [x, y]")
            x, y = point
            inside = (
                isinstance(x, int)
                and isinstance(y, int)
                and 0 <= x < frame.rgb.shape[1]
                and 0 <= y < frame.rgb.shape[0]
            )
            if not inside:
                raise ValueError("visual reference point is outside the image")
    return reference


def evaluate_reference_points(
    frame: RGBDObservation,
    detections: Sequence[VisualDetection],
    reference: dict[str, Any],
) -> dict[str, Any]:
    """Require one correct-category mask at each point and distinct instances."""

    if reference.get("rgb_sha256") != rgb_sha256(frame):
        raise ValueError("visual reference does not match this RGB frame")
    rows = []
    claimed: dict[int, list[str]] = {}
    raw_claimed: dict[int, list[str]] = {}
    for item in reference["instances"]:
        x, y = item["point_xy"]
        raw_masks = [index for index, detection in enumerate(detections) if np.asarray(detection.mask)[y, x]]
        for index in raw_masks:
            raw_claimed.setdefault(index, []).append(item["reference_id"])
        candidates = [
            index
            for index, detection in enumerate(detections)
            if detection.category == item["category"] and np.asarray(detection.mask)[y, x]
        ]
        if len(candidates) == 1:
            claimed.setdefault(candidates[0], []).append(item["reference_id"])
        rows.append(
            {
                "reference_id": item["reference_id"],
                "category": item["category"],
                "raw_mask_indices": raw_masks,
                "candidate_mask_indices": candidates,
                "status": "missing" if not candidates else "ambiguous" if len(candidates) > 1 else "candidate",
            }
        )
    for row in rows:
        if row["status"] == "candidate":
            index = row["candidate_mask_indices"][0]
            row["status"] = "merged" if len(claimed[index]) > 1 else "matched"
    counts = {
        status: sum(row["status"] == status for row in rows)
        for status in ("matched", "missing", "ambiguous", "merged")
    }
    conflicts = mask_conflicts(list(detections))
    negative_hits = []
    for item in reference.get("negative_points", []):
        x, y = item["point_xy"]
        indices = [index for index, detection in enumerate(detections)
                   if detection.category == item["forbidden_category"]
                   and np.asarray(detection.mask)[y, x]]
        if indices:
            negative_hits.append({"reference_id": item["reference_id"],
                                  "forbidden_category": item["forbidden_category"],
                                  "detection_indices": indices})
    return {
        "snapshot_id": f"{frame.episode_id}:step{frame.env_step}:{frame.camera_id}",
        "reference_count": len(rows),
        "detection_count": len(detections),
        "status_counts": counts,
        "shared_raw_mask_groups": [
            {"mask_index": index, "reference_ids": ids}
            for index, ids in sorted(raw_claimed.items())
            if len(ids) > 1
        ],
        "mask_conflicts": conflicts,
        "negative_point_count": len(reference.get("negative_points", [])),
        "negative_point_hits": negative_hits,
        "passed": counts["matched"] == len(rows) and not conflicts and not negative_hits,
        "instances": rows,
    }
