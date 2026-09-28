#!/usr/bin/env python3
"""Render an RGB-D snapshot preview and projected robot end-effector marker."""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path

import numpy as np


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", zlib.crc32(kind + payload))


def _write_rgb_png(path: Path, image: np.ndarray) -> None:
    height, width, channels = image.shape
    if channels != 3 or image.dtype != np.uint8:
        raise ValueError("PNG preview requires uint8 RGB image")
    rows = b"".join(b"\0" + image[row].tobytes() for row in range(height))
    header = b"\x89PNG\r\n\x1a\n"
    header += _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    path.write_bytes(header + _png_chunk(b"IDAT", zlib.compress(rows)) + _png_chunk(b"IEND", b""))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot", type=Path, help="Directory containing metadata.json and rgbd.npz")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

    from experiments.robot.libero.skill_pipeline.rgbd_observation import load_observation

    frame = load_observation(args.snapshot)
    image = frame.rgb.copy()
    depth = frame.depth_m
    finite = depth[frame.depth_valid]
    if not len(finite):
        raise ValueError("snapshot has no valid depth")
    near, far = np.percentile(finite, [2, 98])
    scale = np.clip((depth - near) / max(far - near, 1e-6), 0.0, 1.0)
    gray = np.where(frame.depth_valid, (255.0 * (1.0 - scale)), 0.0).astype(np.uint8)
    depth_rgb = np.repeat(gray[:, :, None], 3, axis=2)

    ee_world = np.asarray(frame.robot_state["robot0_eef_pos"], dtype=np.float64)
    ee_camera = np.linalg.inv(frame.T_world_camera) @ np.r_[ee_world, 1.0]
    if ee_camera[2] > 0:
        projected = frame.K @ ee_camera[:3]
        x, y = np.rint(projected[:2] / projected[2] - 0.5).astype(int)
        if 0 <= x < image.shape[1] and 0 <= y < image.shape[0]:
            for delta in range(-4, 5):
                if 0 <= x + delta < image.shape[1]:
                    image[y, x + delta] = [255, 0, 0]
                if 0 <= y + delta < image.shape[0]:
                    image[y + delta, x] = [255, 0, 0]
            print(f"projected_eef_pixel=({x},{y}) camera_z_m={ee_camera[2]:.4f}")
    preview = np.concatenate((image, depth_rgb), axis=1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_rgb_png(args.output, preview)
    print(f"preview={args.output}")


if __name__ == "__main__":
    main()
