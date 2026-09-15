from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import torch

from .domain import PlanStep, RecoveryPlan
from .predicates import SymbolicState
from .scene_reader import ObjectState, SceneState


@dataclass(frozen=True)
class PlanSkeleton:
    name: str
    steps: List[str]
    reason: str


@dataclass
class ParticleOptimizationConfig:
    num_particles: int = 192
    num_iters: int = 80
    lr: float = 0.045
    workspace_radius: float = 0.85
    table_z: float = 0.78
    pregrasp_height: float = 0.16
    grasp_height: float = 0.035
    place_height: float = 0.16
    collision_margin: float = 0.085
    device: str = "cpu"


@dataclass
class ParticleResult:
    skeleton: PlanSkeleton
    best_cost: float
    success_fraction: float
    params: Dict[str, List[float]]
    diagnostics: Dict[str, float] = field(default_factory=dict)

    @property
    def feasible(self) -> bool:
        return self.success_fraction > 0.0


@dataclass
class CuTAMPPlanResult:
    plan: RecoveryPlan
    particle: ParticleResult
    all_particles: List[ParticleResult]


def enumerate_recovery_skeletons(sym: SymbolicState) -> List[PlanSkeleton]:
    if sym.predicates.get("target_at_goal", False):
        return [PlanSkeleton("already_at_goal_retreat", ["retreat_open"], "already_at_goal")]

    skeletons = [
        PlanSkeleton(
            "direct_regrasp_place",
            ["move_above_object", "descend_to_grasp", "close_gripper", "lift", "move_above_goal", "slow_place", "retreat_open"],
            "direct_regrasp_and_place",
        ),
        PlanSkeleton(
            "retreat_regrasp_place",
            ["retreat_open", "move_above_object", "descend_to_grasp", "close_gripper", "lift", "move_above_goal", "slow_place", "retreat_open"],
            "retreat_then_regrasp_and_place",
        ),
        PlanSkeleton(
            "wide_retreat_regrasp_place",
            ["wide_retreat_open", "move_above_object", "descend_to_grasp", "close_gripper", "lift", "move_above_goal", "slow_place", "retreat_open"],
            "wide_retreat_then_regrasp_and_place",
        ),
    ]
    if not sym.predicates.get("nearest_is_target", True):
        skeletons.insert(
            0,
            PlanSkeleton(
                "move_nearest_as_obstacle_then_regrasp",
                [
                    "retreat_open",
                    "move_above_obstacle",
                    "descend_to_obstacle",
                    "close_gripper",
                    "lift_obstacle",
                    "move_obstacle_aside",
                    "open_gripper",
                    "retreat_open",
                    "move_above_object",
                    "descend_to_grasp",
                    "close_gripper",
                    "lift",
                    "move_above_goal",
                    "slow_place",
                    "retreat_open",
                ],
                "move_nearest_obstacle_then_regrasp",
            ),
        )
    return skeletons


def _vec3(x: np.ndarray | List[float], device: torch.device) -> torch.Tensor:
    return torch.as_tensor(np.asarray(x, dtype=np.float32)[:3], dtype=torch.float32, device=device)


def _segment_point_distance(a: torch.Tensor, b: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
    ab = b - a
    denom = torch.clamp((ab * ab).sum(dim=-1), min=1e-6)
    t = torch.clamp(((p - a) * ab).sum(dim=-1) / denom, 0.0, 1.0)
    closest = a + t.unsqueeze(-1) * ab
    return torch.linalg.norm(closest - p, dim=-1)


class CuTAMPStylePlanner:
    """A small cuTAMP-like optimizer for LIBERO recovery.

    It keeps TiPToP's planning shape: enumerate symbolic skeletons, sample many
    particles for continuous parameters, optimize them in parallel, then choose
    the best feasible particle. It uses proxy costs instead of full robot IK and
    cuRobo because those are not available in the current LIBERO stack.
    """

    def __init__(self, cfg: Optional[ParticleOptimizationConfig] = None) -> None:
        self.cfg = cfg or ParticleOptimizationConfig()

    def plan(self, scene: SceneState, sym: SymbolicState) -> CuTAMPPlanResult:
        skeletons = enumerate_recovery_skeletons(sym)
        results = [self._optimize_skeleton(scene, sym, skel) for skel in skeletons]
        results.sort(key=lambda item: (0 if item.feasible else 1, item.best_cost))
        best = results[0]
        return CuTAMPPlanResult(plan=self._to_recovery_plan(best), particle=best, all_particles=results)

    def _optimize_skeleton(self, scene: SceneState, sym: SymbolicState, skeleton: PlanSkeleton) -> ParticleResult:
        cfg = self.cfg
        device = torch.device(cfg.device)
        n = cfg.num_particles
        target = sym.target or scene.nearest_object()
        goal = sym.goal
        obstacle = self._choose_obstacle(scene, sym)
        ee = _vec3(scene.ee_pos, device)
        target_pos = _vec3(target.pos if target is not None else scene.ee_pos, device)
        goal_pos = _vec3(goal.pos if goal is not None else target_pos.detach().cpu().numpy(), device)
        obstacle_pos = _vec3(obstacle.pos if obstacle is not None else target_pos.detach().cpu().numpy(), device)
        object_points = self._object_points(scene, target, goal, obstacle, device)

        grasp_xy = torch.randn(n, 2, device=device) * 0.035
        place_xy = torch.randn(n, 2, device=device) * 0.045
        retreat_xy = torch.randn(n, 2, device=device)
        obstacle_xy = torch.randn(n, 2, device=device) * 0.12
        raw = [grasp_xy, place_xy, retreat_xy, obstacle_xy]
        for tensor in raw:
            tensor.requires_grad_(True)
        opt = torch.optim.Adam(raw, lr=cfg.lr)

        for _ in range(cfg.num_iters):
            opt.zero_grad(set_to_none=True)
            cost, _ = self._cost(scene, skeleton, ee, target_pos, goal_pos, obstacle_pos, object_points, grasp_xy, place_xy, retreat_xy, obstacle_xy)
            cost.mean().backward()
            opt.step()

        with torch.no_grad():
            cost, parts = self._cost(scene, skeleton, ee, target_pos, goal_pos, obstacle_pos, object_points, grasp_xy, place_xy, retreat_xy, obstacle_xy)
            best_idx = int(torch.argmin(cost).item())
            feasible = cost < 1.0
            best_params = {k: v[best_idx].detach().cpu().numpy().astype(float).tolist() for k, v in parts.items()}
            diag = {
                "mean_cost": float(cost.mean().item()),
                "min_cost": float(cost.min().item()),
                "success_fraction": float(feasible.float().mean().item()),
            }
        return ParticleResult(
            skeleton=skeleton,
            best_cost=diag["min_cost"],
            success_fraction=diag["success_fraction"],
            params=best_params,
            diagnostics=diag,
        )

    def _cost(
        self,
        scene: SceneState,
        skeleton: PlanSkeleton,
        ee: torch.Tensor,
        target_pos: torch.Tensor,
        goal_pos: torch.Tensor,
        obstacle_pos: torch.Tensor,
        object_points: torch.Tensor,
        grasp_xy: torch.Tensor,
        place_xy: torch.Tensor,
        retreat_xy: torch.Tensor,
        obstacle_xy: torch.Tensor,
    ):
        cfg = self.cfg
        n = grasp_xy.shape[0]
        target_base = target_pos.unsqueeze(0).expand(n, -1)
        grasp_xy_pos = target_base[:, :2] + torch.tanh(grasp_xy) * 0.07
        grasp_z = torch.full((n, 1), cfg.table_z + cfg.grasp_height, dtype=grasp_xy.dtype, device=grasp_xy.device)
        grasp = torch.cat([grasp_xy_pos, grasp_z], dim=-1)
        pregrasp_z = torch.full((n, 1), cfg.table_z + cfg.pregrasp_height, dtype=grasp_xy.dtype, device=grasp_xy.device)
        pregrasp = torch.cat([grasp_xy_pos, pregrasp_z], dim=-1)

        goal_base = goal_pos.unsqueeze(0).expand(n, -1)
        place_xy_pos = goal_base[:, :2] + torch.tanh(place_xy) * 0.08
        place_z = torch.full((n, 1), cfg.table_z + cfg.place_height, dtype=place_xy.dtype, device=place_xy.device)
        place = torch.cat([place_xy_pos, place_z], dim=-1)

        retreat_dir = torch.nn.functional.normalize(retreat_xy + 1e-4, dim=-1)
        ee_base = ee.unsqueeze(0).expand(n, -1)
        retreat_xy_pos = ee_base[:, :2] + retreat_dir * 0.13
        retreat_z = torch.maximum(
            ee_base[:, 2:3],
            torch.full((n, 1), cfg.table_z + 0.22, dtype=retreat_xy.dtype, device=retreat_xy.device),
        )
        retreat = torch.cat([retreat_xy_pos, retreat_z], dim=-1)

        obstacle_base = obstacle_pos.unsqueeze(0).expand(n, -1)
        obstacle_xy_pos = obstacle_base[:, :2] + torch.tanh(obstacle_xy) * 0.20
        obstacle_z = torch.full((n, 1), cfg.table_z + cfg.place_height, dtype=obstacle_xy.dtype, device=obstacle_xy.device)
        obstacle_place = torch.cat([obstacle_xy_pos, obstacle_z], dim=-1)

        points = [pregrasp, grasp, place, retreat]
        if "move_obstacle_aside" in skeleton.steps:
            points.append(obstacle_place)
        stacked = torch.cat(points, dim=0)
        xy_radius = torch.linalg.norm(stacked[:, :2], dim=-1)
        workspace_cost = torch.relu(xy_radius - cfg.workspace_radius).reshape(len(points), n).sum(dim=0)
        z_low = torch.relu(cfg.table_z + 0.015 - stacked[:, 2]).reshape(len(points), n).sum(dim=0)
        z_high = torch.relu(stacked[:, 2] - 1.25).reshape(len(points), n).sum(dim=0)

        cost = 0.25 * workspace_cost + 0.4 * z_low + 0.15 * z_high
        cost = cost + 0.30 * torch.linalg.norm(grasp[:, :2] - target_pos[:2], dim=-1)
        cost = cost + 0.35 * torch.linalg.norm(place[:, :2] - goal_pos[:2], dim=-1)
        cost = cost + 0.04 * torch.linalg.norm(pregrasp - ee.unsqueeze(0), dim=-1)
        cost = cost + 0.04 * torch.linalg.norm(place - grasp, dim=-1)

        if object_points.numel() > 0:
            for p in object_points:
                d1 = _segment_point_distance(ee.unsqueeze(0).repeat(n, 1), pregrasp, p.unsqueeze(0).repeat(n, 1))
                d2 = _segment_point_distance(grasp, place, p.unsqueeze(0).repeat(n, 1))
                cost = cost + 0.35 * torch.relu(cfg.collision_margin - d1)
                cost = cost + 0.45 * torch.relu(cfg.collision_margin - d2)

        direct_penalty = 0.0
        if skeleton.name == "direct_regrasp_place":
            direct_penalty = 0.12
        if "move_obstacle_aside" in skeleton.steps:
            old_dist = torch.linalg.norm(obstacle_pos[:2] - target_pos[:2])
            new_dist = torch.linalg.norm(obstacle_place[:, :2] - target_pos[:2], dim=-1)
            cost = cost + 0.15 * torch.relu(0.18 - new_dist) - 0.04 * torch.relu(new_dist - old_dist)
        cost = cost + direct_penalty

        parts = {
            "pregrasp_pos": pregrasp,
            "grasp_pos": grasp,
            "place_pos": place,
            "retreat_pos": retreat,
            "obstacle_place_pos": obstacle_place,
        }
        return cost, parts

    def _object_points(
        self,
        scene: SceneState,
        target: Optional[ObjectState],
        goal: Optional[ObjectState],
        obstacle: Optional[ObjectState],
        device: torch.device,
    ) -> torch.Tensor:
        ignore = {obj.name for obj in (target, goal) if obj is not None}
        points = []
        for obj in scene.objects.values():
            if obj.name in ignore:
                continue
            if obstacle is not None and obj.name == obstacle.name:
                points.append(obj.pos[:3])
            elif float(np.linalg.norm(obj.pos[:2] - scene.ee_pos[:2])) < 0.35:
                points.append(obj.pos[:3])
        if not points:
            return torch.empty(0, 3, dtype=torch.float32, device=device)
        return torch.as_tensor(np.asarray(points, dtype=np.float32), dtype=torch.float32, device=device)

    def _choose_obstacle(self, scene: SceneState, sym: SymbolicState) -> Optional[ObjectState]:
        if sym.nearest is not None and sym.target is not None and sym.nearest.name != sym.target.name:
            return sym.nearest
        return None

    def _to_recovery_plan(self, result: ParticleResult) -> RecoveryPlan:
        steps = []
        for name in result.skeleton.steps:
            args = dict(result.params)
            steps.append(PlanStep(name=name, args=args))
        return RecoveryPlan(steps=steps, reason=result.skeleton.reason)
