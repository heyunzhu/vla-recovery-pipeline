from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp")
for path in root.rglob("*.py"):
    lines = path.read_text(errors="replace").splitlines()
    for i, line in enumerate(lines, 1):
        if "cost_dict" in line or "def get_best_particle" in line or "def optimize" in line:
            print(f"{path.name}:{i}:{line.strip()[:180]}")
