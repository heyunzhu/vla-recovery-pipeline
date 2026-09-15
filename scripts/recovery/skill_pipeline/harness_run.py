#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from experiments.robot.libero.skill_pipeline.harness.benchmark_registry import list_benchmarks, load_benchmark
from experiments.robot.libero.skill_pipeline.harness.launcher import HarnessPaths, prepare_run, start_run
from experiments.robot.libero.skill_pipeline.harness.run_spec import load_spec


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser("Prepare or start a persistent LIBERO skill-recovery harness run.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--spec", help="YAML/JSON run spec path.")
    source.add_argument("--benchmark", help="Registered benchmark name or YAML path.")
    parser.add_argument("--list-benchmarks", action="store_true", help="List registered benchmark specs.")
    parser.add_argument("--workspace_root", default=os.environ.get("XINGHANBO_ROOT", "/mnt/nas/gezuhao/xinghanbo"))
    parser.add_argument("--repo_root", default="")
    parser.add_argument("--python_bin", default="")
    parser.add_argument("--log_root", default="")
    parser.add_argument("--libero_config_path", default="")
    parser.add_argument("--libero_pythonpath_root", default="")
    parser.add_argument("--model", default="", help="Override model path/name from the spec.")
    parser.add_argument("--tasks", default="", help="Override task list, e.g. 47-54.")
    parser.add_argument("--gpus", default="", help="Override GPU list, e.g. 0,1,2,3.")
    parser.add_argument("--skill_pack", "--skill-pack", dest="skill_pack", default="", help="Override skill pack from the spec.")
    parser.add_argument("--run_dir", default="", help="Optional explicit run directory.")
    parser.add_argument("--start", action="store_true", help="Actually launch the generated bash script.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.list_benchmarks:
        print("\n".join(list_benchmarks()))
        return
    if not args.spec and not args.benchmark:
        raise SystemExit("Either --spec or --benchmark is required unless --list-benchmarks is used.")
    spec = load_spec(args.spec) if args.spec else load_benchmark(args.benchmark)
    spec = spec.with_overrides(
        tasks=args.tasks or None,
        gpus=args.gpus or None,
        model=args.model or None,
        skill_pack=args.skill_pack or None,
    )
    paths = HarnessPaths.from_workspace(
        args.workspace_root,
        repo_root=args.repo_root or None,
        python_bin=args.python_bin or None,
        log_root=args.log_root or None,
        model=spec.model,
        libero_config_path=args.libero_config_path or None,
        libero_pythonpath_root=args.libero_pythonpath_root or None,
    )
    plan = prepare_run(spec, paths, run_dir=Path(args.run_dir) if args.run_dir else None)
    if args.start:
        plan["launcher_pid"] = start_run(plan["run_dir"])
        plan["started"] = True
    else:
        plan["started"] = False
    print(json.dumps(plan, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
