#!/usr/bin/env python3
"""Build a few LIBERO-Pro tasks, one edit axis each, with sampled init states.

The suite name does not start with ``libero_``, so the libero_pro umbrella
loader will not pick it up. It ends with ``_task`` so the runner's auto
language source reads ``(:language)`` from the BDDL.
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import numpy as np

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
os.environ.setdefault(
    "LIBERO_CONFIG_PATH",
    "/mnt/nas/gezuhao/xinghanbo/libero_config_pro",
)

import torch
from libero.libero.envs import OffScreenRenderEnv

ROOT = Path("/mnt/nas/gezuhao/xinghanbo/LIBERO-PRO/libero/libero")
BDDL_ROOT = ROOT / "bddl_files"
INIT_ROOT = ROOT / "init_files"
SUITE = "random_axis_20261003_task"
BENCHMARK_INIT = ROOT / "benchmark" / "__init__.py"
TASK_MAP = ROOT / "benchmark" / "libero_suite_task_map.py"
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
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
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
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return text[:start] + replacement + text[index + 1 :]
    raise ValueError(f"unbalanced {marker}")


def rewrite_region(text: str, region_name: str, ranges: tuple[float, float, float, float] | None, yaw: float | None) -> str:
    marker = f"({region_name}"
    start = text.find(marker)
    if start < 0:
        raise ValueError(f"missing region {region_name}")
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                form = text[start : index + 1]
                break
    else:
        raise ValueError(f"unbalanced region {region_name}")
    updated = form
    if ranges is not None:
        block = (
            "(:ranges (\n              ("
            + " ".join(f"{value:.4f}" for value in ranges)
            + ")\n            )\n          )"
        )
        updated = replace_balanced(updated, "ranges", block)
    if yaw is not None:
        block = f"(:yaw_rotation (\n              ({yaw:.6f} {yaw:.6f})\n            )\n          )"
        updated = replace_balanced(updated, "yaw_rotation", block)
    if updated.count("(") != updated.count(")"):
        raise ValueError(f"region rewrite unbalanced: {region_name}")
    return text[:start] + updated + text[index + 1 :]


def specs() -> list[dict]:
    living = BDDL_ROOT / "libero_90" / "LIVING_ROOM_SCENE5_put_the_red_mug_on_the_left_plate.bddl"
    kitchen = BDDL_ROOT / "libero_90" / "KITCHEN_SCENE3_put_the_frying_pan_on_the_stove.bddl"
    return [
        {
            "name": "LIVING_ROOM_SCENE5_put_the_red_mug_on_the_right_plate",
            "edit": "goal",
            "source": living,
            "language": "put the red mug on the right plate",
            "obj_of_interest": "\n    red_coffee_mug_1\n    plate_2\n  ",
            "goal": "\n    (And (On red_coffee_mug_1 plate_2))\n  ",
            "track_body": "red_coffee_mug",
        },
        {
            "name": "KITCHEN_SCENE3_put_the_moka_pot_on_the_stove",
            "edit": "goal",
            "source": kitchen,
            "language": "put the moka pot on the stove",
            "obj_of_interest": "\n    moka_pot_1\n    flat_stove_1\n  ",
            "goal": "\n    (And (On moka_pot_1 flat_stove_1_cook_region))\n  ",
            "track_body": "moka_pot",
        },
        {
            "name": "LIVING_ROOM_SCENE5_put_the_red_mug_on_the_left_plate_shift",
            "edit": "placement",
            "source": living,
            "region": "red_coffee_mug_init_region",
            "ranges": (-0.3450, -0.0250, -0.2950, 0.0250),
            "track_body": "red_coffee_mug",
        },
        {
            "name": "KITCHEN_SCENE3_put_the_frying_pan_on_the_stove_shift",
            "edit": "placement",
            "source": kitchen,
            "region": "frypan_init_region",
            "ranges": (-0.0750, -0.1550, -0.0250, -0.1050),
            "track_body": "frypan",
        },
        {
            "name": "LIVING_ROOM_SCENE5_put_the_red_mug_on_the_left_plate_yaw",
            "edit": "geometry",
            "source": living,
            "region": "red_coffee_mug_init_region",
            "yaw": 1.570796,
            "track_body": "red_coffee_mug",
        },
        {
            "name": "KITCHEN_SCENE3_put_the_frying_pan_on_the_stove_yaw",
            "edit": "geometry",
            "source": kitchen,
            "region": "frypan_init_region",
            "yaw": 1.570796,
            "track_body": "frypan",
        },
    ]


def build_text(spec: dict) -> str:
    text = spec["source"].read_text(encoding="utf-8")
    if spec["edit"] == "goal":
        text = replace_section(text, "language", " " + spec["language"])
        text = replace_section(text, "obj_of_interest", spec["obj_of_interest"])
        text = replace_section(text, "goal", spec["goal"])
    elif spec["edit"] == "placement":
        text = rewrite_region(text, spec["region"], spec["ranges"], None)
    elif spec["edit"] == "geometry":
        text = rewrite_region(text, spec["region"], None, spec["yaw"])
    else:
        raise ValueError(spec["edit"])
    if text.count("(") != text.count(")"):
        raise ValueError(f"unbalanced bddl: {spec['name']}")
    return text


def make_env(bddl: Path) -> OffScreenRenderEnv:
    return OffScreenRenderEnv(
        bddl_file_name=str(bddl),
        camera_heights=HEIGHT,
        camera_widths=WIDTH,
    )


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
        raise RuntimeError(f"only kept {len(kept)} init states, wanted {count}")
    return np.stack(kept)


def filter_copied_states(env: OffScreenRenderEnv, states: np.ndarray) -> np.ndarray:
    env.reset()
    kept = []
    for state in states:
        env.set_init_state(state)
        if env.check_success():
            continue
        kept.append(np.asarray(state, dtype=np.float64))
    if len(kept) < 20:
        raise RuntimeError(f"goal init filter kept only {len(kept)} states")
    return np.stack(kept)


def body_pose(env: OffScreenRenderEnv, needle: str) -> tuple[str, np.ndarray]:
    model = env.sim.model
    data = env.sim.data
    nbody = int(model.nbody)
    for index in range(nbody):
        name = model.body(index).name
        if needle in name:
            return name, np.array(data.body_xpos[index][:2], dtype=np.float64)
    raise KeyError(needle)


def frame_from_state(env: OffScreenRenderEnv, state: np.ndarray) -> np.ndarray:
    env.reset()
    obs = env.set_init_state(state)
    return np.flipud(obs["agentview_image"])


def register(task_names: list[str]) -> None:
    init_text = BENCHMARK_INIT.read_text(encoding="utf-8")
    if f'"{SUITE}"' not in init_text:
        anchor = '"libero_object_env",\n]'
        if anchor not in init_text:
            raise RuntimeError("could not find suite list anchor")
        init_text = init_text.replace(anchor, f'"libero_object_env",\n    "{SUITE}",\n]', 1)
    class_name = "RANDOM_AXIS_20261003_TASK"
    if f"class {class_name}" not in init_text:
        init_text += (
            "\n\n@register_benchmark\n"
            f"class {class_name}(Benchmark):\n"
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
        if end < 0:
            raise RuntimeError("could not replace existing task map entry")
        map_text = map_text[:start] + block[4:] + map_text[end + 3 :]
    else:
        close = map_text.rstrip()
        if not close.endswith("}"):
            raise RuntimeError("task map does not end with a brace")
        map_text = close[:-1] + block + "}\n"
    TASK_MAP.write_text(map_text, encoding="utf-8")


def main() -> None:
    import imageio.v2 as imageio

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
        text = build_text(spec)
        bddl_path = bddl_dir / f"{spec['name']}.bddl"
        bddl_path.write_text(text, encoding="utf-8")
        source_init = INIT_ROOT / "libero_90" / f"{spec['source'].stem}.pruned_init"
        source_states = np.asarray(torch.load(source_init, weights_only=False))
        env = make_env(bddl_path)
        try:
            if spec["edit"] == "goal":
                states = filter_copied_states(env, source_states)
            else:
                states = sample_states(env, N_INIT)
            init_path = init_dir / f"{spec['name']}.pruned_init"
            torch.save(states, init_path)
            source_env = make_env(spec["source"])
            try:
                before = frame_from_state(source_env, source_states[0])
                _, before_xy = body_pose(source_env, spec["track_body"])
            finally:
                source_env.close()
            after = frame_from_state(env, states[0])
            _, after_xy = body_pose(env, spec["track_body"])
        finally:
            env.close()
        pair = np.concatenate([before, after], axis=1)
        imageio.imwrite(video_dir / f"{spec['name']}_pair.png", pair)
        imageio.mimsave(video_dir / f"{spec['name']}.mp4", [pair] * 20, fps=10)
        delta = (after_xy - before_xy).round(4).tolist()
        row = {
            "name": spec["name"],
            "edit": spec["edit"],
            "source_bddl": str(spec["source"]),
            "bddl": str(bddl_path),
            "init": str(init_dir / f"{spec['name']}.pruned_init"),
            "n_init": int(states.shape[0]),
            "tracked_body_xy_delta_m": delta,
        }
        if spec["edit"] == "goal":
            row["language"] = spec["language"]
        if spec["edit"] == "placement":
            row["ranges"] = list(spec["ranges"])
        if spec["edit"] == "geometry":
            row["yaw"] = spec["yaw"]
        rows.append(row)
        print("delta_m", spec["track_body"], delta, "n_init", states.shape[0], flush=True)

    register([row["name"] for row in rows])
    manifest = Path("/mnt/nas/gezuhao/xinghanbo") / SUITE / "manifest.json"
    manifest.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print("suite", SUITE)
    print("tasks", len(rows))
    print("manifest", manifest)


if __name__ == "__main__":
    main()
