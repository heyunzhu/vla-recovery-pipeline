from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp")
for name, start, end in (
    ("optimize_plan.py", 120, 240),
    ("cost_function.py", 1, 80),
):
    lines = (root / name).read_text(errors="replace").splitlines()
    print(f"===== {name} =====")
    for i in range(start - 1, min(end, len(lines))):
        print(f"{i+1}:{lines[i]}")
print("===== collision names =====")
text = (root / "cost_function.py").read_text(errors="replace").splitlines()
for i, line in enumerate(text, 1):
    if "robot_to_movables" in line or "pos_err" in line or "in_xy" in line:
        print(f"{i}:{line.strip()[:200]}")
