#!/usr/bin/env python3
"""Render short before/after clips for generated LIBERO-Pro task variants."""

from __future__ import annotations

import json
import os
from pathlib import Path

import imageio.v2 as imageio
import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault(
    "LIBERO_CONFIG_PATH",
    "/mnt/nas/gezuhao/xinghanbo/libero_config_pro",
)

from libero.libero.envs import OffScreenRenderEnv


PREVIEW = Path("/mnt/nas/gezuhao/xinghanbo/libero_pro_random_preview_20261003")
OUT = PREVIEW / "videos"
HEIGHT = 256
WIDTH = 256
SEED = 0
SETTLE_STEPS = 40
HOLD_FRAMES = 20


def load_rows() -> list[dict]:
    rows = []
    for line in (PREVIEW / "manifest.jsonl").read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def pick(rows: list[dict]) -> list[dict]:
    wanted = {
        "placement": "red_coffee_mug_init_region",
        "geometry": "alphabet_soup_init_region",
        "goal": "moka_pot_1",
    }
    chosen = []
    for kind, marker in wanted.items():
        for row in rows:
            if row["edit"] != kind:
                continue
            blob = json.dumps(row["detail"])
            if marker in blob:
                chosen.append(row)
                break
    return chosen


def grab(bddl: str, seed: int) -> list[np.ndarray]:
    env = OffScreenRenderEnv(
        bddl_file_name=bddl,
        camera_heights=HEIGHT,
        camera_widths=WIDTH,
    )
    env.seed(seed)
    obs = env.reset()
    frames = [np.flipud(obs["agentview_image"])]
    action = np.zeros(env.env.action_dim, dtype=np.float32)
    for _ in range(SETTLE_STEPS):
        obs = env.step(action)[0]
        frames.append(np.flipud(obs["agentview_image"]))
    env.close()
    return frames


def side_by_side(before: list[np.ndarray], after: list[np.ndarray]) -> list[np.ndarray]:
    count = min(len(before), len(after))
    clips = []
    for index in range(count):
        pair = np.concatenate([before[index], after[index]], axis=1)
        clips.append(pair)
    clips.extend([clips[-1]] * HOLD_FRAMES)
    return clips


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows = pick(load_rows())
    for row in rows:
        print("render", row["edit"], row["task_id"], flush=True)
        before = grab(row["source_bddl"], SEED)
        after = grab(row["bddl_path"], SEED)
        frames = side_by_side(before, after)
        stem = f"{row['edit']}_{row['task_id']}"
        video_path = OUT / f"{stem}.mp4"
        try:
            imageio.mimsave(video_path, frames, fps=10)
        except Exception as exc:
            video_path = OUT / f"{stem}.gif"
            imageio.mimsave(video_path, frames, fps=10)
            print("mp4 failed, wrote gif:", exc, flush=True)
        imageio.imwrite(OUT / f"{stem}_before.png", before[-1])
        imageio.imwrite(OUT / f"{stem}_after.png", after[-1])
        imageio.imwrite(OUT / f"{stem}_pair.png", frames[-1])
        print("wrote", video_path, flush=True)


if __name__ == "__main__":
    main()
