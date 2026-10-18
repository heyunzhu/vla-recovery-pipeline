from pathlib import Path
root = Path("/inspire/hdd/project/feelingai/chenwenming-25012/jxs/xinghanbo/third_party/cuTAMP")
hits = []
for path in root.rglob("*.py"):
    text = path.read_text(errors="replace")
    if "satisfying" in text and "remaining" in text:
        hits.append(str(path))
print("\n".join(hits))
