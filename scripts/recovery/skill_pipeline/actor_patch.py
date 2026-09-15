"""Apply a UTF-8 patch file without PowerShell/Bash quoting. Workdir-local only."""

import argparse
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
import sys


def validate_paths(text: str, root: Path) -> None:
    for line in text.splitlines():
        prefix = next((p for p in ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: ")
                       if line.startswith(p)), None)
        if not prefix:
            continue
        raw = line[len(prefix):].strip()
        windows = PureWindowsPath(raw)
        if not raw or windows.drive or windows.root or PurePosixPath(raw).is_absolute():
            raise ValueError(f"Patch paths must be workdir-relative: {raw}")
        path = root / raw.replace("\\", "/")
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError(f"Patch escapes intervention workdir: {raw}")


def apply_file(patch_file: Path, root: Path, executable: str) -> subprocess.CompletedProcess:
    text = patch_file.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
    validate_paths(text, root)
    return subprocess.run([executable, "--codex-run-as-apply-patch", text], cwd=root,
                          capture_output=True, text=True, encoding="utf-8", timeout=60,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("patch", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    config = json.loads((root / "remote_config.json").read_text(encoding="utf-8"))
    result = apply_file(args.patch, root, config["codex_exe"])
    print(result.stdout, end="")
    print(result.stderr, end="")
    raise SystemExit(result.returncode)
