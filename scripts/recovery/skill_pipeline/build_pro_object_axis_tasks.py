#!/usr/bin/env python3
"""One-axis variants of a LIBERO-Pro object-swap task.

Source suite is libero_object_swap, which the libero_pro umbrella loads.
The new suite name does not start with libero_, so it is not added to that
umbrella. It ends with _task so auto language source reads (:language).
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault("LIBERO_CONFIG_PATH", "/mnt/nas/gezuhao/xinghanbo/libero_config_pro")

import torch
from libero.libero.envs import OffScreenRenderEnv

ROOT = Path("/mnt/nas/gezuhao/xinghanbo/LIBERO-PRO/libero/libero")
BDDL_ROOT = ROOT / "bddl_files"
INIT_ROOT = ROOT / "init_files"
SUITE = "pro_object_axis_20261003_task"
BENCHMARK_INIT = ROOT / "benchmark" / "__init__.py"
TASK_MAP = ROOT / "benchmark" / "libero_suite_task_map.py"
SOURCE = BDDL_ROOT / "libero_object_swap" / "pick_up_the_cream_cheese_and_place_it_in_the_basket.bddl"
SOURCE_INIT = INIT_ROOT / "libero_object_swap" / "pick_up_the_cream_cheese_and_place_it_in_the_basket.pruned_init"
N_INIT = 8
SETTLE_STEPS = 15
HEIGHT = 256
WIDTH = 256


def replace_section(text: str, name: str, body: str) -> str:
    marker = f"(:{name}"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"missing {marker}")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[:start] + f"(:{name}{body})" + text[index + 1 :]
    raise ValueError(f"unbalanced {marker}")


def replace_balanced(text: str, keyword: str, replacement: str) -> str:
    marker = f"(:{keyword}"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"missing {marker}")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                return text[:start] + replacement + text[index + 1 :]
    raise ValueError(f"unbalanced {marker}")


def rewrite_region(text: str, region_name: str, ranges: tuple[float, float, float, float] | None, yaw: float | None) -> str:
    marker = f"({region_name}"
    start = text.find(marker)
    if start < 0:
        raise ValueError(region_name)
    depth = 0
    for index in range(start, len(text)):
        if text[index] == "(":
            depth += 1
        elif text[index] == ")":
            depth -= 1
            if depth == 0:
                form = text[start : index + 1]
                break
    else:
        raise ValueError(f"unbalanced {region_name}")
    updated = form
    if ranges is not None:
        block = "(:ranges (\n              (" + " ".join(f"{value:.4f}" for value in ranges) + ")\n            )\n          )"
        updated = replace_balanced(updated, "ranges", block)
    if yaw is not None:
        block = f"(:yaw_rotation (\n              ({yaw:.6f} {yaw:.6f})\n            )\n          )"
        if "(:yaw_rotation" in updated:
            updated = replace_balanced(updated, "yaw_rotation", block)
        else:
            close = updated.rfind(")")
            updated = updated[:close] + "\n          " + block + "\n      " + updated[close:]
    if updated.count("(") != updated.count(")"):
        raise ValueError(f"region unbalanced: {region_name}")
    return text[:start] + updated + text[index + 1 :]


def specs() -> list[dict]:
    return [
        {
            "name": "pick_the_alphabet_soup_and_place_it_in_the_basket",
            "edit": "goal",
            "language": "Pick the alphabet soup and place it in the basket",
            "obj_of_interest": "\n    alphabet_soup_1\n    basket_1\n  ",
            "goal": "\n    (And (In alphabet_soup_1 basket_1_contain_region))\n  ",
            "track_body": "alphabet_soup",
        },
        {
            "name": "pick_the_cream_cheese_and_place_it_in_the_basket_shift",
            "edit": "placement",
            "region": "other_object_region_0",
            "ranges": (-0.2450, -0.2650, -0.1950, -0.2150),
            "track_body": "cream_cheese",
        },
        {
            "name": "pick_the_cream_cheese_and_place_it_in_the_basket_yaw",
            "edit": "geometry",
            "region": "other_object_region_0",
            "yaw": 1.570796,
            "track_body": "cream_cheese",
        },
    ]


def build_text(source: str, spec: dict) -> str:
    if spec["edit"] == "goal":
        text = replace_section(source, "language", " " + spec["language"])
        text = replace_section(text, "obj_of_interest", spec["obj_of_interest"])
        text = replace_section(text, "goal", spec["goal"])
    elif spec["edit"] == "placement":
        text = rewrite_region(source, spec["region"], spec["ranges"], None)
    else:
        text = rewrite_region(source, spec["region"], None, spec["yaw"])
    if text.count("(") != text.count(")"):
        raise ValueError(spec["name"])
    return text


def make_env(bddl: Path) -> OffScreenRenderEnv:
    return OffScreenRenderEnv(bddl_file_name=str(bddl), camera_heights=HEIGHT, camera_widths=WIDTH)


def settle(env: OffScreenRenderEnv):
    action = np.zeros(env.env.action_dim, dtype=np.float32)
    obs = None
    for _ in range(SETTLE_STEPS):
        obs = env.step(action)[0]
    return obs


def sample_states(env: OffScreenRenderEnv, count: int) -> np.ndarray:
    kept = []
    for seed in range(count * 4):
        if len(kept) >= count:
            break
        env.seed(seed)
        env.reset()
        settle(env)
        if env.check_success():
            continue
        kept.append(np.asarray(env.get_sim_state(), dtype=np.float64))
    if len(kept) < count:
        raise RuntimeError(f"only kept {len(kept)} init states")
    return np.stack(kept)


def filter_copied_states(env: OffScreenRenderEnv, states: np.ndarray) -> np.ndarray:
    env.reset()
    kept = []
    for state in states:
        env.set_init_state(state)
        if env.check_success():
            continue
        kept.append(np.asarray(state, dtype=np.float64))
    if len(kept) < 10:
        raise RuntimeError(f"goal filter kept {len(kept)}")
    return np.stack(kept)


def body_xy(env: OffScreenRenderEnv, needle: str) -> np.ndarray:
    model = env.sim.model
    for index in range(int(model.nbody)):
        if needle in model.body(index).name:
            return np.array(env.sim.data.body_xpos[index][:2], dtype=np.float64)
    raise KeyError(needle)


def frame_from_state(env: OffScreenRenderEnv, state: np.ndarray) -> np.ndarray:
    env.reset()
    obs = env.set_init_state(state)
    return np.flipud(obs["agentview_image"])


def register(task_names: list[str]) -> None:
    init_text = BENCHMARK_INIT.read_text(encoding="utf-8")
    if f'"{SUITE}"' not in init_text:
        anchor = '"random_axis_20261003_task",\n]'
        if anchor not in init_text:
            raise RuntimeError("suite list anchor missing")
        init_text = init_text.replace(anchor, f'"random_axis_20261003_task",\n    "{SUITE}",\n]', 1)
    if "class PRO_OBJECT_AXIS_20261003_TASK" not in init_text:
        init_text += (
            "\n\n@register_benchmark\n"
            "class PRO_OBJECT_AXIS_20261003_TASK(Benchmark):\n"
            "    def __init__(self, task_order_index=0):\n"
            "        super().__init__(task_order_index=task_order_index)\n"
            f'        self.name = "{SUITE}"\n'
            "        self._make_benchmark()\n"
        )
    BENCHMARK_INIT.write_text(init_text, encoding="utf-8")
    map_text = TASK_MAP.read_text(encoding="utf-8")
    rendered = ",\n        ".join(f'"{name}"' for name in task_names)
    block = f'    "{SUITE}": [\n        {rendered},\n    ],\n'
    key = f'"{SUITE}"'
    if key in map_text:
        start = map_text.find(key)
        end = map_text.find("],", start)
        map_text = map_text[:start] + block[4:] + map_text[end + 3 :]
    else:
        close = map_text.rstrip()
        if not close.endswith("}"):
            raise RuntimeError("task map brace missing")
        map_text = close[:-1] + block + "}\n"
    TASK_MAP.write_text(map_text, encoding="utf-8")


def main() -> None:
    import imageio.v2 as imageio

    source = SOURCE.read_text(encoding="utf-8")
    source_states = np.asarray(torch.load(SOURCE_INIT, weights_only=False))
    bddl_dir = BDDL_ROOT / SUITE
    init_dir = INIT_ROOT / SUITE
    video_dir = Path("/mnt/nas/gezuhao/xinghanbo") / SUITE / "videos"
    if bddl_dir.exists():
        shutil.rmtree(bddl_dir)
    if init_dir.exists():
        shutil.rmtree(init_dir)
    bddl_dir.mkdir(parents=True)
    init_dir.mkdir(parents=True)
    video_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for spec in specs():
        print("build", spec["name"], flush=True)
        text = build_text(source, spec)
        bddl_path = bddl_dir / f"{spec['name']}.bddl"
        bddl_path.write_text(text, encoding="utf-8")
        env = make_env(bddl_path)
        try:
            states = filter_copied_states(env, source_states) if spec["edit"] == "goal" else sample_states(env, N_INIT)
            torch.save(states, init_dir / f"{spec['name']}.pruned_init")
            source_env = make_env(SOURCE)
            try:
                before = frame_from_state(source_env, source_states[0])
                before_xy = body_xy(source_env, spec["track_body"])
            finally:
                source_env.close()
            after = frame_from_state(env, states[0])
            after_xy = body_xy(env, spec["track_body"])
        finally:
            env.close()
        pair = np.concatenate([before, after], axis=1)
        imageio.imwrite(video_dir / f"{spec['name']}_pair.png", pair)
        delta = (after_xy - before_xy).round(4).tolist()
        row = {
            "name": spec["name"],
            "edit": spec["edit"],
            "source_suite": "libero_object_swap",
            "source_bddl": str(SOURCE),
            "bddl": str(bddl_path),
            "n_init": int(states.shape[0]),
            "tracked_body_xy_delta_m": delta,
        }
        rows.append(row)
        print("delta_m", spec["track_body"], delta, "n_init", states.shape[0], flush=True)
    register([row["name"] for row in rows])
    manifest = Path("/mnt/nas/gezuhao/xinghanbo") / SUITE / "manifest.json"
    manifest.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("suite", SUITE)


if __name__ == "__main__":
    main()
