"""Visual-only object snapshots and conservative identity tracking.

Segmentation is supplied by an external RGB backend. This module lifts its
masks through simulator depth and camera calibration, without accepting an env,
simulator scene, BDDL goal, contact table or object model.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .rgbd_observation import RGBDObservation, unproject_world


MASK_SOURCES = frozenset({"text_guided_segmentation", "rgbd_height_component"})


@dataclass(frozen=True)
class VisualDetection:
    mask: np.ndarray
    category: str | None
    raw_score: float | None
    source: str

    def __post_init__(self) -> None:
        if self.source not in MASK_SOURCES:
            raise ValueError("visual detection source is not allowed")
        if self.source == "rgbd_height_component" and self.category is not None:
            raise ValueError("height components cannot supply semantic categories")
        if self.category is not None and not self.category.strip():
            raise ValueError("category cannot be blank")
        if self.raw_score is not None and not np.isfinite(self.raw_score):
            raise ValueError("raw detector score must be finite")
        if np.asarray(self.mask).dtype != np.bool_ or not np.asarray(self.mask).any():
            raise ValueError("detection mask must be a nonempty bool array")


@dataclass(frozen=True)
class VisualObject:
    id: str
    category: str | None
    validity: str
    identity_status: str
    last_seen_step: int
    visible_centroid_world_m: tuple[float, float, float] | None
    visible_bounds_world_m: tuple[tuple[float, float, float], tuple[float, float, float]] | None
    pixel_bbox_xyxy: tuple[int, int, int, int] | None
    depth_valid_fraction: float | None
    raw_detection_score: float | None
    mask_source: str | None


@dataclass(frozen=True)
class VisualSceneSnapshot:
    snapshot_id: str
    episode_id: str
    env_step: int
    timestamp_s: float
    camera_id: str
    source: str
    objects: tuple[VisualObject, ...]
    perception_backend_id: str | None = None


class RGBDSceneTracker:
    def __init__(
        self,
        *,
        min_valid_pixels: int = 20,
        min_depth_fraction: float = 0.5,
        max_match_distance_m: float = 0.12,
        ambiguity_margin_m: float = 0.025,
        max_missing_steps: int = 20,
    ) -> None:
        if min_valid_pixels < 1 or not 0 < min_depth_fraction <= 1:
            raise ValueError("invalid depth evidence threshold")
        if max_match_distance_m <= 0 or ambiguity_margin_m < 0 or max_missing_steps < 0:
            raise ValueError("invalid tracking threshold")
        self.min_valid_pixels = min_valid_pixels
        self.min_depth_fraction = min_depth_fraction
        self.max_match_distance_m = max_match_distance_m
        self.ambiguity_margin_m = ambiguity_margin_m
        self.max_missing_steps = max_missing_steps
        self.reset()

    def reset(self) -> None:
        self._episode_id: str | None = None
        self._last_step = -1
        self._next_id = 1
        self._tracks: dict[str, VisualObject] = {}

    def _new_id(self) -> str:
        result = f"obj_{self._next_id:03d}"
        self._next_id += 1
        return result

    def update(self, observation: RGBDObservation, detections: list[VisualDetection]) -> VisualSceneSnapshot:
        if self._episode_id is not None and observation.episode_id != self._episode_id:
            raise ValueError("reset the tracker before a new episode")
        if observation.env_step <= self._last_step:
            raise ValueError("visual snapshots must advance in environment steps")
        height, width = observation.depth_m.shape
        for index, detection in enumerate(detections):
            mask = np.asarray(detection.mask)
            if mask.shape != (height, width):
                raise ValueError("segmentation mask does not align with RGB-D observation")
            for earlier in detections[:index]:
                old_mask = np.asarray(earlier.mask)
                overlap = int(np.count_nonzero(mask & old_mask))
                if overlap / min(int(mask.sum()), int(old_mask.sum())) > 0.1:
                    raise ValueError("segmentation masks overlap; resolve instance ambiguity before scene update")
        world = np.full((height, width, 3), np.nan, dtype=np.float64)
        world[observation.depth_valid] = unproject_world(observation)
        visible: list[VisualObject] = []
        for index, detection in enumerate(detections, start=1):
            mask = np.asarray(detection.mask)
            ys, xs = np.nonzero(mask)
            good = mask & observation.depth_valid
            points = world[good]
            enough_depth = (
                len(points) >= self.min_valid_pixels and len(points) / len(xs) >= self.min_depth_fraction
            )
            centroid = tuple(float(value) for value in np.mean(points, axis=0)) if enough_depth else None
            bounds = (
                (
                    tuple(float(value) for value in np.min(points, axis=0)),
                    tuple(float(value) for value in np.max(points, axis=0)),
                )
                if enough_depth
                else None
            )
            visible.append(
                VisualObject(
                    id=f"candidate_{observation.env_step}_{index:03d}",
                    category=detection.category,
                    validity="observed" if enough_depth else "depth_insufficient",
                    identity_status="unbound",
                    last_seen_step=observation.env_step,
                    visible_centroid_world_m=centroid,
                    visible_bounds_world_m=bounds,
                    pixel_bbox_xyxy=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                    depth_valid_fraction=len(points) / len(xs),
                    raw_detection_score=detection.raw_score,
                    mask_source=detection.source,
                )
            )

        # Compute candidate pairings without mutating tracks. A binding is
        # accepted only when both the new detection and old track have a unique
        # nearest neighbor with a sufficient distance margin.
        distances: dict[tuple[int, str], float] = {}
        for index, item in enumerate(visible):
            if item.category is None or item.visible_centroid_world_m is None:
                continue
            for track_id, old in self._tracks.items():
                if old.category != item.category or old.visible_centroid_world_m is None:
                    continue
                if observation.env_step - old.last_seen_step > self.max_missing_steps:
                    continue
                distance = float(
                    np.linalg.norm(
                        np.asarray(item.visible_centroid_world_m) - np.asarray(old.visible_centroid_world_m)
                    )
                )
                if distance <= self.max_match_distance_m:
                    distances[index, track_id] = distance

        choices: dict[int, str] = {}
        ambiguous: set[int] = set()
        for index, item in enumerate(visible):
            if item.category is None or item.visible_centroid_world_m is None:
                continue
            options = sorted((distance, track_id) for (j, track_id), distance in distances.items() if j == index)
            if len(options) > 1 and options[1][0] - options[0][0] < self.ambiguity_margin_m:
                ambiguous.add(index)
            elif options:
                choices[index] = options[0][1]
        for track_id in set(choices.values()):
            claimants = sorted((distance, index) for (index, key), distance in distances.items() if key == track_id)
            if len(claimants) > 1 and claimants[1][0] - claimants[0][0] < self.ambiguity_margin_m:
                ambiguous.update(index for _, index in claimants)
            else:
                for index, chosen in list(choices.items()):
                    if chosen == track_id and index != claimants[0][1]:
                        ambiguous.add(index)

        output = []
        refreshed: dict[str, VisualObject] = {}
        for index, item in enumerate(visible):
            values = dict(item.__dict__)
            if item.category is None or item.visible_centroid_world_m is None:
                pass
            elif index in ambiguous:
                values["identity_status"] = "ambiguous"
            elif index in choices:
                values["id"] = choices[index]
                values["identity_status"] = "tracked"
            else:
                values["id"] = self._new_id()
                values["identity_status"] = "new"
            result = VisualObject(**values)
            output.append(result)
            if result.id.startswith("obj_"):
                refreshed[result.id] = result

        for track_id, old in self._tracks.items():
            if track_id in refreshed or observation.env_step - old.last_seen_step > self.max_missing_steps:
                continue
            values = dict(old.__dict__)
            values.update(validity="not_observed", identity_status="history_only", pixel_bbox_xyxy=None)
            output.append(VisualObject(**values))
            refreshed[track_id] = old
        self._tracks = refreshed
        self._episode_id = observation.episode_id
        self._last_step = observation.env_step
        return VisualSceneSnapshot(
            snapshot_id=f"{observation.episode_id}:step{observation.env_step}:{observation.camera_id}",
            episode_id=observation.episode_id,
            env_step=observation.env_step,
            timestamp_s=observation.timestamp_s,
            camera_id=observation.camera_id,
            source="rgbd",
            objects=tuple(output),
        )
