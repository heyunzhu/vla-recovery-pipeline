from __future__ import annotations

from typing import List, Optional

import numpy as np
import torch

from .cutamp_like import (
    CuTAMPPlanResult,
    CuTAMPStylePlanner,
    ParticleOptimizationConfig,
    ParticleResult,
    PlanSkeleton,
    enumerate_recovery_skeletons,
)
from .domain import PlanStep, RecoveryPlan
from .predicates import SymbolicState
from .scene_reader import ObjectState, SceneState
from .tamp_scene import TAMPProblem


def _vec3(x: np.ndarray, device: torch.device) -> torch.Tensor:
    return torch.as_tensor(np.asarray(x, dtype=np.float32)[:3], dtype=torch.float32, device=device)


def _segment_point_distance(a: torch.Tensor, b: torch.Tensor, p: torch.Tensor) -> torch.Tensor:
    ab = b - a
    denom = torch.clamp((ab * ab).sum(dim=-1), min=1e-6)
    t = torch.clamp(((p - a) * ab).sum(dim=-1) / denom, 0.0, 1.0)
    closest = a + t.unsqueeze(-1) * ab
    return torch.linalg.norm(closest - p, dim=-1)


def _table_bounds_tensor(tamp_problem: TAMPProblem, device: torch.device) -> torch.Tensor:
    bounds = tamp_problem.table_geometry.get("bounds", {}) if tamp_problem.table_geometry else {}
    vals = [
        float(bounds.get("x_min", -tamp_problem.table_z * 0.0 - 0.65)),
        float(bounds.get("x_max", 0.65)),
        float(bounds.get("y_min", -0.45)),
        float(bounds.get("y_max", 0.45)),
    ]
    return torch.as_tensor(vals, dtype=torch.float32, device=device)


def _bounds_violation(points: torch.Tensor, bounds: torch.Tensor, margin: float = 0.03) -> torch.Tensor:
    x_min, x_max, y_min, y_max = bounds
    return (
        torch.relu(x_min + margin - points[:, 0])
        + torch.relu(points[:, 0] - x_max + margin)
        + torch.relu(y_min + margin - points[:, 1])
        + torch.relu(points[:, 1] - y_max + margin)
    )


class CuTAMPStylePlannerV2(CuTAMPStylePlanner):
    """cuTAMP-like planner that consumes a TAMPProblem-like scene.

    Compared with the first approximation, particles are initialized from
    object-specific grasp candidates and surface-specific placement candidates.
    This mirrors TiPToP's data flow more closely while staying independent of
    the external cuTAMP/cuRobo packages.
    """

    def __init__(self, cfg: Optional[ParticleOptimizationConfig] = None) -> None:
        self.cfg = cfg or ParticleOptimizationConfig()

    def plan(
        self,
        scene: SceneState,
        sym: SymbolicState,
        tamp_problem: TAMPProblem,
        skeletons: Optional[List[PlanSkeleton]] = None,
    ) -> CuTAMPPlanResult:
        skeletons = skeletons or enumerate_recovery_skeletons(sym)
        results = [self._optimize_skeleton(scene, sym, tamp_problem, skel) for skel in skeletons]
        results.sort(key=lambda item: (0 if item.feasible else 1, item.best_cost))
        best = results[0]
        return CuTAMPPlanResult(plan=self._to_recovery_plan(best), particle=best, all_particles=results)

    def _optimize_skeleton(
        self,
        scene: SceneState,
        sym: SymbolicState,
        tamp_problem: TAMPProblem,
        skeleton: PlanSkeleton,
    ) -> ParticleResult:
        cfg = self.cfg
        device = torch.device(cfg.device)
        n = cfg.num_particles
        table_z = tamp_problem.table_z
        target = sym.target or scene.nearest_object()
        goal = sym.goal
        obstacle = self._choose_obstacle(scene, sym)

        ee = _vec3(scene.ee_pos, device)
        target_pos = _vec3(target.pos if target is not None else scene.ee_pos, device)
        goal_pos = _vec3(goal.pos if goal is not None else np.array([0.0, 0.0, table_z]), device)
        obstacle_pos = _vec3(obstacle.pos if obstacle is not None else target_pos.detach().cpu().numpy(), device)
        grasp_base = self._sample_candidates(
            tamp_problem.grasp_points(target.name) if target is not None else None,
            target_pos,
            n,
            device,
        )
        place_key = goal.name if goal is not None else "table"
        place_base = self._sample_candidates(tamp_problem.place_candidates.get(place_key, None), goal_pos, n, device)
        obstacle_base = self._sample_candidates(tamp_problem.place_candidates.get("table", None), obstacle_pos, n, device)
        retreat_base = self._sample_candidates(tamp_problem.retreat_points(), ee, n, device)
        object_points = self._object_points(scene, target, goal, obstacle, device)
        table_bounds = _table_bounds_tensor(tamp_problem, device)

        grasp_xy = torch.randn(n, 2, device=device) * 0.015
        place_xy = torch.randn(n, 2, device=device) * 0.020
        retreat_xy = torch.randn(n, 2, device=device)
        obstacle_xy = torch.randn(n, 2, device=device) * 0.060
        raw = [grasp_xy, place_xy, retreat_xy, obstacle_xy]
        for tensor in raw:
            tensor.requires_grad_(True)
        opt = torch.optim.Adam(raw, lr=cfg.lr)

        for _ in range(cfg.num_iters):
            opt.zero_grad(set_to_none=True)
            cost, _ = self._cost(
                skeleton,
                ee,
                target_pos,
                goal_pos,
                obstacle_pos,
                object_points,
                table_bounds,
                grasp_base,
                place_base,
                obstacle_base,
                retreat_base,
                table_z,
                grasp_xy,
                place_xy,
                retreat_xy,
                obstacle_xy,
            )
            cost.mean().backward()
            opt.step()

        with torch.no_grad():
            cost, parts = self._cost(
                skeleton,
                ee,
                target_pos,
                goal_pos,
                obstacle_pos,
                object_points,
                table_bounds,
                grasp_base,
                place_base,
                obstacle_base,
                retreat_base,
                table_z,
                grasp_xy,
                place_xy,
                retreat_xy,
                obstacle_xy,
            )
            best_idx = int(torch.argmin(cost).item())
            feasible = cost < 1.0
            best_params = {k: v[best_idx].detach().cpu().numpy().astype(float).tolist() for k, v in parts.items()}
            diagnostics = {
                "mean_cost": float(cost.mean().item()),
                "min_cost": float(cost.min().item()),
                "success_fraction": float(feasible.float().mean().item()),
                "num_grasp_candidates": float(0 if target is None else len(tamp_problem.grasps.get(target.name, []))),
                "num_place_candidates": float(len(tamp_problem.place_candidates.get(place_key, []))),
                "num_retreat_candidates": float(len(tamp_problem.retreat_candidates)),
                "num_movables": float(len(tamp_problem.movables)),
                "num_surfaces": float(len(tamp_problem.surfaces)),
                "num_statics": float(len(tamp_problem.statics)),
                "table_bounds_x_min": float(table_bounds[0].item()),
                "table_bounds_x_max": float(table_bounds[1].item()),
                "table_bounds_y_min": float(table_bounds[2].item()),
                "table_bounds_y_max": float(table_bounds[3].item()),
                "geometry_source": 1.0 if tamp_problem.table_geometry else 0.0,
            }
        return ParticleResult(
            skeleton=skeleton,
            best_cost=diagnostics["min_cost"],
            success_fraction=diagnostics["success_fraction"],
            params=best_params,
            diagnostics=diagnostics,
        )

    def _cost(
        self,
        skeleton: PlanSkeleton,
        ee: torch.Tensor,
        target_pos: torch.Tensor,
        goal_pos: torch.Tensor,
        obstacle_pos: torch.Tensor,
        object_points: torch.Tensor,
        table_bounds: torch.Tensor,
        grasp_base: torch.Tensor,
        place_base: torch.Tensor,
        obstacle_base: torch.Tensor,
        retreat_base: torch.Tensor,
        table_z: float,
        grasp_xy: torch.Tensor,
        place_xy: torch.Tensor,
        retreat_xy: torch.Tensor,
        obstacle_xy: torch.Tensor,
    ):
        cfg = self.cfg
        n = grasp_xy.shape[0]
        grasp_xy_pos = grasp_base[:, :2] + torch.tanh(grasp_xy) * 0.045
        grasp_z = torch.full((n, 1), table_z + cfg.grasp_height, dtype=grasp_base.dtype, device=grasp_base.device)
        grasp = torch.cat([grasp_xy_pos, grasp_z], dim=-1)
        pregrasp_z = torch.full((n, 1), table_z + cfg.pregrasp_height, dtype=grasp.dtype, device=grasp.device)
        pregrasp = torch.cat([grasp[:, :2], pregrasp_z], dim=-1)
        place_xy_pos = place_base[:, :2] + torch.tanh(place_xy) * 0.055
        place_z = torch.full((n, 1), table_z + cfg.place_height, dtype=place_base.dtype, device=place_base.device)
        place = torch.cat([place_xy_pos, place_z], dim=-1)
        retreat_xy_pos = retreat_base[:, :2] + torch.tanh(retreat_xy) * 0.035
        retreat_z = torch.maximum(
            retreat_base[:, 2:3],
            torch.full((n, 1), table_z + 0.20, dtype=ee.dtype, device=ee.device),
        )
        retreat = torch.cat([retreat_xy_pos, retreat_z], dim=-1)
        obstacle_xy_pos = obstacle_base[:, :2] + torch.tanh(obstacle_xy) * 0.18
        obstacle_z = torch.full((n, 1), table_z + cfg.place_height, dtype=obstacle_base.dtype, device=obstacle_base.device)
        obstacle_place = torch.cat([obstacle_xy_pos, obstacle_z], dim=-1)

        points = [pregrasp, grasp, place, retreat]
        if "move_obstacle_aside" in skeleton.steps:
            points.append(obstacle_place)
        stacked = torch.cat(points, dim=0)
        workspace_cost = _bounds_violation(stacked, table_bounds).reshape(len(points), n).sum(dim=0)
        z_low = torch.relu(table_z + 0.015 - stacked[:, 2]).reshape(len(points), n).sum(dim=0)
        z_high = torch.relu(stacked[:, 2] - 1.25).reshape(len(points), n).sum(dim=0)

        cost = 0.35 * workspace_cost + 0.4 * z_low + 0.15 * z_high
        cost = cost + 0.18 * torch.linalg.norm(grasp[:, :2] - target_pos[:2], dim=-1)
        cost = cost + 0.18 * torch.linalg.norm(place[:, :2] - goal_pos[:2], dim=-1)
        cost = cost + 0.04 * torch.linalg.norm(pregrasp - ee.unsqueeze(0), dim=-1)
        cost = cost + 0.04 * torch.linalg.norm(place - grasp, dim=-1)

        if object_points.numel() > 0:
            for p in object_points:
                pp = p.unsqueeze(0).repeat(n, 1)
                d1 = _segment_point_distance(ee.unsqueeze(0).repeat(n, 1), pregrasp, pp)
                d2 = _segment_point_distance(grasp, place, pp)
                cost = cost + 0.35 * torch.relu(cfg.collision_margin - d1)
                cost = cost + 0.45 * torch.relu(cfg.collision_margin - d2)

        if skeleton.name == "direct_regrasp_place":
            cost = cost + 0.12
        if "move_obstacle_aside" in skeleton.steps:
            old_dist = torch.linalg.norm(obstacle_pos[:2] - target_pos[:2])
            new_dist = torch.linalg.norm(obstacle_place[:, :2] - target_pos[:2], dim=-1)
            cost = cost + 0.15 * torch.relu(0.18 - new_dist) - 0.04 * torch.relu(new_dist - old_dist)

        parts = {
            "pregrasp_pos": pregrasp,
            "grasp_pos": grasp,
            "place_pos": place,
            "retreat_pos": retreat,
            "obstacle_place_pos": obstacle_place,
        }
        return cost, parts

    def _sample_candidates(
        self,
        candidates: Optional[np.ndarray],
        fallback: torch.Tensor,
        n: int,
        device: torch.device,
    ) -> torch.Tensor:
        if candidates is None or len(candidates) == 0:
            return fallback.unsqueeze(0).repeat(n, 1)
        cand = torch.as_tensor(np.asarray(candidates, dtype=np.float32)[:, :3], dtype=torch.float32, device=device)
        idx = torch.randint(0, cand.shape[0], (n,), device=device)
        return cand[idx].clone()

    def _choose_obstacle(self, scene: SceneState, sym: SymbolicState) -> Optional[ObjectState]:
        if sym.nearest is not None and sym.target is not None and sym.nearest.name != sym.target.name:
            return sym.nearest
        return None

    def _to_recovery_plan(self, result: ParticleResult) -> RecoveryPlan:
        return RecoveryPlan(
            steps=[PlanStep(name=name, args=dict(result.params)) for name in result.skeleton.steps],
            reason=result.skeleton.reason,
        )
