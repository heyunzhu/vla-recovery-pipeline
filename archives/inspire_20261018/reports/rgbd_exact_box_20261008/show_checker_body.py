from pathlib import Path
path = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP/cutamp/constraint_checker.py")
lines = path.read_text(errors="replace").splitlines()
for i in range(45, 95):
    print(f"{i+1}:{lines[i]}")
