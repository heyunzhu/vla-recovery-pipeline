"""Replay frozen visual masks without loading a detector or simulator."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Sequence

import numpy as np

from .rgbd_observation import RGBDObservation
from .rgbd_scene import VisualDetection


PERCEPTION_ARTIFACT_VERSION = 1


def rgb_sha256(frame: RGBDObservation) -> str:
    return hashlib.sha256(np.ascontiguousarray(frame.rgb).tobytes()).hexdigest()


def save_detections(
    frame: RGBDObservation,
    detections: Sequence[VisualDetection],
    directory: str | Path,
    *,
    detector_id: str,
) -> None:
    if not detector_id.strip():
        raise ValueError("detector_id is required")
    height, width = frame.rgb.shape[:2]
    for item in detections:
        if np.asarray(item.mask).shape != (height, width):
            raise ValueError("detection mask does not align with RGB frame")
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    masks = (
        np.stack([np.asarray(item.mask, dtype=bool) for item in detections])
        if detections
        else np.empty((0, height, width), dtype=bool)
    )
    metadata = {
        "schema_version": PERCEPTION_ARTIFACT_VERSION,
        "episode_id": frame.episode_id,
        "env_step": frame.env_step,
        "camera_id": frame.camera_id,
        "image_shape_hw": [height, width],
        "rgb_sha256": rgb_sha256(frame),
        "detector_id": detector_id,
        "detections": [
            {"mask_index": i, "category": item.category, "raw_score": item.raw_score, "source": item.source}
            for i, item in enumerate(detections)
        ],
    }
    np.savez_compressed(target / "detections.npz", masks=masks)
    (target / "detections.json").write_text(
        json.dumps(metadata, ensure_ascii=False, allow_nan=False, indent=2) + "\n", encoding="utf-8"
    )


def load_detections(frame: RGBDObservation, directory: str | Path) -> tuple[str, list[VisualDetection]]:
    source = Path(directory)
    metadata = json.loads((source / "detections.json").read_text(encoding="utf-8"))
    if metadata.get("schema_version") != PERCEPTION_ARTIFACT_VERSION:
        raise ValueError("unsupported perception artifact schema")
    if (
        metadata.get("episode_id") != frame.episode_id
        or metadata.get("env_step") != frame.env_step
        or metadata.get("camera_id") != frame.camera_id
        or metadata.get("image_shape_hw") != list(frame.rgb.shape[:2])
        or metadata.get("rgb_sha256") != rgb_sha256(frame)
    ):
        raise ValueError("perception artifact does not match the RGB frame")
    detector_id = metadata.get("detector_id")
    if not isinstance(detector_id, str) or not detector_id.strip():
        raise ValueError("perception artifact has no detector_id")
    rows = metadata.get("detections")
    if not isinstance(rows, list):
        raise ValueError("perception artifact requires a detection list")
    with np.load(source / "detections.npz", allow_pickle=False) as arrays:
        masks = arrays["masks"]
    if masks.shape != (len(rows), *frame.rgb.shape[:2]) or masks.dtype != np.bool_:
        raise ValueError("perception artifact masks do not match metadata")
    detections = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict) or row.get("mask_index") != index:
            raise ValueError("perception artifact mask indices are inconsistent")
        detections.append(
            VisualDetection(
                mask=masks[index],
                category=row.get("category"),
                raw_score=row.get("raw_score"),
                source=row.get("source"),
            )
        )
    return detector_id, detections
