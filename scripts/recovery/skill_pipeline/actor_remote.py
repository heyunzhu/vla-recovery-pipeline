"""Stable SSH transport for Windows actors. Python scripts travel over stdin."""

import argparse
import base64
import json
import os
from pathlib import Path, PurePosixPath
import shlex
import subprocess
import sys
import uuid


def bounded(path: str, root: str) -> str:
    p = PurePosixPath(path)
    if ".." in p.parts or not p.is_relative_to(root):
        raise ValueError("Remote path is outside the authorized workspace")
    return str(p)


def ssh_args(config: dict) -> list[str]:
    return ["ssh", "-p", config["port"], "-i", config["key"], "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=no", "-o", "ConnectTimeout=15", "-o", "ServerAliveInterval=15",
            "-o", "ServerAliveCountMax=3", "root@" + config["host"]]


def main():
    parser = argparse.ArgumentParser(__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    read = sub.add_parser("read")
    read.add_argument("path")
    read.add_argument("--start", type=int, default=1)
    read.add_argument("--lines", type=int, default=160)
    listing = sub.add_parser("list")
    listing.add_argument("path")
    download = sub.add_parser("get")
    download.add_argument("path")
    download.add_argument("output", type=Path)
    script = sub.add_parser("script")
    script.add_argument("file", type=Path)
    script.add_argument("--planning", action="store_true")
    script.add_argument("--timeout", type=int, default=300)
    for name in ("probe-recovery", "check-drafts"):
        command = sub.add_parser(name)
        command.add_argument("--draft-dir", type=Path)
        command.add_argument("--timeout", type=int, default=900)
        if name == "probe-recovery":
            command.add_argument("--seed", type=int, required=True)
            command.add_argument("--query", type=int, required=True)
            command.add_argument("--task", type=int)
            command.add_argument("--dry-run", action="store_true")
            command.add_argument("--preflight-only", action="store_true")
    args = parser.parse_args()
    config = json.loads(Path(__file__).with_name("remote_config.json").read_text(encoding="utf-8"))
    env = config["env"]
    exports = "; ".join("export " + k + "=" + shlex.quote(v) for k, v in env.items())
    python = config["python"]
    if args.action in {"probe-recovery", "check-drafts"}:
        tool = config["probe_tool"]
        run = bounded(config["run_root"], config["root"])
        argv = [tool, "--run-root", run, "--timeout", str(args.timeout)]
        if args.action == "check-drafts":
            argv.append("--check-only")
        else:
            argv += ["--seed", str(args.seed), "--query", str(args.query)]
            if args.task is not None:
                argv += ["--task", str(args.task)]
            for flag in ("dry_run", "preflight_only"):
                if getattr(args, flag):
                    argv.append("--" + flag.replace("_", "-"))
        files = {}
        dest = f"{run}/mine/probe_inputs/{uuid.uuid4().hex}/drafts"
        if args.draft_dir:
            local = args.draft_dir.resolve()
            if not local.is_relative_to(Path(__file__).parent.resolve()) or not local.is_dir():
                raise ValueError("Draft input must be a directory under this intervention workdir")
            for p in sorted(local.rglob("*")):
                if p.is_symlink():
                    raise ValueError("Draft upload does not accept symlinks")
                if p.is_file():
                    files[p.relative_to(local).as_posix()] = base64.b64encode(p.read_bytes()).decode("ascii")
            argv += ["--draft-dir", dest]
        program = ("import base64,sys,runpy\nfrom pathlib import Path\n"
                   f"files={files!r}\nroot=Path({dest!r})\n"
                   "for name,data in files.items():\n"
                   "    p=root/name; p.parent.mkdir(parents=True,exist_ok=True); p.write_bytes(base64.b64decode(data))\n"
                   f"sys.path.insert(0,{str(PurePosixPath(tool).parent)!r})\nsys.argv={argv!r}\n"
                   f"runpy.run_path({tool!r},run_name='__main__')\n")
    elif args.action == "script":
        program = args.file.read_text(encoding="utf-8")
        if args.planning:
            python = config["planner"]
    else:
        path = bounded(args.path, config["root"])
        if args.action == "read":
            program = ("from pathlib import Path\n"
                       f"lines=Path({path!r}).read_text(errors='replace').splitlines()\n"
                       f"print('\\n'.join(f'{{i+1}}: {{line}}' for i,line in enumerate(lines) "
                       f"if {max(0,args.start-1)} <= i < {max(0,args.start-1)+args.lines}))\n")
        elif args.action == "list":
            program = f"from pathlib import Path\nprint('\\n'.join(str(p) for p in sorted(Path({path!r}).iterdir())))\n"
        else:
            program = f"from pathlib import Path\nimport sys\nsys.stdout.buffer.write(Path({path!r}).read_bytes())\n"
    command = exports + "; " + shlex.quote(python) + " -"
    done = subprocess.run([*ssh_args(config), command], input=program.encode("utf-8"), capture_output=True,
                          timeout=getattr(args, "timeout", 180) + (180 if args.action in {"probe-recovery", "check-drafts"} else 0),
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0)
    if args.action == "get" and done.returncode == 0:
        output = args.output.resolve()
        if not output.is_relative_to(Path(__file__).parent.resolve()):
            raise ValueError("Downloads belong in this intervention's work directory")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(done.stdout)
        print(str(output))
    else:
        sys.stdout.buffer.write(done.stdout)
    sys.stderr.buffer.write(done.stderr)
    raise SystemExit(done.returncode)


if __name__ == "__main__":
    main()
