"""One visual scene snapshot shared by consumers of the same RGB-D frame.

The detector receives only the whitelisted observation. In particular this
provider never accepts a LIBERO environment, simulator handle, BDDL goal, or
oracle scene. A detector backend must be supplied explicitly.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Callable, Sequence

import numpy as np

from .rgbd_observation import RGBDObservation
from .rgbd_scene import RGBDSceneTracker, VisualDetection, VisualSceneSnapshot


DetectionBackend = Callable[[RGBDObservation], Sequence[VisualDetection]]


def _frame_digest(frame: RGBDObservation) -> bytes:
    """Detect changed content under a supposedly identical episode/step key."""

    digest = hashlib.sha256()
    metadata = (
        frame.episode_id,
        frame.env_step,
        frame.timestamp_s,
        frame.camera_id,
        frame.calibration_version,
        frame.robot_state,
    )
    digest.update(json.dumps(metadata, sort_keys=True, allow_nan=False).encode("utf-8"))
    for array in (frame.rgb, frame.depth_m, frame.depth_valid, frame.K, frame.T_world_camera):
        value = np.ascontiguousarray(array)
        digest.update(str(value.dtype).encode("ascii"))
        digest.update(str(value.shape).encode("ascii"))
        digest.update(value.tobytes())
    return digest.digest()


class RGBDSceneProvider:
    """Own detector, tracker, and current-step cache for one camera/episode."""

    def __init__(
        self,
        detector: DetectionBackend,
        *,
        detector_id: str,
        camera_id: str,
        tracker: RGBDSceneTracker | None = None,
    ) -> None:
        if not callable(detector) or not detector_id.strip() or not camera_id.strip():
            raise ValueError("detector, detector_id, and camera_id are required")
        self._detector = detector
        self.detector_id = detector_id
        self.camera_id = camera_id
        self._tracker = tracker if tracker is not None else RGBDSceneTracker()
        self.reset()

    def reset(self) -> None:
        self._tracker.reset()
        self._cached_key: tuple[str, int, str] | None = None
        self._cached_digest: bytes | None = None
        self._cached_scene: VisualSceneSnapshot | None = None

    def get_scene(self, frame: RGBDObservation) -> VisualSceneSnapshot:
        if frame.camera_id != self.camera_id:
            raise ValueError(f"expected RGB-D camera {self.camera_id!r}, got {frame.camera_id!r}")
        key = (frame.episode_id, frame.env_step, frame.camera_id)
        digest = _frame_digest(frame)
        if key == self._cached_key:
            if digest != self._cached_digest:
                raise ValueError("RGB-D content changed for an already cached episode/step")
            assert self._cached_scene is not None
            return self._cached_scene
        if self._cached_key is not None and frame.episode_id != self._cached_key[0]:
            raise ValueError("reset the scene provider before a new episode")
        if self._cached_key is not None and frame.env_step <= self._cached_key[1]:
            raise ValueError("RGB-D scene provider requires increasing environment steps")

        detections = list(self._detector(frame))
        if not all(isinstance(item, VisualDetection) for item in detections):
            raise TypeError("detector must return VisualDetection objects")
        scene = dataclasses.replace(
            self._tracker.update(frame, detections),
            perception_backend_id=self.detector_id,
        )
        self._cached_key = key
        self._cached_digest = digest
        self._cached_scene = scene
        return scene
