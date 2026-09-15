"""Rule-based admission checks. First version is not a coordinator agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from .dispatcher import available_backends
from .schema import SkillSchemaError, SkillSpec, validate_skill
from .validate import TriggerMetrics, admission_ok


@dataclass
class CoordinatorReport:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    online_ready: bool = False
    track: str = "pair"
    library: str = "pair"

    def raise_if_invalid(self) -> None:
        if not self.ok:
            raise SkillSchemaError("; ".join(self.errors))


def _library_for(spec: SkillSpec) -> str:
    return "fail_only" if spec.track == "fail_only" else "pair"


def check_draft(
    spec: SkillSpec,
    *,
    backends: Sequence[str] | None = None,
    writing_episodes: Sequence[str] | None = None,
    heldout_metrics: TriggerMetrics | None = None,
    same_init_improved: bool | None = None,
    success_regressed: bool | None = None,
    predicate_registry: object | None = None,
) -> CoordinatorReport:
    errors = list(validate_skill(spec, predicate_registry=predicate_registry))
    warnings: list[str] = []
    known = set(backends if backends is not None else available_backends())
    library = _library_for(spec)
    if spec.kind != "diagnostics":
        if spec.pending_backend:
            warnings.append("backend is pending; cannot go online")
        elif spec.kind != "recovery_hint" and spec.backend not in known:
            errors.append(f"backend not implemented: {spec.backend}")
        evidence_eps = list(spec.evidence.get("episodes") or [])
        if writing_episodes:
            if not evidence_eps:
                errors.append("evidence.episodes is empty")
            elif set(evidence_eps) <= set(writing_episodes) and heldout_metrics is None:
                if spec.track == "fail_only":
                    warnings.append(
                        "fail_only writing episodes are draft evidence only; held-out / same-init required to promote"
                    )
                else:
                    errors.append("writing episodes cannot be the only evidence; held-out metrics required")
        if spec.track == "fail_only":
            warnings.append("fail_only library cannot be loaded by --enable_skills")
        if heldout_metrics is not None or same_init_improved is not None or success_regressed is not None:
            if spec.track != "fail_only" and not admission_ok(
                heldout_metrics,
                same_init_improved=bool(same_init_improved),
                success_regressed=bool(success_regressed),
            ):
                errors.append("held-out / same-init admission thresholds not met")
    ok = not errors
    online_ready = (
        ok
        and spec.kind not in {"diagnostics", "recovery_hint"}
        and spec.track == "pair"
        and not spec.pending_backend
        and spec.backend in known
        and heldout_metrics is not None
        and bool(same_init_improved)
        and not bool(success_regressed)
    )
    return CoordinatorReport(
        ok=ok,
        errors=errors,
        warnings=warnings,
        online_ready=online_ready,
        track=spec.track,
        library=library,
    )
