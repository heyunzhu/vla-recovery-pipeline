from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import numpy as np

from .mujoco_compat import data_field, model_name_to_id, model_names


ROBOT_BODY_HINTS = (
    "robot",
    "panda",
    "gripper",
    "hand",
    "finger",
    "eef",
    "camera",
    "eye",
    "world",
    "table",
    "floor",
)

MUJOCO_GEOM_TYPE_NAMES = {
    0: "plane",
    1: "hfield",
    2: "sphere",
    3: "capsule",
    4: "ellipsoid",
    5: "cylinder",
    6: "box",
    7: "mesh",
    8: "sdf",
}


@dataclass
class ObjectState:
    name: str
    pos: np.ndarray
    quat: Optional[np.ndarray] = None
    geometry: Dict[str, Any] = field(default_factory=dict)


@dataclass
class JointState:
    name: str
    qpos: float
    qvel: float = 0.0


@dataclass
class SceneState:
    ee_pos: np.ndarray
    ee_quat: np.ndarray
    gripper_qpos: np.ndarray
    robot_qpos: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    objects: Dict[str, ObjectState] = field(default_factory=dict)
    joints: Dict[str, JointState] = field(default_factory=dict)
    robot_joint_debug: Dict[str, Any] = field(default_factory=dict)
    contacts: List[Dict[str, Any]] = field(default_factory=list)
    holding_evidence: Dict[str, Any] = field(default_factory=dict)
    raw_obs_keys: tuple[str, ...] = ()
    articulation_structure: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    articulation_diagnostics: List[str] = field(default_factory=list)

    @property
    def gripper_open(self) -> bool:
        # LIBERO exposes the two finger joints with opposite signs, e.g.
        # open ~= [0.04, -0.04] and closed ~= [0.0, 0.0].
        return float(np.mean(np.abs(self.gripper_qpos))) > 0.02

    def nearest_object(self) -> Optional[ObjectState]:
        if not self.objects:
            return None
        return min(self.objects.values(), key=lambda obj: float(np.linalg.norm(obj.pos - self.ee_pos)))


def _as_vec(obs: Dict[str, Any], key: str, dim: int) -> np.ndarray:
    value = np.asarray(obs.get(key, np.zeros(dim, dtype=np.float32)), dtype=np.float32).reshape(-1)
    out = np.zeros(dim, dtype=np.float32)
    out[: min(dim, value.size)] = value[: min(dim, value.size)]
    return out


def _as_flat_vec(obs: Dict[str, Any], key: str) -> np.ndarray:
    if key not in obs:
        return np.zeros(0, dtype=np.float32)
    return np.asarray(obs.get(key), dtype=np.float32).reshape(-1).copy()


def _body_name_allowed(name: str) -> bool:
    low = name.lower()
    if any(hint in low for hint in ROBOT_BODY_HINTS):
        return False
    return any(ch.isalpha() for ch in low)


def _safe_name(seq: Any, idx: int) -> Optional[str]:
    try:
        if idx < 0:
            return None
        return str(seq[idx])
    except Exception:
        return None


def _matrix_to_quat_wxyz(matrix: Any) -> np.ndarray:
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


def _geom_world_quat(data: Any, geom_id: int) -> List[float]:
    if hasattr(data, "geom_xquat"):
        quat = np.asarray(data.geom_xquat[geom_id], dtype=np.float64).reshape(-1)[:4]
        if quat.size == 4:
            return quat.astype(float).tolist()
    rotation = np.asarray(data.geom_xmat[geom_id], dtype=np.float64).reshape(3, 3)
    return _matrix_to_quat_wxyz(rotation).astype(float).tolist()


def _site_world_quat(data: Any, site_id: int) -> List[float]:
    if hasattr(data, "site_xquat"):
        quat = np.asarray(data.site_xquat[site_id], dtype=np.float64).reshape(-1)[:4]
        if quat.size == 4:
            return quat.astype(float).tolist()
    rotation = np.asarray(data.site_xmat[site_id], dtype=np.float64).reshape(3, 3)
    return _matrix_to_quat_wxyz(rotation).astype(float).tolist()


def _rigid_subtree_body_ids(model: Any, root_body_id: int) -> List[int]:
    """Collect rigid descendants without crossing another body's joint."""
    parent_ids = np.asarray(getattr(model, "body_parentid", []), dtype=np.int64).reshape(-1)
    joint_counts = np.asarray(getattr(model, "body_jntnum", []), dtype=np.int64).reshape(-1)
    if root_body_id < 0 or root_body_id >= parent_ids.size:
        return [root_body_id]
    children: Dict[int, List[int]] = {}
    for body_id, parent_id in enumerate(parent_ids.tolist()):
        if body_id == parent_id:
            continue
        children.setdefault(int(parent_id), []).append(int(body_id))
    out: List[int] = []
    queue = [int(root_body_id)]
    while queue:
        body_id = queue.pop(0)
        out.append(body_id)
        for child_id in children.get(body_id, []):
            if child_id < joint_counts.size and int(joint_counts[child_id]) > 0:
                continue
            queue.append(child_id)
    return out


def _read_mesh_data(model: Any, mesh_id: int) -> Dict[str, Any]:
    if mesh_id < 0:
        return {}
    try:
        vert_start = int(model.mesh_vertadr[mesh_id])
        vert_count = int(model.mesh_vertnum[mesh_id])
        face_start = int(model.mesh_faceadr[mesh_id])
        face_count = int(model.mesh_facenum[mesh_id])
        vertices = np.asarray(model.mesh_vert[vert_start : vert_start + vert_count], dtype=np.float32)
        faces = np.asarray(model.mesh_face[face_start : face_start + face_count], dtype=np.int64)
        if faces.size and int(faces.max()) >= vert_count:
            faces = faces - vert_start
        if vertices.ndim != 2 or vertices.shape[1] != 3 or faces.ndim != 2 or faces.shape[1] != 3:
            return {}
        return {
            "mesh_vertices": vertices.astype(float).tolist(),
            "mesh_faces": faces.astype(int).tolist(),
        }
    except Exception:
        return {}


def _read_body_geometry(model: Any, data: Any, body_id: int) -> Dict[str, Any]:
    geoms: List[Dict[str, Any]] = []
    sites: List[Dict[str, Any]] = []
    geom_names = model_names(model, "geom")
    site_names = model_names(model, "site")
    body_names = model_names(model, "body")
    mesh_names = getattr(model, "mesh_names", [])
    mesh_files = getattr(model, "mesh_files", [])
    mesh_scales = getattr(model, "mesh_scale", [])
    seen_geom_ids = set()
    rigid_body_ids = _rigid_subtree_body_ids(model, body_id)
    for geom_body_id in rigid_body_ids:
        try:
            geom_start = int(model.body_geomadr[geom_body_id])
            geom_count = int(model.body_geomnum[geom_body_id])
        except Exception:
            continue
        for geom_id in range(geom_start, geom_start + geom_count):
            if geom_id in seen_geom_ids:
                continue
            seen_geom_ids.add(geom_id)
            try:
                geom_type = int(model.geom_type[geom_id])
                geom_size = np.asarray(model.geom_size[geom_id], dtype=np.float32).reshape(-1).astype(float).tolist()
                geom_pos = np.asarray(data.geom_xpos[geom_id], dtype=np.float32).reshape(-1)[:3].astype(float).tolist()
                geom_quat = _geom_world_quat(data, geom_id)
                mesh_id = int(model.geom_dataid[geom_id]) if hasattr(model, "geom_dataid") else -1
                contype = int(model.geom_contype[geom_id]) if hasattr(model, "geom_contype") else None
                conaffinity = int(model.geom_conaffinity[geom_id]) if hasattr(model, "geom_conaffinity") else None
            except Exception:
                continue
            mesh_scale = None
            if mesh_id >= 0:
                try:
                    mesh_scale = np.asarray(mesh_scales[mesh_id], dtype=np.float32).reshape(-1).astype(float).tolist()
                except Exception:
                    mesh_scale = None
            collision_active = (
                True
                if contype is None and conaffinity is None
                else bool((contype or 0) != 0 or (conaffinity or 0) != 0)
            )
            geom = {
                "name": _safe_name(geom_names, geom_id) or f"geom_{geom_id}",
                "geom_id": geom_id,
                "body_id": geom_body_id,
                "body_name": _safe_name(body_names, geom_body_id) or f"body_{geom_body_id}",
                "type": geom_type,
                "shape": MUJOCO_GEOM_TYPE_NAMES.get(geom_type, f"unknown_{geom_type}"),
                "size": geom_size,
                "pos": geom_pos,
                "quat": geom_quat,
                "mesh_id": mesh_id if mesh_id >= 0 else None,
                "mesh_name": _safe_name(mesh_names, mesh_id) if mesh_id >= 0 else None,
                "mesh_path": _safe_name(mesh_files, mesh_id) if mesh_id >= 0 else None,
                "mesh_scale": mesh_scale,
                "contype": contype,
                "conaffinity": conaffinity,
                "collision_active": collision_active,
            }
            if collision_active and geom_type == 7:
                geom.update(_read_mesh_data(model, mesh_id))
            geoms.append(geom)
    site_body_ids = getattr(model, "site_bodyid", [])
    for site_id in range(len(site_names)):
        try:
            site_body_id = int(site_body_ids[site_id])
        except Exception:
            continue
        if site_body_id not in rigid_body_ids:
            continue
        try:
            site_type = int(model.site_type[site_id]) if hasattr(model, "site_type") else None
            site_size = np.asarray(model.site_size[site_id], dtype=np.float32).reshape(-1).astype(float).tolist()
            site_pos = np.asarray(data.site_xpos[site_id], dtype=np.float32).reshape(-1)[:3].astype(float).tolist()
            site_quat = _site_world_quat(data, site_id)
        except Exception:
            continue
        sites.append(
            {
                "name": _safe_name(site_names, site_id) or f"site_{site_id}",
                "site_id": site_id,
                "body_id": site_body_id,
                "body_name": _safe_name(body_names, site_body_id) or f"body_{site_body_id}",
                "type": site_type,
                "shape": MUJOCO_GEOM_TYPE_NAMES.get(site_type, f"unknown_{site_type}") if site_type is not None else None,
                "size": site_size,
                "pos": site_pos,
                "quat": site_quat,
            }
        )
    if not geoms and not sites:
        return {}
    return {
        "source": "mujoco_geom",
        "root_body_id": int(body_id),
        "rigid_body_ids": rigid_body_ids,
        "geoms": geoms,
        "sites": sites,
        "collision_geom_ids": [int(geom["geom_id"]) for geom in geoms if geom["collision_active"]],
    }


def _read_joint_states(model: Any, data: Any) -> Dict[str, JointState]:
    out: Dict[str, JointState] = {}
    joint_names = model_names(model, "joint") if model is not None else []
    qpos = np.asarray(getattr(data, "qpos", []), dtype=np.float32).reshape(-1) if data is not None else np.zeros(0, dtype=np.float32)
    qvel = np.asarray(getattr(data, "qvel", []), dtype=np.float32).reshape(-1) if data is not None else np.zeros(0, dtype=np.float32)
    for name in joint_names:
        try:
            joint_id = model_name_to_id(model, "joint", name)
            if joint_id is None:
                continue
            qpos_addr = int(model.jnt_qposadr[joint_id])
            qvel_addr = int(model.jnt_dofadr[joint_id]) if hasattr(model, "jnt_dofadr") else qpos_addr
        except Exception:
            continue
        value = float(qpos[qpos_addr]) if 0 <= qpos_addr < qpos.size else 0.0
        velocity = float(qvel[qvel_addr]) if 0 <= qvel_addr < qvel.size else 0.0
        out[str(name)] = JointState(str(name), value, velocity)
    return out


def _read_robot_joint_debug(model: Any, data: Any, obs_robot_qpos: np.ndarray) -> Dict[str, Any]:
    joint_names = model_names(model, "joint") if model is not None else []
    qpos = np.asarray(getattr(data, "qpos", []), dtype=np.float32).reshape(-1) if data is not None else np.zeros(0, dtype=np.float32)
    rows: List[Dict[str, Any]] = []
    for name in joint_names:
        low = str(name).lower()
        if not (low.startswith("robot0") or "panda" in low or "joint" in low):
            continue
        try:
            joint_id = model_name_to_id(model, "joint", name)
            if joint_id is None:
                continue
            joint_id = int(joint_id)
            qpos_addr = int(model.jnt_qposadr[joint_id])
            joint_type = int(model.jnt_type[joint_id]) if hasattr(model, "jnt_type") else None
            joint_range = np.asarray(model.jnt_range[joint_id], dtype=np.float32).astype(float).tolist() if hasattr(model, "jnt_range") else None
        except Exception:
            continue
        rows.append(
            {
                "name": str(name),
                "joint_id": joint_id,
                "qpos_addr": qpos_addr,
                "qpos": float(qpos[qpos_addr]) if 0 <= qpos_addr < qpos.size else None,
                "joint_type": joint_type,
                "joint_range": joint_range,
            }
        )
    frame_candidates: List[Dict[str, Any]] = []
    body_names = model_names(model, "body") if model is not None else []
    for name in body_names:
        low = str(name).lower()
        if not any(token in low for token in ("mount0_base", "mount0_controller_box", "mount0_pedestal", "robot0_base")):
            continue
        try:
            body_id = model_name_to_id(model, "body", name)
            if body_id is None:
                continue
            body_id = int(body_id)
            body_xpos = data_field(data, "body_xpos", "xpos")
            body_xquat = data_field(data, "body_xquat", "xquat")
            pos = np.asarray(body_xpos[body_id], dtype=np.float32).reshape(-1)[:3]
            quat = np.asarray(body_xquat[body_id], dtype=np.float32).reshape(-1)[:4]
        except Exception:
            continue
        frame_candidates.append(
            {
                "name": str(name),
                "body_id": body_id,
                "pos_world": pos.astype(float).tolist(),
                "quat_world_wxyz": quat.astype(float).tolist(),
            }
        )

    return {
        "obs_robot0_joint_pos": np.asarray(obs_robot_qpos, dtype=np.float32).astype(float).tolist(),
        "obs_robot0_joint_pos_len": int(np.asarray(obs_robot_qpos).size),
        "mujoco_robot_like_joints": rows,
        "frame_candidates": frame_candidates,
    }


def _finger_side(name: str) -> Optional[str]:
    low = str(name).lower()
    if not any(token in low for token in ("finger", "gripper", "hand")):
        return None
    if any(token in low for token in ("finger1", "finger_1", "leftfinger", "left_finger")):
        return "left"
    if any(token in low for token in ("finger2", "finger_2", "rightfinger", "right_finger")):
        return "right"
    return "unknown"


def _read_contacts(model: Any, data: Any, objects: Dict[str, ObjectState]) -> List[Dict[str, Any]]:
    if model is None or data is None:
        return []
    geom_names = model_names(model, "geom")
    body_names = model_names(model, "body")
    object_body_ids: Dict[int, str] = {}
    for object_name in objects:
        try:
            body_id = model_name_to_id(model, "body", object_name)
            if body_id is not None:
                object_body_ids[int(body_id)] = object_name
        except Exception:
            continue
    geom_to_object: Dict[int, str] = {}
    geom_body_ids = getattr(model, "geom_bodyid", [])
    body_parent_ids = getattr(model, "body_parentid", [])
    for geom_id in range(len(geom_names)):
        try:
            body_id = int(geom_body_ids[geom_id])
        except Exception:
            continue
        visited = set()
        while body_id >= 0 and body_id not in visited:
            visited.add(body_id)
            if body_id in object_body_ids:
                geom_to_object[geom_id] = object_body_ids[body_id]
                break
            try:
                parent_id = int(body_parent_ids[body_id])
            except Exception:
                break
            if parent_id == body_id:
                break
            body_id = parent_id

    contacts: List[Dict[str, Any]] = []
    ncon = int(getattr(data, "ncon", 0) or 0)
    raw_contacts = getattr(data, "contact", [])
    for idx in range(ncon):
        try:
            contact = raw_contacts[idx]
            geom1_id, geom2_id = int(contact.geom1), int(contact.geom2)
        except Exception:
            continue
        geom1_name = _safe_name(geom_names, geom1_id) or f"geom_{geom1_id}"
        geom2_name = _safe_name(geom_names, geom2_id) or f"geom_{geom2_id}"
        side1, side2 = _finger_side(geom1_name), _finger_side(geom2_name)
        object1, object2 = geom_to_object.get(geom1_id), geom_to_object.get(geom2_id)
        finger_side: Optional[str] = None
        object_name: Optional[str] = None
        if side1 is not None and object2 is not None:
            finger_side, object_name = side1, object2
        elif side2 is not None and object1 is not None:
            finger_side, object_name = side2, object1
        contacts.append(
            {
                "contact_index": idx,
                "geom1_id": geom1_id,
                "geom1_name": geom1_name,
                "geom2_id": geom2_id,
                "geom2_name": geom2_name,
                "object1": object1,
                "object2": object2,
                "geom1_body_name": _safe_name(body_names, int(geom_body_ids[geom1_id])) if geom1_id < len(geom_body_ids) else None,
                "geom2_body_name": _safe_name(body_names, int(geom_body_ids[geom2_id])) if geom2_id < len(geom_body_ids) else None,
                "finger_side": finger_side,
                "finger_object": object_name,
                "distance": float(getattr(contact, "dist", 0.0)),
            }
        )
    return contacts


def _infer_holding(scene: SceneState) -> Dict[str, Any]:
    aperture = float(np.mean(np.abs(scene.gripper_qpos)))
    closed = not scene.gripper_open
    by_object: Dict[str, Dict[str, Any]] = {}
    for contact in scene.contacts:
        object_name = contact.get("finger_object")
        side = contact.get("finger_side")
        if not object_name or side is None:
            continue
        record = by_object.setdefault(str(object_name), {"finger_sides": set(), "contacts": []})
        record["finger_sides"].add(str(side))
        record["contacts"].append(contact)

    candidates: List[Dict[str, Any]] = []
    for object_name, record in by_object.items():
        obj = scene.objects.get(object_name)
        if obj is None:
            continue
        sides = set(record["finger_sides"])
        bilateral = "left" in sides and "right" in sides
        distance = float(np.linalg.norm(obj.pos[:3] - scene.ee_pos[:3]))
        confidence = 0.98 if closed and bilateral else (0.45 if closed and sides else 0.05)
        candidates.append(
            {
                "object_name": object_name,
                "finger_sides": sorted(sides),
                "num_contacts": len(record["contacts"]),
                "bilateral_contact": bilateral,
                "eef_object_distance_m": distance,
                "confidence": confidence,
                "accepted": bool(closed and bilateral and distance <= 0.12),
            }
        )
    candidates.sort(key=lambda item: (bool(item["accepted"]), float(item["confidence"]), -float(item["eef_object_distance_m"])), reverse=True)
    accepted = [item for item in candidates if item["accepted"]]
    return {
        "status": "holding" if len(accepted) == 1 else ("ambiguous" if len(accepted) > 1 else "handempty_or_unconfirmed"),
        "object_name": accepted[0]["object_name"] if len(accepted) == 1 else None,
        "confidence": float(accepted[0]["confidence"]) if len(accepted) == 1 else 0.0,
        "gripper_closed": closed,
        "gripper_aperture_abs_mean": aperture,
        "criterion": "closed_and_bilateral_finger_contact_and_eef_distance_le_0.12m",
        "candidates": candidates,
    }


def read_scene(env: Any, obs: Dict[str, Any]) -> SceneState:
    robot_qpos = _as_flat_vec(obs, "robot0_joint_pos")
    scene = SceneState(
        ee_pos=_as_vec(obs, "robot0_eef_pos", 3),
        ee_quat=_as_vec(obs, "robot0_eef_quat", 4),
        gripper_qpos=_as_vec(obs, "robot0_gripper_qpos", 2),
        robot_qpos=robot_qpos,
        raw_obs_keys=tuple(sorted(obs.keys())),
    )

    sim = getattr(env, "sim", None)
    model = getattr(sim, "model", None)
    data = getattr(sim, "data", None)
    body_names = model_names(model, "body") if model is not None else []
    for name in body_names:
        if not _body_name_allowed(str(name)):
            continue
        try:
            body_id = model_name_to_id(model, "body", name)
            if body_id is None:
                continue
            body_xpos = data_field(data, "body_xpos", "xpos")
            body_xquat = data_field(data, "body_xquat", "xquat")
            pos = np.asarray(body_xpos[body_id], dtype=np.float32).copy()
            quat = np.asarray(body_xquat[body_id], dtype=np.float32).copy()
            geometry = _read_body_geometry(model, data, body_id)
        except Exception:
            continue
        if not np.all(np.isfinite(pos)):
            continue
        scene.objects[str(name)] = ObjectState(str(name), pos, quat, geometry=geometry)
    scene.joints = _read_joint_states(model, data)
    from .articulation import read_articulation_structure
    try:
        scene.articulation_structure = read_articulation_structure(model, data)
    except (AttributeError, IndexError, TypeError, ValueError) as exc:
        # Legacy/fake models may not expose structural arrays. Never guess a
        # joint binding from object-name substrings; articulated planning fails
        # closed if explicitly requested without this information.
        scene.articulation_diagnostics.append(f"articulation_structure_unavailable:{exc}")
    scene.contacts = _read_contacts(model, data, scene.objects)
    scene.holding_evidence = _infer_holding(scene)
    scene.robot_joint_debug = _read_robot_joint_debug(model, data, robot_qpos)
    expected_arm_names = [f"robot0_joint{idx}" for idx in range(1, 8)]
    named_arm_qpos = [scene.joints[name].qpos for name in expected_arm_names if name in scene.joints]
    if len(named_arm_qpos) == len(expected_arm_names):
        scene.robot_joint_debug["libero_arm_joint_names"] = expected_arm_names
        scene.robot_joint_debug["curobo_arm_joint_names"] = [f"panda_joint{idx}" for idx in range(1, 8)]
        if robot_qpos.size == len(expected_arm_names):
            # Keep q and EEF from the same observation snapshot. MuJoCo named
            # joints verify order and expose any simulator/observation lag.
            scene.robot_qpos = robot_qpos.astype(np.float32).copy()
            scene.robot_joint_debug["q_init_source"] = "obs_robot0_joint_pos_verified_by_named_mujoco_joints"
            scene.robot_joint_debug["obs_vs_mujoco_q_linf"] = float(
                np.max(np.abs(robot_qpos.astype(np.float64) - np.asarray(named_arm_qpos, dtype=np.float64)))
            )
        else:
            scene.robot_qpos = np.asarray(named_arm_qpos, dtype=np.float32)
            scene.robot_joint_debug["q_init_source"] = "mujoco_named_robot0_joint1_to_joint7_fallback"
    else:
        scene.robot_joint_debug["q_init_source"] = "obs_robot0_joint_pos_fallback"
        scene.robot_joint_debug["q_init_warning"] = "could not resolve all robot0_joint1..robot0_joint7 from MuJoCo"
    scene.robot_joint_debug["obs_eef_world"] = {
        "pos": scene.ee_pos.astype(float).tolist(),
        "quat_xyzw": scene.ee_quat.astype(float).tolist(),
    }
    return scene
