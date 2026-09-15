from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import numpy as np

from .scene_reader import SceneState


LIBERO_PANDA_ARM_JOINTS = tuple(f"robot0_joint{idx}" for idx in range(1, 8))
CUROBO_PANDA_ARM_JOINTS = tuple(f"panda_joint{idx}" for idx in range(1, 8))


def quat_wxyz_to_matrix(quat: Any) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64).reshape(-1)[:4]
    if q.size != 4:
        raise ValueError(f"expected quaternion with 4 values, got {q.size}")
    q = q / max(float(np.linalg.norm(q)), 1e-12)
    w, x, y, z = q
    return np.asarray(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def matrix_to_quat_wxyz(matrix: Any) -> np.ndarray:
    m = np.asarray(matrix, dtype=np.float64).reshape(3, 3)
    trace = float(np.trace(m))
    if trace > 0.0:
        scale = np.sqrt(trace + 1.0) * 2.0
        quat = np.asarray(
            [0.25 * scale, (m[2, 1] - m[1, 2]) / scale, (m[0, 2] - m[2, 0]) / scale, (m[1, 0] - m[0, 1]) / scale]
        )
    else:
        axis = int(np.argmax(np.diag(m)))
        if axis == 0:
            scale = np.sqrt(max(1.0 + m[0, 0] - m[1, 1] - m[2, 2], 0.0)) * 2.0
            quat = np.asarray([(m[2, 1] - m[1, 2]) / scale, 0.25 * scale, (m[0, 1] + m[1, 0]) / scale, (m[0, 2] + m[2, 0]) / scale])
        elif axis == 1:
            scale = np.sqrt(max(1.0 + m[1, 1] - m[0, 0] - m[2, 2], 0.0)) * 2.0
            quat = np.asarray([(m[0, 2] - m[2, 0]) / scale, (m[0, 1] + m[1, 0]) / scale, 0.25 * scale, (m[1, 2] + m[2, 1]) / scale])
        else:
            scale = np.sqrt(max(1.0 + m[2, 2] - m[0, 0] - m[1, 1], 0.0)) * 2.0
            quat = np.asarray([(m[1, 0] - m[0, 1]) / scale, (m[0, 2] + m[2, 0]) / scale, (m[1, 2] + m[2, 1]) / scale, 0.25 * scale])
    quat = quat / max(float(np.linalg.norm(quat)), 1e-12)
    return quat if quat[0] >= 0.0 else -quat


def xyzw_to_wxyz(quat: Any) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64).reshape(-1)[:4]
    return q[[3, 0, 1, 2]]


def wxyz_to_xyzw(quat: Any) -> np.ndarray:
    q = np.asarray(quat, dtype=np.float64).reshape(-1)[:4]
    return q[[1, 2, 3, 0]]


def robot_base_pose(scene: SceneState) -> Optional[Tuple[np.ndarray, np.ndarray, str]]:
    candidates = list(scene.robot_joint_debug.get("frame_candidates", []) or [])
    by_name: Dict[str, Dict[str, Any]] = {str(row.get("name")): row for row in candidates}
    for name in ("robot0_base", "mount0_base", "mount0_controller_box", "mount0_pedestal"):
        row = by_name.get(name)
        if row is None:
            continue
        pos = np.asarray(row.get("pos_world", []), dtype=np.float64).reshape(-1)[:3]
        quat = np.asarray(row.get("quat_world_wxyz", []), dtype=np.float64).reshape(-1)[:4]
        if pos.size == 3 and quat.size == 4 and np.all(np.isfinite(pos)) and np.all(np.isfinite(quat)):
            return pos, quat, name
    return None


def world_to_base_position(position: Any, base_position: Any, base_quat_wxyz: Any) -> np.ndarray:
    rotation = quat_wxyz_to_matrix(base_quat_wxyz)
    return rotation.T @ (np.asarray(position, dtype=np.float64).reshape(-1)[:3] - np.asarray(base_position, dtype=np.float64).reshape(-1)[:3])


def base_to_world_position(position: Any, base_position: Any, base_quat_wxyz: Any) -> np.ndarray:
    rotation = quat_wxyz_to_matrix(base_quat_wxyz)
    return rotation @ np.asarray(position, dtype=np.float64).reshape(-1)[:3] + np.asarray(base_position, dtype=np.float64).reshape(-1)[:3]


def world_to_base_quat_wxyz(quat_wxyz: Any, base_quat_wxyz: Any) -> np.ndarray:
    rotation = quat_wxyz_to_matrix(base_quat_wxyz).T @ quat_wxyz_to_matrix(quat_wxyz)
    return matrix_to_quat_wxyz(rotation)
