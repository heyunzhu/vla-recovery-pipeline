from pathlib import Path
path = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp/constraint_checker.py")
lines = path.read_text(errors="replace").splitlines()
for i, line in enumerate(lines, 1):
    if "satisfying" in line or "remaining" in line or "def " in line:
        print(f"{i}:{line}")
