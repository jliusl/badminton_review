from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class ShuttlePoint:
    time: float
    x: float
    y: float
    confidence: float


@dataclass(frozen=True)
class TrajectoryResult:
    points: tuple[ShuttlePoint, ...]
    coverage: float
    landing_side: str | None
    landing_in_court: bool | None
    confidence: float


def _resolve_court_points(court_points: list[list[float]] | None) -> np.ndarray:
    if court_points and len(court_points) == 4:
        return np.array(court_points, dtype=np.float32)
    return np.array(
        [[0.08, 0.18], [0.92, 0.18], [0.96, 0.96], [0.04, 0.96]],
        dtype=np.float32,
    )


def _candidate_points(
    gray: np.ndarray,
    previous: np.ndarray,
    mask: np.ndarray,
    timestamp: float,
) -> list[tuple[float, float, float]]:
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    diff = cv2.absdiff(blurred, previous)
    _, motion = cv2.threshold(diff, 18, 255, cv2.THRESH_BINARY)
    _, bright = cv2.threshold(blurred, 158, 255, cv2.THRESH_BINARY)
    binary = cv2.bitwise_and(motion, bright)
    binary = cv2.bitwise_and(binary, mask)
    binary = cv2.dilate(binary, np.ones((2, 2), np.uint8), iterations=1)
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    height, width = gray.shape
    candidates: list[tuple[float, float, float]] = []
    for contour in contours:
        area = float(cv2.contourArea(contour))
        if area < 1.4 or area > 95:
            continue
        x, y, w, h = cv2.boundingRect(contour)
        if w > 16 or h > 16 or w <= 0 or h <= 0:
            continue
        if max(w, h) / max(1, min(w, h)) > 4.5:
            continue
        center_x = (x + w / 2) / width
        center_y = (y + h / 2) / height
        roi = blurred[y : y + h, x : x + w]
        mean_brightness = float(roi.mean()) if roi.size else 0.0
        confidence = min(1.0, 0.25 + area / 40.0 + mean_brightness / 510.0)
        candidates.append((center_x, center_y, confidence))
    return candidates


def _match_candidates(
    tracks: list[dict],
    candidates: list[tuple[float, float, float]],
    timestamp: float,
    width: int,
    height: int,
) -> None:
    predicted: list[tuple[float, float]] = []
    for track in tracks:
        misses = track["misses"]
        px = track["x"] + track["vx"] * (1.0 + misses * 0.35)
        py = track["y"] + track["vy"] * (1.0 + misses * 0.35)
        predicted.append((px, py))

    available = set(range(len(candidates)))
    assignments: list[tuple[float, int, int]] = []
    for track_index, (px, py) in enumerate(predicted):
        for candidate_index in available:
            cx, cy, _ = candidates[candidate_index]
            distance = ((cx - px) * width) ** 2 + ((cy - py) * height) ** 2
            if distance <= 42**2:
                assignments.append((distance, track_index, candidate_index))
    assignments.sort(key=lambda item: item[0])

    used_tracks: set[int] = set()
    used_candidates: set[int] = set()
    for _, track_index, candidate_index in assignments:
        if track_index in used_tracks or candidate_index in used_candidates:
            continue
        track = tracks[track_index]
        cx, cy, confidence = candidates[candidate_index]
        old_x, old_y = track["x"], track["y"]
        dt = max(1e-3, timestamp - track["last_time"])
        vx = (cx - old_x) / dt
        vy = (cy - old_y) / dt
        track["vx"] = track["vx"] * 0.55 + vx * 0.45
        track["vy"] = track["vy"] * 0.55 + vy * 0.45
        track["x"] = cx
        track["y"] = cy
        track["last_time"] = timestamp
        track["misses"] = 0
        track["hits"] += 1
        track["path"] += float(np.hypot((cx - old_x) * width, (cy - old_y) * height))
        track["points"].append(ShuttlePoint(timestamp, cx, cy, confidence))
        used_tracks.add(track_index)
        used_candidates.add(candidate_index)

    for track_index, track in enumerate(tracks):
        if track_index not in used_tracks:
            track["misses"] += 1
    for candidate_index, (cx, cy, confidence) in enumerate(candidates):
        if candidate_index not in used_candidates:
            tracks.append(
                {
                    "x": cx,
                    "y": cy,
                    "vx": 0.0,
                    "vy": 0.0,
                    "last_time": timestamp,
                    "misses": 0,
                    "hits": 1,
                    "path": 0.0,
                    "points": [ShuttlePoint(timestamp, cx, cy, confidence)],
                }
            )


def track_shuttle(
    video_path: Path,
    start_time: float,
    end_time: float,
    court_points: list[list[float]] | None = None,
    sample_fps: float = 15.0,
) -> TrajectoryResult:
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return TrajectoryResult((), 0.0, None, None, 0.0)
    source_fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    if width <= 0 or height <= 0:
        capture.release()
        return TrajectoryResult((), 0.0, None, None, 0.0)

    target_width = 480
    scale = target_width / width
    target_height = max(1, int(height * scale))
    polygon = _resolve_court_points(court_points)
    polygon_px = np.array(
        [[int(point[0] * target_width), int(point[1] * target_height)] for point in polygon],
        dtype=np.int32,
    )
    mask = np.zeros((target_height, target_width), dtype=np.uint8)
    cv2.fillPoly(mask, [polygon_px], 255)

    step = max(1, int(round(source_fps / sample_fps)))
    capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, start_time) * 1000)
    previous: np.ndarray | None = None
    tracks: list[dict] = []
    frame_count = 0
    analyzed_frames = 0
    frames_with_candidates = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if timestamp > end_time:
            break
        if frame_count % step != 0:
            frame_count += 1
            continue
        resized = cv2.resize(frame, (target_width, target_height), interpolation=cv2.INTER_AREA)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        analyzed_frames += 1
        if previous is not None:
            candidates = _candidate_points(gray, previous, mask, timestamp)
            if candidates:
                frames_with_candidates += 1
            _match_candidates(tracks, candidates, timestamp, target_width, target_height)
            tracks = [
                track
                for track in tracks
                if track["misses"] <= 5 and track["hits"] >= 1
            ]
        previous = gray
        frame_count += 1
    capture.release()

    if not tracks:
        return TrajectoryResult((), 0.0, None, None, 0.0)
    qualified = [
        track
        for track in tracks
        if track["hits"] >= 3 and track["path"] >= 18.0
    ]
    if not qualified:
        return TrajectoryResult((), 0.0, None, None, 0.0)
    best = max(qualified, key=lambda track: (track["hits"], track["path"]))
    points = tuple(best["points"])
    coverage = float(frames_with_candidates / max(1, analyzed_frames))
    last = points[-1]
    first = points[0]
    vertical_descent = last.y - first.y
    landing_side = None
    landing_in_court = None
    # Only report a landing when the shuttle track is clearly descending. A
    # level track near the ceiling is usually a clear shot, not a landing.
    if vertical_descent >= 0.035 and last.time - first.time >= 0.5:
        if last.y < 0.5:
            landing_side = "top"
        elif last.y > 0.5:
            landing_side = "bottom"
        point_in_polygon = cv2.pointPolygonTest(
            polygon_px,
            (int(last.x * target_width), int(last.y * target_height)),
            False,
        )
        landing_in_court = point_in_polygon >= 0
    confidence = float(
        np.clip(
            0.2
            + min(0.35, best["hits"] / 24.0)
            + min(0.25, best["path"] / 420.0)
            + coverage * 0.2,
            0.0,
            0.95,
        )
    )
    return TrajectoryResult(
        points=points,
        coverage=coverage,
        landing_side=landing_side,
        landing_in_court=landing_in_court,
        confidence=confidence,
    )


def trajectory_suggests_continuation(
    video_path: Path,
    start_time: float,
    end_time: float,
    court_points: list[list[float]] | None = None,
) -> bool:
    result = track_shuttle(video_path, start_time, end_time, court_points, sample_fps=12.0)
    if result.confidence < 0.45 or len(result.points) < 3:
        return False
    first = result.points[0].time
    last = result.points[-1].time
    return (last - first) >= max(0.5, (end_time - start_time) * 0.35)


def infer_winner_from_landing(
    trajectory: TrajectoryResult,
    a_side_at_end: str,
) -> tuple[str, float] | None:
    if (
        trajectory.landing_side is None
        or trajectory.landing_in_court is None
        or trajectory.confidence < 0.55
    ):
        return None
    player_on_landing_side = "A" if trajectory.landing_side == a_side_at_end else "B"
    if trajectory.landing_in_court:
        winner = "B" if player_on_landing_side == "A" else "A"
    else:
        winner = player_on_landing_side
    return winner, min(0.88, trajectory.confidence)