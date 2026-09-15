"""Check draft skills with the existing parser, static gates and runtime registries.

All edits and checks happen on a disposable copy under the caller's probe directory.
This never ingests skills, edits the active index or scores a mining write.
"""

from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import yaml
from ingest_actor_candidate import patch_files


def prepare_candidate(repo: Path, pack: Path, drafts: Path | None, output: Path) -> Path:
    candidate = output / "candidate_repo" / "skill_packs" / pack.name
    candidate.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(pack, candidate, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    if drafts is None:
        return candidate
    for source, destination, _ in patch_files(drafts, repo, pack):
        target = candidate / destination.relative_to(pack.resolve())
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    from experiments.robot.libero.skill_pipeline.bundles import load_skill_bundle
    from experiments.robot.libero.skill_pipeline.predicate_registry import load_predicate_registry
    index = candidate / "skills/_index.yaml"
    predicates = load_predicate_registry(index_path=index)
    bundle = load_skill_bundle(draft_dir=drafts, predicate_registry=predicates)
    data = yaml.safe_load(index.read_text(encoding="utf-8")) or {}
    for draft in bundle.drafts:
        if not draft.path.resolve().is_relative_to(drafts.resolve()):
            raise ValueError("Draft file escapes bundle directory")
        name = f"fail_only/candidate/{draft.spec.id}.md"
        # A revision replaces the same id in this temporary index instead of loading it twice.
        from experiments.robot.libero.skill_pipeline.schema import load_skill
        for key in ("online", "fail_only"):
            data[key] = [rel for rel in data.get(key, [])
                         if load_skill(index.parent / rel, predicate_registry=predicates).id != draft.spec.id]
        dest = index.parent / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(draft.path, dest)
        data.setdefault("fail_only", []).append(name)
    index.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return candidate


def check_candidate(repo: Path, candidate: Path, drafts: Path | None, output: Path,
                    active_pack: Path) -> dict:
    sys.path.insert(0, str(repo))
    from experiments.robot.libero.skill_pipeline.schema import resolve_mining_skills
    from experiments.robot.libero.skill_pipeline.runtime import SkillRuntime
    from experiments.robot.libero.skill_pipeline.coordinator import check_draft
    from experiments.robot.libero.skill_pipeline.admission import _run_static_gate
    from experiments.robot.libero.skill_pipeline.pack_code_check import check_pack_code
    errors, warnings, rows = [], [], []
    index = candidate / "skills/_index.yaml"
    runtime = SkillRuntime.from_index(index)
    specs = resolve_mining_skills(index, predicate_registry=runtime.predicate_registry)
    code = check_pack_code(pack_root=candidate)
    if not code.get("ok"):
        errors.append("pack_code_check failed; see pack_code report")
    admission = None
    if drafts and (drafts / "code_patch_manifest.yaml").is_file():
        from experiments.robot.libero.skill_pipeline.code_admission import CodeAdmissionConfig, run_code_admission
        replacements = patch_files(drafts, repo, active_pack)
        base = {rel: dest.read_text(encoding="utf-8") if dest.exists() else "" for _, dest, rel in replacements}
        admission = run_code_admission(CodeAdmissionConfig(
            repo_root=candidate.parents[1], pack_root=candidate, out_dir=output / "code_admission",
            manifest_path=drafts / "code_patch_manifest.yaml", index_path=index,
            skill_files=[s.path for s in specs], changed_files=list(base), base_file_texts=base))
        errors.extend(admission.get("errors") or [])
    for spec in specs:
        row = {"id": spec.id, "kind": spec.kind, "scope": spec.scope}
        try:
            coordinator = check_draft(spec, predicate_registry=runtime.predicate_registry)
            errors.extend(f"{spec.id}: {e}" for e in coordinator.errors)
            audit = runtime.capability_registry.audit_skill(spec)
            errors.extend(f"{spec.id}: {e}" for e in audit.errors)
            # Same expansion/gate path used by runtime; catch missing underlying executor keys.
            hints = runtime._expand_named_profiles(spec.recovery_hints)
            hints = runtime._attach_grasp_profile_adapter(hints)
            runtime._apply_capability_gate(hints)
            dest = output / spec.id
            dest.mkdir(parents=True, exist_ok=True)
            static, errs, warns = _run_static_gate(spec=spec, skill_file=spec.path,
                index_path=index, out_dir=dest, predicate_registry=runtime.predicate_registry)
            errors.extend(f"{spec.id}: {e}" for e in errs)
            warnings.extend(f"{spec.id}: {w}" for w in warns)
            row.update(expanded_hints=hints, static=static)
        except Exception as exc:
            errors.append(f"{spec.id}: {type(exc).__name__}: {exc}")
        rows.append(row)
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "skills": rows, "pack_code": code, "code_admission": admission,
            "candidate_pack": str(candidate), "offline_scan_run": False,
            "note": "Precheck only. Global offline scan and formal validation still run at admission."}
