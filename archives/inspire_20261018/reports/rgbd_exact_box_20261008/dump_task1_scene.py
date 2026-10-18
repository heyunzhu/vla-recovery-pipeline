"""Save the simulator state for spatial task 1, seed 7, init 0, settle 10."""
import json
import os
import sys
from pathlib import Path

os.environ.setdefault("MUJOCO_GL", "egl")
os.environ.setdefault("PYOPENGL_PLATFORM", "egl")
import numpy as np

repo = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/code")
sys.path.insert(0, str(repo))
from libero.libero import benchmark, get_libero_path
from libero.libero.envs import OffScreenRenderEnv
from experiments.robot.libero.tiptop_repro.scene_reader import read_scene


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.astype(float).tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(item) for item in value]
    return value


suite = benchmark.get_benchmark_dict()["libero_spatial"]()
task = suite.get_task(1)
initial_states = suite.get_task_init_states(1)
bddl = Path(get_libero_path("bddl_files")) / task.problem_folder / task.bddl_file
env = OffScreenRenderEnv(
    bddl_file_name=str(bddl), camera_names=["agentview"],
    camera_heights=256, camera_widths=256, camera_depths=True,
)
try:
    env.seed(7)
    env.reset()
    obs = env.set_init_state(initial_states[0])
    for _ in range(10):
        obs, _, _, _ = env.step([0.0] * 6 + [-1.0])
    scene = read_scene(env, obs)
finally:
    env.close()
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/task1")
root.mkdir(parents=True, exist_ok=True)
payload = {
    "language": task.language, "bddl_path": str(bddl), "task_id": 1,
    "ee_pos": jsonable(scene.ee_pos), "ee_quat": jsonable(scene.ee_quat),
    "gripper_qpos": jsonable(scene.gripper_qpos), "robot_qpos": jsonable(scene.robot_qpos),
    "robot_joint_debug": jsonable(scene.robot_joint_debug),
    "holding_evidence": jsonable(scene.holding_evidence),
    "objects": {name: {"pos": jsonable(obj.pos), "quat": jsonable(obj.quat), "geometry": jsonable(obj.geometry)}
                for name, obj in scene.objects.items()},
}
(root / "scene.json").write_text(json.dumps(payload) + "\n", encoding="utf-8")
print(json.dumps({"language": task.language, "objects": sorted(scene.objects)}, indent=2))
