from __future__ import annotations

from pathlib import Path

from .run_spec import HarnessSpec, load_spec


BENCHMARK_DIR = Path(__file__).resolve().parent / "benchmarks"


def list_benchmarks() -> list[str]:
    if not BENCHMARK_DIR.exists():
        return []
    return sorted(path.stem for path in BENCHMARK_DIR.glob("*.yaml"))


def benchmark_path(name_or_path: str | Path) -> Path:
    raw = Path(name_or_path)
    if raw.exists():
        return raw
    if raw.suffix:
        candidate = BENCHMARK_DIR / raw.name
    else:
        candidate = BENCHMARK_DIR / f"{raw.name}.yaml"
    if candidate.exists():
        return candidate
    names = ", ".join(list_benchmarks()) or "(none)"
    raise FileNotFoundError(f"unknown harness benchmark {name_or_path!r}; available: {names}")


def load_benchmark(name_or_path: str | Path) -> HarnessSpec:
    return load_spec(benchmark_path(name_or_path))
