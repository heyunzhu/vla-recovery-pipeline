"""Register the six LIBERO-Pro replay suites before starting the fixed runner."""

from __future__ import annotations

from pathlib import Path

from libero.libero import benchmark, get_libero_path


SUITES = (
    "libero_goal_swap",
    "libero_spatial_task",
    "libero_goal_task",
    "libero_spatial_swap",
    "libero_object_task",
    "libero_object_swap",
)


def _register_suite(suite: str) -> None:
    bddl_dir = Path(get_libero_path("bddl_files")) / suite
    init_dir = Path(get_libero_path("init_states")) / suite
    stems = sorted(path.stem for path in bddl_dir.glob("*.bddl"))
    if len(stems) != 10:
        raise RuntimeError(f"{suite}: expected 10 BDDL tasks, found {len(stems)}")
    missing = [stem for stem in stems if not (init_dir / f"{stem}.pruned_init").is_file()]
    if missing:
        raise RuntimeError(f"{suite}: missing init states for {missing}")

    benchmark.libero_task_map[suite] = stems
    benchmark.task_maps[suite] = {
        stem: benchmark.Task(
            name=stem,
            language=benchmark.grab_language_from_filename(f"{stem}.bddl"),
            problem="Libero",
            problem_folder=suite,
            bddl_file=f"{stem}.bddl",
            init_states_file=f"{stem}.pruned_init",
        )
        for stem in stems
    }

    def __init__(self, task_order_index: int = 0, *, _suite: str = suite) -> None:
        benchmark.Benchmark.__init__(self, task_order_index=task_order_index)
        self.name = _suite
        self._make_benchmark()

    suite_class = type(suite.upper(), (benchmark.Benchmark,), {"__init__": __init__})
    benchmark.BENCHMARK_MAPPING[suite] = suite_class


for _suite in SUITES:
    _register_suite(_suite)

from experiments.robot.libero.skill_pipeline.runner import main, parse_args  # noqa: E402

main(parse_args())
