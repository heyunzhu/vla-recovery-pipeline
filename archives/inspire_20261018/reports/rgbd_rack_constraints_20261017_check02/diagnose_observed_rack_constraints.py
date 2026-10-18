"""Saved-problem ablations only: never create a simulator or execute actions.

The release variant replaces the flat support proxy constraint with proximity
to a measured, footprint-validated upright hover pose. Physical collision and
kinematic constraints remain active. This is not evidence of stable placement.
"""
import argparse
import importlib.util
import json
from pathlib import Path


def install_release_constraint(backend, problem):
    import torch
    from cutamp.cost_function import CostFunction
    policies = backend._place_yaw_policies_by_surface(problem, {})
    original = CostFunction.stable_placement_costs

    def measured(self, rollout, spheres):
        result = original(self, rollout, spheres)
        if result is None:
            return result
        grouped = {}
        for constraint in self.stable_placement_constraints:
            obj, _, placement, surface = constraint.params
            if not isinstance(policies.get(surface), list):
                continue
            pose = rollout['obj_to_pose'][obj][:, rollout['action_to_pose_ts'][placement]]
            values = torch.as_tensor(policies[surface], device=pose.device, dtype=pose.dtype)
            delta = pose[:, None, :3, 3] - values[None, :, :3]
            yaw = torch.atan2(pose[:, 1, 0], pose[:, 0, 0])
            angle = yaw[:, None] - values[None, :, 3]
            angle = torch.atan2(torch.sin(angle), torch.cos(angle)).abs()
            # One candidate must satisfy all coordinates together. Multiplying
            # metre errors by ten makes the native 0.01 tolerance at most 1 mm.
            score = 10 * delta.norm(dim=-1) + angle
            index = score.argmin(dim=1)
            selected = delta[torch.arange(len(pose), device=pose.device), index]
            selected_angle = angle.gather(1, index[:, None])[:, 0]
            grouped.setdefault(surface, []).append((
                10 * selected[:, :2].norm(dim=-1) + selected_angle,
                10 * selected[:, 2].abs()))
        for surface, rows in grouped.items():
            result['values'][surface+'_in_xy'] = torch.stack([r[0] for r in rows], dim=1)
            result['values'][surface+'_support'] = torch.stack([r[1] for r in rows], dim=1)
        return result

    CostFunction.stable_placement_costs = measured


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--problem', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--variant', choices=['baseline', 'target_dims', 'release', 'both'], required=True)
    p.add_argument('--opt-steps', type=int)
    p.add_argument('--grasp-profile')
    args = p.parse_args()
    from experiments.robot.libero.tiptop_repro import real_cutamp_backend as backend
    raw = json.loads(args.problem.read_text())
    if args.opt_steps is not None or args.grasp_profile:
        if args.opt_steps is not None:
            raw['config']['num_opt_steps'] = args.opt_steps
        if args.grasp_profile:
            raw['config']['grasp_sampler_profile'] = args.grasp_profile
        args.problem = args.out_dir.parent / (args.out_dir.name+'.input.json')
        args.problem.write_text(json.dumps(raw))
    problem = backend._problem_from_dict(raw['problem'])
    if args.variant in ['target_dims', 'both']:
        original = backend._cuboid_dims
        def dimensions(obj, cfg):
            if obj.geometry.get('source') == 'rgbd_observed_cuboid':
                return [2*float(v) for v in obj.half_extents]
            return original(obj, cfg)
        backend._cuboid_dims = dimensions
    if args.variant in ['release', 'both']:
        install_release_constraint(backend, problem)
    source = Path(__file__).with_name('diagnose_rgbd_bowl_constraints.py')
    spec = importlib.util.spec_from_file_location('saved_problem_diagnosis', source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from types import SimpleNamespace
    module.worker(SimpleNamespace(problem=args.problem, out_dir=args.out_dir,
        seed=0, variant='baseline', wall_names=[], capture=True))
    (args.out_dir/'ablation.json').write_text(json.dumps(dict(
        variant=args.variant, simulator_created=False, actions_executed=False,
        release_meaning='upright hover pose proximity; not stable contact'), indent=2))


if __name__ == '__main__':
    main()
