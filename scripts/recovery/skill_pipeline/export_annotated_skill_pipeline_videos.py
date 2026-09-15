"""Overlay query and recovery markers on skill-pipeline episode videos."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


@dataclass
class RecoverySegment:
    start: int
    end: int
    query_idx: int
    skill_id: str
    terminal: str


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def read_video(path: Path) -> tuple[list[np.ndarray], float]:
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    frames: list[np.ndarray] = []
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
    cap.release()
    if not frames:
        raise RuntimeError(f"No frames in video: {path}")
    return frames, float(fps)


def load_query_image(ep_dir: Path, query_idx: int) -> np.ndarray | None:
    path = ep_dir / "frames" / f"q{int(query_idx):04d}_agentview.jpg"
    if not path.exists():
        return None
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    return img


def resize_like(img: np.ndarray, shape: tuple[int, int, int]) -> np.ndarray:
    h, w = shape[:2]
    if img.shape[:2] == (h, w):
        return img
    return cv2.resize(img, (w, h), interpolation=cv2.INTER_AREA)


def frame_distance(a: np.ndarray, b: np.ndarray) -> float:
    a_small = cv2.resize(a, (64, 64), interpolation=cv2.INTER_AREA)
    b_small = cv2.resize(b, (64, 64), interpolation=cv2.INTER_AREA)
    return float(np.mean(np.abs(a_small.astype(np.float32) - b_small.astype(np.float32))))


def match_frame(
    frames: list[np.ndarray],
    target: np.ndarray | None,
    lo: int,
    hi: int,
    fallback: int,
) -> tuple[int, float | None]:
    if target is None:
        return int(np.clip(fallback, 0, len(frames) - 1)), None
    lo = max(0, int(lo))
    hi = min(len(frames), int(hi))
    if lo >= hi:
        return int(np.clip(fallback, 0, len(frames) - 1)), None
    target = resize_like(target, frames[0].shape)
    best_idx = lo
    best_dist = float("inf")
    for idx in range(lo, hi):
        dist = frame_distance(frames[idx], target)
        if dist < best_dist:
            best_dist = dist
            best_idx = idx
    return best_idx, best_dist


def terminal_from_recovery(rows: list[dict[str, Any]]) -> str:
    errors: list[str] = []
    for row in rows:
        err = str(row.get("error") or "")
        if err and err not in errors:
            errors.append(err)
    if errors:
        return "; ".join(errors[-2:])
    if any(row.get("event") == "place_open" for row in rows):
        return "place_open"
    if any(row.get("event") == "goal_satisfied_after_step" for row in rows):
        return "goal_satisfied_after_step"
    return "no_recovery_trace" if not rows else "recovery_trace_without_terminal_error"


def detect_recovery_segment(
    ep_dir: Path,
    frames: list[np.ndarray],
    queries: list[dict[str, Any]],
    recovery_rows: list[dict[str, Any]],
    *,
    num_steps_wait: int,
    max_search_after_start: int,
) -> tuple[list[RecoverySegment], dict[int, int]]:
    positions: dict[int, int] = {}
    rec_pos = next((idx for idx, row in enumerate(queries) if row.get("mode") == "recovery"), None)
    if rec_pos is None:
        for row in queries:
            q = int(row.get("query_idx", 0))
            positions[q] = int(np.clip(int(row.get("env_step", num_steps_wait)) - num_steps_wait, 0, len(frames) - 1))
        return [], positions

    rec_row = queries[rec_pos]
    rec_q = int(rec_row.get("query_idx", rec_pos))
    start_guess = int(rec_row.get("env_step", num_steps_wait)) - num_steps_wait
    start_img = load_query_image(ep_dir, rec_q)
    start, _ = match_frame(frames, start_img, start_guess - 6, start_guess + 7, start_guess)

    end = len(frames) - 1
    callback_offset = 0
    if rec_pos + 1 < len(queries):
        next_row = queries[rec_pos + 1]
        next_q = int(next_row.get("query_idx", rec_q + 1))
        next_img = load_query_image(ep_dir, next_q)
        search_hi = min(len(frames), start + max_search_after_start)
        next_pos, _ = match_frame(frames, next_img, start + 1, search_hi, start + 1)
        end = max(start, next_pos - 1)
        next_base = int(next_row.get("env_step", num_steps_wait)) - num_steps_wait
        callback_offset = max(0, next_pos - next_base)
    else:
        callback_offset = max(0, end - start)

    for idx, row in enumerate(queries):
        q = int(row.get("query_idx", idx))
        base = int(row.get("env_step", num_steps_wait)) - num_steps_wait
        pos = base if idx <= rec_pos else base + callback_offset
        positions[q] = int(np.clip(pos, 0, len(frames) - 1))

    skill_id = str(rec_row.get("skill_id") or "")
    terminal = terminal_from_recovery(recovery_rows)
    return [RecoverySegment(start=start, end=end, query_idx=rec_q, skill_id=skill_id, terminal=terminal)], positions


def last_query_for_frame(frame_idx: int, queries: list[dict[str, Any]], positions: dict[int, int]) -> dict[str, Any] | None:
    best: dict[str, Any] | None = None
    best_pos = -1
    for row in queries:
        q = int(row.get("query_idx", 0))
        pos = positions.get(q)
        if pos is not None and pos <= frame_idx and pos >= best_pos:
            best = row
            best_pos = pos
    return best


def put_text(img: np.ndarray, text: str, org: tuple[int, int], *, scale: float, color: tuple[int, int, int], thickness: int = 1) -> None:
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 2, cv2.LINE_AA)
    cv2.putText(img, text, org, cv2.FONT_HERSHEY_SIMPLEX, scale, color, thickness, cv2.LINE_AA)


def overlay_box(img: np.ndarray, top: int, bottom: int, color: tuple[int, int, int], alpha: float) -> None:
    overlay = img.copy()
    cv2.rectangle(overlay, (0, top), (img.shape[1], bottom), color, -1)
    cv2.addWeighted(overlay, alpha, img, 1.0 - alpha, 0, img)


def short(value: Any, max_len: int = 36) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= max_len else text[: max_len - 3] + "..."


def annotate_frame(
    frame: np.ndarray,
    frame_idx: int,
    total_frames: int,
    fps: float,
    episode: dict[str, Any],
    queries: list[dict[str, Any]],
    positions: dict[int, int],
    segments: list[RecoverySegment],
) -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]
    active = next((seg for seg in segments if seg.start <= frame_idx <= seg.end), None)
    query = last_query_for_frame(frame_idx, queries, positions) or {}
    success = "SUCCESS" if episode.get("success") else "FAIL"
    rec_count = int(episode.get("recovery_calls") or 0)

    overlay_box(img, 0, 108, (0, 0, 0), 0.60)
    status_color = (80, 255, 80) if episode.get("success") else (80, 180, 255)
    mode = "RECOVERY ACTIVE" if active else ("NO RECOVERY TRIGGERED" if rec_count == 0 else "VLA")
    mode_color = (0, 80, 255) if active else ((0, 255, 255) if rec_count == 0 else (255, 255, 255))
    small = 0.34 if w <= 320 else 0.45
    mid = 0.42 if w <= 320 else 0.55

    now_s = frame_idx / max(fps, 1e-6)
    total_s = max(0.0, (total_frames - 1) / max(fps, 1e-6))
    title = (
        f"T{episode.get('task_id_1based')} ep{episode.get('episode_idx'):02d} {success}  "
        f"f{frame_idx + 1}/{total_frames}  t={now_s:.1f}/{total_s:.1f}s"
    )
    put_text(img, title, (8, 17), scale=mid, color=status_color, thickness=1)
    put_text(img, f"q={query.get('query_idx', '')}  mode={mode}", (8, 36), scale=small, color=mode_color, thickness=1)
    put_text(img, f"target={short(query.get('target_name'), 31)}", (8, 54), scale=small, color=(235, 235, 235), thickness=1)
    if query:
        put_text(
            img,
            f"ap={float(query.get('gripper_aperture') or 0.0):.4f}  cmd={float(query.get('gripper_cmd') or 0.0):+.3f}",
            (8, 72),
            scale=small,
            color=(235, 235, 235),
            thickness=1,
        )
    put_text(img, f"holding={short(query.get('holding_status'), 28)}", (8, 90), scale=small, color=(235, 235, 235), thickness=1)

    if active:
        rline = f"skill={short(active.skill_id, 26)}"
    elif rec_count == 0:
        rline = "recovery did not fire in this episode"
    else:
        rline = "outside recovery period"
    put_text(img, rline, (8, 106), scale=small, color=mode_color, thickness=1)

    if active:
        overlay_box(img, h - 58, h, (0, 0, 180), 0.45)
        cv2.rectangle(img, (2, 2), (w - 3, h - 3), (0, 0, 255), 5)
        put_text(img, "RECOVERY ACTIVE", (8, h - 29), scale=0.76 if w <= 320 else 0.9, color=(0, 255, 255), thickness=2)
        put_text(
            img,
            (
                f"q={active.query_idx} frames {active.start + 1}-{active.end + 1}  "
                f"t={active.start / max(fps, 1e-6):.1f}-{active.end / max(fps, 1e-6):.1f}s  "
                f"dur={(active.end - active.start + 1) / max(fps, 1e-6):.1f}s"
            ),
            (8, h - 9),
            scale=small,
            color=(255, 255, 255),
            thickness=1,
        )

    bar_y = h - 6
    cv2.rectangle(img, (0, bar_y), (w - 1, h - 1), (70, 70, 70), -1)
    for seg in segments:
        x0 = int(w * seg.start / max(1, total_frames - 1))
        x1 = int(w * seg.end / max(1, total_frames - 1))
        cv2.rectangle(img, (x0, bar_y), (max(x1, x0 + 2), h - 1), (0, 0, 255), -1)
    x = int(w * frame_idx / max(1, total_frames - 1))
    cv2.line(img, (x, bar_y - 5), (x, h - 1), (255, 255, 255), 1)
    return img


def export_episode(
    run_dir: Path,
    ep_dir: Path,
    out_dir: Path,
    *,
    num_steps_wait: int,
    max_search_after_start: int,
) -> dict[str, Any]:
    episode = json.loads((ep_dir / "episode.json").read_text(encoding="utf-8"))
    queries = read_jsonl(ep_dir / "query_trace.jsonl")
    recovery_rows = read_jsonl(ep_dir / "recovery_trace.jsonl")
    frames, fps = read_video(ep_dir / "video.mp4")
    segments, positions = detect_recovery_segment(
        ep_dir,
        frames,
        queries,
        recovery_rows,
        num_steps_wait=num_steps_wait,
        max_search_after_start=max_search_after_start,
    )

    rel = ep_dir.relative_to(run_dir)
    target_dir = out_dir / rel
    target_dir.mkdir(parents=True, exist_ok=True)
    out_path = target_dir / "video_annotated_recovery.mp4"
    h, w = frames[0].shape[:2]
    writer = cv2.VideoWriter(str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))
    if not writer.isOpened():
        raise RuntimeError(f"Could not open output writer: {out_path}")
    for idx, frame in enumerate(frames):
        writer.write(annotate_frame(frame, idx, len(frames), fps, episode, queries, positions, segments))
    writer.release()

    return {
        "episode": str(rel).replace("\\", "/"),
        "output": str(out_path),
        "success": bool(episode.get("success")),
        "recovery_calls": int(episode.get("recovery_calls") or 0),
        "fps": fps,
        "segments": [
            {
                **seg.__dict__,
                "start_s": seg.start / max(fps, 1e-6),
                "end_s": seg.end / max(fps, 1e-6),
                "duration_s": (seg.end - seg.start + 1) / max(fps, 1e-6),
            }
            for seg in segments
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--num-steps-wait", type=int, default=10)
    parser.add_argument("--max-search-after-start", type=int, default=260)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict[str, Any]] = []
    for ep_json in sorted(args.run_dir.glob("*/ep*/episode.json")):
        summaries.append(
            export_episode(
                args.run_dir,
                ep_json.parent,
                args.out_dir,
                num_steps_wait=args.num_steps_wait,
                max_search_after_start=args.max_search_after_start,
            )
        )
    (args.out_dir / "index.json").write_text(json.dumps(summaries, indent=2), encoding="utf-8")
    print(json.dumps({"episodes": len(summaries), "out_dir": str(args.out_dir)}, indent=2))


if __name__ == "__main__":
    main()
