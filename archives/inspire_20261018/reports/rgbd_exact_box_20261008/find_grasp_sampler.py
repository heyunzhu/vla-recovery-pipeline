from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp")
for name in ("samplers.py", "particle_initialization.py"):
    lines = (root / name).read_text(errors="replace").splitlines()
    print(f"===== {name} =====")
    for i, line in enumerate(lines, 1):
        if "def grasp_6dof" in line or "grasp_6dof_sampler" in line:
            print(f"{i}:{line.strip()[:200]}")
text = (root / "cost_function.py").read_text(errors="replace").splitlines()
print("===== kinematic =====")
for i, line in enumerate(text, 1):
    if "pos_err" in line or "def " in line and "kinematic" in line.lower():
        print(f"{i}:{line.strip()[:220]}")
