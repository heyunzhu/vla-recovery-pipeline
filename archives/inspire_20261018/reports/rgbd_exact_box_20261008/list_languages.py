import os
import sys
sys.path.insert(0, "/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo/LIBERO-PRO")
os.environ["LIBERO_CONFIG_PATH"] = "/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/logs/rgbd_exact_box_20261008/libero_config"
os.environ["LIBERO_PYTHONPATH_ROOT"] = "/inspire/ssd/project/feelingai/chenwenming-25012/jxs/xinghanbo/LIBERO-PRO"
from libero.libero.benchmark import get_benchmark
for suite in ("libero_goal", "libero_object", "libero_spatial"):
    bench = get_benchmark(suite)()
    print("====", suite, bench.n_tasks)
    for i in range(bench.n_tasks):
        print(i, bench.get_task(i).language)
