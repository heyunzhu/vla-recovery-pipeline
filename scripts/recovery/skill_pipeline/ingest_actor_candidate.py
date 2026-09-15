"""Apply an actor's pack-local files transactionally, then run normal admission."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import yaml


def write_journal(path: Path, value: dict) -> None:
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value), encoding="utf-8")
    tmp.replace(path)


def recover_transaction(transaction: Path, pack: Path) -> dict:
    journal = transaction / "transaction.json"
    record = json.loads(journal.read_text(encoding="utf-8"))
    if record["status"] != "applying":
        return record
    state_path = Path(record["state_path"])
    state = json.loads(state_path.read_text(encoding="utf-8"))
    task = str(record["task_id"])
    writes = int((state.get("tasks", {}).get(task) or {}).get("writes") or 0)
    if writes == record["writes_before"] + 1 and state.get("awaiting_kind") == "validation":
        record.update(status="committed", output=json.dumps({"ok": True, "recovered": True,
                      "writes_used": writes, "status": "awaiting_validation"}))
    elif writes == record["writes_before"] and state.get("awaiting_kind") == "draft":
        shutil.rmtree(pack)
        shutil.copytree(transaction / "pack_before", pack)
        record.update(status="rolled_back_interruption", output="")
    else:
        raise RuntimeError("Transaction and mining state disagree; refusing to overwrite a newer pack")
    write_journal(journal, record)
    return record


def patch_files(drafts: Path, repo: Path, pack: Path) -> list[tuple[Path, Path, str]]:
    root = drafts / "patch"
    if not root.exists():
        return []
    manifest_path = drafts / "code_patch_manifest.yaml"
    if not manifest_path.is_file():
        raise ValueError("patch/ requires code_patch_manifest.yaml")
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    declared = set(manifest.get("touched_files") or [])
    result = []
    for src in sorted(root.rglob("*")):
        if src.is_symlink():
            raise ValueError(f"Symlinks are not allowed in actor patches: {src}")
        if not src.is_file():
            continue
        rel = src.relative_to(root).as_posix()
        dest = (repo / rel).resolve()
        if not dest.is_relative_to(pack.resolve()):
            raise ValueError(f"Actor patch escapes active pack: {rel}")
        in_pack = dest.relative_to(pack.resolve())
        allowed = (in_pack.parts[0] in {"code", "profiles", "diagnostics", "tests"}
                   or in_pack.as_posix() == "capabilities.yaml")
        if not allowed or src.suffix not in {".py", ".yaml", ".json"}:
            raise ValueError(f"Actor patch cannot replace pack identity/skill index: {rel}")
        if rel not in declared:
            raise ValueError(f"Undeclared actor patch file: {rel}")
        result.append((src, dest, rel))
    return result


def apply_and_ingest(drafts: Path, repo: Path, pack: Path, transaction: Path, argv: list[str]) -> int:
    patches = patch_files(drafts, repo, pack)
    transaction.mkdir(parents=True, exist_ok=True)
    backup = transaction / "pack_before"
    journal = transaction / "transaction.json"
    if journal.exists():
        prior = json.loads(journal.read_text())
        if prior["status"] == "applying":
            prior = recover_transaction(transaction, pack)
        if prior["status"] == "committed":
            print(prior["output"])
            return 0
    if backup.exists():
        raise ValueError("Use a unique transaction directory per admission attempt")
    shutil.copytree(pack, backup)
    base = {rel: dest.read_text(encoding="utf-8") if dest.exists() else "" for _, dest, rel in patches}
    baseline = transaction / "code_base_snapshot.json"
    baseline.write_text(json.dumps(base), encoding="utf-8")
    state_file = Path(argv[argv.index("--out_dir") + 1]) / "mine_state.json" if "--out_dir" in argv else None
    old_state = json.loads(state_file.read_text()) if state_file and state_file.exists() else {}
    task = str(old_state.get("awaiting_task") or "")
    record = {"status": "applying", "pid": os.getpid(), "state_path": str(state_file or ""),
              "task_id": task, "writes_before": int((old_state.get("tasks", {}).get(task) or {}).get("writes") or 0)}
    write_journal(journal, record)
    try:
        for src, dest, _ in patches:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
        extra = ["--code_base_snapshot", str(baseline)] if patches else []
        proc = subprocess.run([sys.executable, str(repo / "scripts/recovery/skill_pipeline/run_skill_mine.py"),
                               *argv, *extra], cwd=repo, capture_output=True, text=True)
        output = (proc.stdout or "") + "\n" + (proc.stderr or "")
        (transaction / "ingest.log").write_text(output, encoding="utf-8")
        if proc.returncode:
            shutil.rmtree(pack)
            shutil.copytree(backup, pack)
        record.update(status="committed" if proc.returncode == 0 else "rolled_back",
                      returncode=proc.returncode, output=output)
        write_journal(journal, record)
        print(output)
        return proc.returncode
    except BaseException:
        # A normal Python exception rolls back. Hard process death leaves the applying receipt.
        if state_file and state_file.exists():
            recover_transaction(transaction, pack)
        else:
            shutil.rmtree(pack)
            shutil.copytree(backup, pack)
            write_journal(journal, {"status": "rolled_back_exception"})
        raise


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--skill_pack", required=True)
    parser.add_argument("--draft_dir", required=True, type=Path)
    parser.add_argument("--out_dir", required=True, type=Path)
    parser.add_argument("--recover_transaction", action="store_true")
    args, _ = parser.parse_known_args()
    repo = Path(__file__).resolve().parents[3]
    pack = (repo / "skill_packs" / args.skill_pack).resolve()
    if not pack.is_relative_to(repo / "skill_packs") or not pack.is_dir():
        raise ValueError("Expected an existing isolated pack under this repository")
    transaction = args.draft_dir.parent / "admission_transaction"
    if args.recover_transaction:
        print(json.dumps(recover_transaction(transaction, pack)))
        return
    raise SystemExit(apply_and_ingest(args.draft_dir, repo, pack, transaction, sys.argv[1:]))


if __name__ == "__main__":
    main()
