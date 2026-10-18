import os
os.environ.setdefault("MUJOCO_GL", "egl")
from libero.libero import benchmark
for suite_name in ("libero_spatial", "libero_object", "libero_goal"):
    suite = benchmark.get_benchmark_dict()[suite_name]()
    print("SUITE", suite_name, suite.n_tasks)
    for i in range(suite.n_tasks):
        task = suite.get_task(i)
        print(f"{i}\t{task.language}")
