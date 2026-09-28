"""Depth-only connected foreground candidates above a visible support plane.

The output is deliberately unnamed and frame-local. It does not infer an
object's hidden shape, MuJoCo body center, grasp pose or stable tracking ID.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .rgbd_observation import RGBDObservation, unproject_world
from .visual_geometry import HorizontalPlaneCandidate, WorkspaceBounds


@dataclass(frozen=True)
class ForegroundProposal:
    proposal_id: str
    mask: np.ndarray
    pixel_bbox_xyxy: tuple[int, int, int, int]
    visible_centroid_world_m: tuple[float, float, float]
    visible_bounds_world_m: tuple[tuple[float, float, float], tuple[float, float, float]]
    pixel_count: int
    height_above_plane_m: tuple[float, float]
    touches_image_boundary: bool
    source: str = "rgbd_height_component"


def _point_image(observation: RGBDObservation) -> np.ndarray:
    height, width = observation.depth_m.shape
    image = np.full((height, width, 3), np.nan, dtype=np.float64)
    image[observation.depth_valid] = unproject_world(observation)
    return image


def foreground_proposals(
    observation: RGBDObservation,
    plane: HorizontalPlaneCandidate,
    workspace: WorkspaceBounds,
    *,
    min_height_m: float = 0.012,
    max_height_m: float = 0.35,
    min_pixels: int = 30,
) -> list[ForegroundProposal]:
    """Find 8-connected visible height components in a declared workspace."""

    if min_height_m <= 0 or max_height_m <= min_height_m or min_pixels < 1:
        raise ValueError("invalid foreground height or pixel thresholds")
    xyz = _point_image(observation)
    height, width = observation.depth_m.shape
    plane_height = plane.height_at(xyz[:, :, 0], xyz[:, :, 1])
    above = xyz[:, :, 2] - plane_height
    foreground = (
        observation.depth_valid
        & (xyz[:, :, 0] >= workspace.x[0])
        & (xyz[:, :, 0] <= workspace.x[1])
        & (xyz[:, :, 1] >= workspace.y[0])
        & (xyz[:, :, 1] <= workspace.y[1])
        & (xyz[:, :, 2] >= workspace.z[0])
        & (xyz[:, :, 2] <= workspace.z[1])
        & (above >= min_height_m)
        & (above <= max_height_m)
    )
    visited = np.zeros_like(foreground)
    components: list[tuple[np.ndarray, np.ndarray]] = []
    for y0, x0 in np.argwhere(foreground):
        if visited[y0, x0]:
            continue
        visited[y0, x0] = True
        stack = [(int(y0), int(x0))]
        pixels: list[tuple[int, int]] = []
        while stack:
            y, x = stack.pop()
            pixels.append((y, x))
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dy == 0 and dx == 0:
                        continue
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < height and 0 <= nx < width and foreground[ny, nx] and not visited[ny, nx]:
                        visited[ny, nx] = True
                        stack.append((ny, nx))
        if len(pixels) >= min_pixels:
            coordinates = np.asarray(pixels, dtype=np.int32)
            components.append((coordinates[:, 0], coordinates[:, 1]))

    components.sort(key=lambda item: (float(np.mean(item[1])), float(np.mean(item[0]))))
    proposals = []
    for index, (ys, xs) in enumerate(components, start=1):
        mask = np.zeros((height, width), dtype=bool)
        mask[ys, xs] = True
        points = xyz[ys, xs]
        low, high = np.min(points, axis=0), np.max(points, axis=0)
        proposals.append(
            ForegroundProposal(
                proposal_id=f"proposal_{index:03d}",
                mask=mask,
                pixel_bbox_xyxy=(int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1),
                visible_centroid_world_m=tuple(float(value) for value in np.mean(points, axis=0)),
                visible_bounds_world_m=(
                    tuple(float(value) for value in low),
                    tuple(float(value) for value in high),
                ),
                pixel_count=len(xs),
                height_above_plane_m=(float(np.min(above[ys, xs])), float(np.max(above[ys, xs]))),
                touches_image_boundary=bool(
                    np.any((xs == 0) | (ys == 0) | (xs == width - 1) | (ys == height - 1))
                ),
            )
        )
    return proposals
