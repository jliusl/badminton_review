from __future__ import annotations

import json
import math
import re
import subprocess
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

import cv2
import numpy as np

from .config import FFMPEG
from .trajectory import infer_winner_from_landing, track_shuttle

ProgressCallback = Callable[[float, str], None]


@dataclass(frozen=True)
class VideoInfo:
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str | None
    has_audio: bool


@dataclass(frozen=True)
class DetectedRally:
    start_time: float
    end_time: float
    confidence: float
    hit_count: int


DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
VIDEO_RE = re.compile(r"Video:\s*([^,\s]+).*?(\d{2,5})x(\d{2,5}).*?([\d.]+)\s*fps", re.I)
AUDIO_RE = re.compile(r"Audio:\s*([^,\s]+)", re.I)


def _stderr_text(result: subprocess.CompletedProcess[bytes]) -> str:
    return result.stderr.decode("utf-8", errors="replace")


def ffmpeg_version() -> str:
    result = subprocess.run(
        [FFMPEG, "-version"], capture_output=True, check=False
    )
    output = (result.stdout or b"") + (result.stderr or b"")
    text = output.decode("utf-8", errors="replace")
    return text.splitlines()[0] if text else "ffmpeg"


def probe_video(path: Path) -> VideoInfo:
    if not path.exists():
        raise FileNotFoundError(f"视频不存在：{path}")
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path)],
        capture_output=True,
        check=False,
    )
    text = _stderr_text(result)
    duration_match = DURATION_RE.search(text)
    if not duration_match:
        raise ValueError("无法读取视频时长，请确认文件是有效视频")
    hours, minutes, seconds = duration_match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    duration_line = next((line for line in text.splitlines() if "Duration:" in line), "")
    info_text = text[duration_line.find("Duration:") :] if duration_line else text
    video_match = VIDEO_RE.search(info_text)
    if not video_match:
        raise ValueError("无法读取视频分辨率或帧率")
    codec, width, height, fps = video_match.groups()
    audio_match = AUDIO_RE.search(text)
    audio_codec = audio_match.group(1).lower() if audio_match else None
    return VideoInfo(
        duration=duration,
        width=int(width),
        height=int(height),
        fps=float(fps),
        video_codec=codec.lower(),
        audio_codec=audio_codec,
        has_audio=audio_codec is not None,
    )


def _parse_timestamp(value: str) -> float:
    try:
        hours, minutes, seconds = value.split(":")
        return int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except Exception:
        return 0.0


def run_ffmpeg_with_progress(
    args: list[str],
    duration: float,
    on_progress: ProgressCallback | None = None,
    stage: str = "处理视频",
    cwd: Path | None = None,
) -> None:
    command = [FFMPEG, "-hide_banner", "-y", *args, "-progress", "pipe:1", "-nostats"]
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", errors="replace") as error_file:
        process = subprocess.Popen(
            command,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=error_file,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if not line or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key in {"out_time_us", "out_time_ms"}:
                try:
                    seconds = int(value) / 1_000_000
                    if on_progress and duration > 0:
                        on_progress(min(0.99, seconds / duration), stage)
                except ValueError:
                    pass
        return_code = process.wait()
        error_file.seek(0)
        stderr = error_file.read()
    if return_code != 0:
        tail = "\n".join(stderr.splitlines()[-12:])
        raise RuntimeError(f"FFmpeg 执行失败：{tail}")

def create_preview(
    source: Path,
    output: Path,
    info: VideoInfo,
    on_progress: ProgressCallback | None = None,
) -> Path:
    if info.video_codec in {"h264", "avc1"} and "mp4" in source.suffix.lower():
        return source
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i",
        str(source),
        "-map",
        "0:v:0",
        "-map",
        "0:a:0?",
        "-vf",
        "scale='min(1280,iw)':-2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output),
    ]
    run_ffmpeg_with_progress(args, info.duration, on_progress, "生成浏览器预览")
    return output


def create_thumbnail(video: Path, output: Path, duration: float) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    timestamp = min(max(duration * 0.12, 1.0), max(duration - 0.5, 1.0))
    args = [
        "-ss",
        f"{timestamp:.3f}",
        "-i",
        str(video),
        "-frames:v",
        "1",
        "-vf",
        "scale=640:-2",
        "-q:v",
        "3",
        str(output),
    ]
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-y", *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("生成视频缩略图失败")
    return output


def extract_analysis_audio(video: Path, output: Path) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    args = [
        "-i",
        str(video),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-af",
        "highpass=f=1400,lowpass=f=8500",
        "-f",
        "wav",
        str(output),
    ]
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-y", *args],
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError("提取分析音频失败，视频可能没有音轨")
    return output


def _read_wave(path: Path) -> tuple[np.ndarray, int]:
    with wave.open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        channels = wav.getnchannels()
        sample_width = wav.getsampwidth()
        raw = wav.readframes(wav.getnframes())
    if sample_width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif sample_width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise ValueError("暂不支持该音频采样格式")
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, sample_rate


def _moving_average(values: np.ndarray, width: int) -> np.ndarray:
    if width <= 1:
        return values
    kernel = np.ones(width, dtype=np.float32) / width
    return np.convolve(values, kernel, mode="same")


def _window_motion(
    capture: cv2.VideoCapture,
    start: float,
    end: float,
    duration: float,
    court_points: list[list[float]] | None,
) -> float:
    start = max(0.0, start)
    end = min(duration, end)
    if end - start < 0.35:
        return 0.0
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    sample_interval = max(1, int(round(fps * 0.20)))
    polygon = None
    if court_points and len(court_points) == 4:
        polygon = np.array(
            [[int(point[0] * 240), int(point[1] * 136)] for point in court_points],
            dtype=np.int32,
        )
    mask = np.zeros((136, 240), dtype=np.uint8)
    if polygon is None:
        mask[:, :] = 255
    else:
        cv2.fillPoly(mask, [polygon], 255)

    capture.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    previous: np.ndarray | None = None
    scores: list[float] = []
    frame_index = 0
    while True:
        ok, frame = capture.read()
        if not ok:
            break
        timestamp = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
        if timestamp > end:
            break
        if frame_index % sample_interval == 0:
            gray = cv2.resize(
                cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY),
                (240, 136),
                interpolation=cv2.INTER_AREA,
            )
            if previous is not None:
                diff = cv2.absdiff(gray, previous)
                _, diff = cv2.threshold(diff, 20, 255, cv2.THRESH_BINARY)
                diff = cv2.bitwise_and(diff, mask)
                scores.append(float(np.count_nonzero(diff)))
            previous = gray
        frame_index += 1
    return float(np.mean(scores)) if scores else 0.0


def _merge_visually_continuous_groups(
    groups: list[list[tuple[float, float]]],
    duration: float,
    video_path: Path | None,
    court_points: list[list[float]] | None,
) -> list[list[tuple[float, float]]]:
    if len(groups) < 2 or video_path is None:
        return groups
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return groups

    merged: list[list[tuple[float, float]]] = []
    current = list(groups[0])
    for next_group in groups[1:]:
        last_hit = current[-1][0]
        next_hit = next_group[0][0]
        gap = next_hit - last_hit
        should_merge = False
        # Merge a medium audio gap only when the players remain at least as
        # active as in the adjacent rally segments. Longer gaps are treated as
        # dead-ball intervals rather than risking unrelated rallies being merged.
        if 4.0 <= gap <= 5.2:
            gap_motion = _window_motion(
                capture, last_hit + 0.3, next_hit - 0.3, duration, court_points
            )
            previous_motion = _window_motion(
                capture, max(0.0, last_hit - 1.3), last_hit + 0.2, duration, court_points
            )
            next_motion = _window_motion(
                capture, next_hit - 0.2, next_hit + 1.3, duration, court_points
            )
            active_reference = max(previous_motion, next_motion, 1.0)
            should_merge = gap_motion >= 1200.0 and gap_motion >= active_reference
        if should_merge:
            current.extend(next_group)
        else:
            merged.append(current)
            current = list(next_group)
    merged.append(current)
    capture.release()
    return merged


def detect_rallies_from_audio(
    wav_path: Path,
    duration: float,
    on_progress: ProgressCallback | None = None,
    video_path: Path | None = None,
    court_points: list[list[float]] | None = None,
) -> list[DetectedRally]:
    samples, sample_rate = _read_wave(wav_path)
    if samples.size == 0:
        return []

    frame = max(1, int(sample_rate * 0.010))
    hop = max(1, int(sample_rate * 0.005))
    if samples.size < frame:
        return []
    windows = np.lib.stride_tricks.sliding_window_view(samples, frame)[::hop]
    rms = np.sqrt(np.mean(windows * windows, axis=1) + 1e-10)
    envelope = np.log1p(rms * 70.0)
    envelope = _moving_average(envelope, 3)

    median = float(np.median(envelope))
    mad = float(np.median(np.abs(envelope - median))) + 1e-6
    percentile = float(np.percentile(envelope, 90))
    threshold = max(median + 4.2 * mad, percentile * 0.94, 0.12)

    candidate_indices: list[int] = []
    min_frames = max(2, int(0.16 / 0.005))
    for index in range(2, len(envelope) - 2):
        value = envelope[index]
        if value < threshold:
            continue
        if value < envelope[index - 1] or value < envelope[index + 1]:
            continue
        if candidate_indices and index - candidate_indices[-1] < min_frames:
            if value > envelope[candidate_indices[-1]]:
                candidate_indices[-1] = index
            continue
        candidate_indices.append(index)

    if on_progress:
        on_progress(0.3, "识别击球与回合")

    hits: list[tuple[float, float]] = [
        (index * hop / sample_rate, float(envelope[index])) for index in candidate_indices
    ]
    if not hits:
        return []

    # Group transient hits into rallies. The gap threshold is deliberately larger
    # than the longest normal shot interval but shorter than most dead-ball gaps.
    groups: list[list[tuple[float, float]]] = []
    for hit in hits:
        if not groups or hit[0] - groups[-1][-1][0] > 2.6:
            groups.append([hit])
        else:
            groups[-1].append(hit)

    groups = _merge_visually_continuous_groups(
        groups, duration, video_path, court_points
    )

    rallies: list[DetectedRally] = []
    for index, group in enumerate(groups):
        first_hit = group[0][0]
        last_hit = group[-1][0]
        start = max(0.0, first_hit - 2.25)
        end = min(duration, last_hit + 1.8)

        # Keep a generous lead-in for the serve, but split adjacent rallies at
        # the midpoint between the previous dead ball and the next first hit.
        # This avoids merging two rallies when their lead-ins overlap.
        if index > 0:
            previous_last_hit = groups[index - 1][-1][0]
            start = max(start, (previous_last_hit + first_hit) / 2.0)
        if index + 1 < len(groups):
            next_first_hit = groups[index + 1][0][0]
            end = min(end, (last_hit + next_first_hit) / 2.0)

        if end - start < 1.25 or end - start > 75:
            continue
        strengths = np.array([hit[1] for hit in group], dtype=np.float32)
        peak_strength = float(np.percentile(strengths, 75) / max(threshold, 1e-6))
        confidence = float(np.clip(0.46 + 0.12 * min(len(group), 8) + 0.08 * (peak_strength - 1), 0.35, 0.9))
        rallies.append(
            DetectedRally(
                start_time=round(start, 3),
                end_time=round(end, 3),
                confidence=round(confidence, 3),
                hit_count=len(group),
            )
        )
    return rallies

def infer_winners(
    video: Path,
    rallies: list[DetectedRally],
    duration: float,
    initial_a_side: str,
    side_swap_times: Iterable[float],
    court_points: list[list[float]] | None = None,
) -> list[tuple[str, float, bool]]:
    """Return a low-cost camera-side heuristic winner suggestion.

    This intentionally reports low confidence when motion is ambiguous. It is a
    review aid, not a referee: users can correct every point in the timeline.
    """
    swaps = sorted(float(value) for value in side_swap_times)
    polygon = None
    if court_points and len(court_points) == 4:
        polygon = np.array(
            [[int(point[0] * 240), int(point[1] * 136)] for point in court_points],
            dtype=np.int32,
        )
    capture = cv2.VideoCapture(str(video))
    if not capture.isOpened():
        return [("B", 0.25, False) for _ in rallies]

    suggestions: list[tuple[str, float, bool]] = []
    fps = capture.get(cv2.CAP_PROP_FPS) or 30.0
    for rally in rallies:
        side_swap_count = sum(1 for swap_time in swaps if swap_time <= rally.end_time)
        a_side = initial_a_side
        if side_swap_count % 2:
            a_side = "bottom" if initial_a_side == "top" else "top"

        trajectory = track_shuttle(
            video,
            max(rally.start_time, rally.end_time - 6.0),
            rally.end_time,
            court_points,
            sample_fps=10.0,
        )
        landing_result = infer_winner_from_landing(trajectory, a_side)
        if landing_result is not None:
            suggestions.append((landing_result[0], landing_result[1], True))
            continue

        end = max(rally.start_time + 0.1, rally.end_time - 0.2)
        start = max(rally.start_time, end - 1.7)
        capture.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
        previous_gray: np.ndarray | None = None
        half_motion = {"top": 0.0, "bottom": 0.0}
        frames = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            current_time = capture.get(cv2.CAP_PROP_POS_MSEC) / 1000
            if current_time > end:
                break
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            gray = cv2.resize(gray, (240, 136), interpolation=cv2.INTER_AREA)
            if previous_gray is not None:
                diff = cv2.absdiff(gray, previous_gray)
                _, diff = cv2.threshold(diff, 22, 255, cv2.THRESH_BINARY)
                if polygon is not None:
                    mask = np.zeros_like(diff)
                    cv2.fillPoly(mask, [polygon], 255)
                    diff = cv2.bitwise_and(diff, mask)
                half_motion["top"] += float(diff[:74].sum())
                half_motion["bottom"] += float(diff[74:].sum())
            previous_gray = gray
            frames += 1
            if frames > int(fps * 2.2):
                break

        total = half_motion["top"] + half_motion["bottom"] + 1e-6
        top_ratio = half_motion["top"] / total
        active_side = "top" if top_ratio >= 0.5 else "bottom"
        loser = "A" if active_side == a_side else "B"
        winner = "B" if loser == "A" else "A"
        separation = abs(top_ratio - 0.5) * 2
        confidence = float(np.clip(0.28 + separation * 0.55, 0.28, 0.72))
        suggestions.append((winner, round(confidence, 3), False))

    capture.release()
    return suggestions

def _ass_time(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def _ass_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def _score_states(
    duration: float,
    timeline: list[dict],
    initial_a_score: int,
    initial_b_score: int,
    first_server: str,
) -> list[tuple[float, int, int, str]]:
    states: list[tuple[float, int, int, str]] = [
        (0.0, initial_a_score, initial_b_score, first_server)
    ]
    for item in timeline:
        score = item["score_after"]
        states.append((float(item["score_update_time"]), score["A"], score["B"], item["server_after"]))
    compact: list[tuple[float, int, int, str]] = []
    for state in states:
        if compact and state[1:] == compact[-1][1:]:
            continue
        if compact and state[0] <= compact[-1][0]:
            compact[-1] = state
        else:
            compact.append(state)
    return compact


def _approx_text_width(text: str, font_size: int) -> float:
    return float(
        sum(font_size * (0.58 if ord(character) < 128 else 1.0) for character in text)
    )


def _ass_round_rect(width: float, height: float, radius: float) -> str:
    r = min(radius, width / 2, height / 2)
    w = width
    h = height
    return (
        f"m {r} 0 l {w-r} 0 "
        f"b {w} 0 {w} 0 {w} {r} "
        f"l {w} {h-r} "
        f"b {w} {h} {w} {h} {w-r} {h} "
        f"l {r} {h} "
        f"b 0 {h} 0 {h} 0 {h-r} "
        f"l 0 {r} "
        f"b 0 0 0 0 {r} 0"
    )


def write_score_ass(
    path: Path,
    *,
    clip_start: float,
    clip_end: float,
    width: int,
    height: int,
    player_a: str,
    player_b: str,
    initial_a_score: int,
    initial_b_score: int,
    first_server: str,
    timeline: list[dict],
) -> Path:
    states = _score_states(
        clip_end - clip_start,
        timeline,
        initial_a_score,
        initial_b_score,
        first_server,
    )

    scale = max(0.8, min(1.6, width / 960.0 if width else 1.0))
    margin = round(14 * scale)
    row_height = round(35 * scale)
    name_font = max(14, round(17 * scale))
    score_font = max(18, round(22 * scale))
    padding_x = round(10 * scale)
    dot_space = round(13 * scale)
    score_gap = round(16 * scale)
    score_width = score_font * 1.6
    max_name_width = max(
        _approx_text_width(player_a, name_font),
        _approx_text_width(player_b, name_font),
    )
    box_width = max(
        round(168 * scale),
        round(
            padding_x * 2
            + dot_space
            + max_name_width
            + score_gap
            + score_width
        ),
    )
    box_height = row_height * 2
    radius = round(10 * scale)
    x = margin
    y = margin
    right = x + box_width - padding_x
    row_a_y = y + round(7 * scale)
    row_b_y = y + row_height + round(7 * scale)
    score_a_y = y + round(3 * scale)
    score_b_y = y + row_height + round(3 * scale)
    name_x = x + padding_x + dot_space
    background_shape = _ass_round_rect(box_width, box_height, radius)
    separator_shape = f"m 1 0 l {box_width-1} 0 l {box_width-1} 1 l 1 1"
    highlight_height = row_height - 5
    highlight_shape = _ass_round_rect(
        box_width - 4, highlight_height, max(6, radius - 3)
    )
    server_highlight_y = (
        y + 2 if first_server == "A" else y + row_height + 1
    )

    style = (
        f"Style: Scoreboard,Microsoft YaHei,{name_font},"
        "&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,"
        f"-1,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1"
    )
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{style}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    visible_states = [state for state in states if state[0] < clip_end]
    for index, state in enumerate(visible_states):
        start, score_a, score_b, server = state
        end = visible_states[index + 1][0] if index + 1 < len(visible_states) else clip_end
        if end <= clip_start:
            continue
        start = max(start, clip_start)
        end = min(end, clip_end)
        if end - start < 0.01:
            continue

        def dialogue(layer: int, text: str) -> str:
            return (
                f"Dialogue: {layer},{_ass_time(start - clip_start)},"
                f"{_ass_time(end - clip_start)},Scoreboard,,0,0,0,,{text}"
            )

        lines.append(
            dialogue(
                0,
                (
                    f"{{\\an7\\pos({x},{y})\\p1\\bord{max(1, round(scale))}"
                    "\\shad0\\1c&H070905&\\1a&H21&\\3c&H2B2B2B&\\3a&H7A&}"
                    f"{background_shape}"
                ),
            )
        )
        highlight_y = (
            y + 2 if server == "A" else y + row_height + 1
        )
        lines.append(
            dialogue(
                1,
                (
                    f"{{\\an7\\pos({x + 2},{highlight_y})\\p1\\bord0\\shad0"
                    "\\1c&H4FF3C6&\\1a&HF2&}"
                    f"{highlight_shape}"
                ),
            )
        )
        lines.append(
            dialogue(
                1,
                (
                    f"{{\\an7\\pos({x + 1},{y + row_height})\\p1\\bord0\\shad0"
                    "\\1c&HFFFFFF&\\1a&HF0&}"
                    f"{separator_shape}"
                ),
            )
        )

        name_a_text = (
            f"{{\\an7\\pos({name_x},{row_a_y})\\fs{name_font}\\b1"
            "\\c&HEFF5ED&}"
            + _ass_escape(player_a)
        )
        name_b_text = (
            f"{{\\an7\\pos({name_x},{row_b_y})\\fs{name_font}\\b1"
            "\\c&HEFF5ED&}"
            + _ass_escape(player_b)
        )
        if server == "A":
            lines.append(
                dialogue(
                    2,
                    (
                        f"{{\\an7\\pos({x + padding_x},{row_a_y + round(4 * scale)})"
                        f"\\fs{max(9, round(name_font * 0.62))}\\b1\\c&H4FF3C6&}}●"
                    ),
                )
            )
        elif server == "B":
            lines.append(
                dialogue(
                    2,
                    (
                        f"{{\\an7\\pos({x + padding_x},{row_b_y + round(4 * scale)})"
                        f"\\fs{max(9, round(name_font * 0.62))}\\b1\\c&H4FF3C6&}}●"
                    ),
                )
            )
        lines.append(dialogue(2, name_a_text))
        lines.append(
            dialogue(
                2,
                f"{{\\an9\\pos({right},{score_a_y})\\fs{score_font}\\b1\\c&HEFF5ED&}}{score_a}",
            )
        )
        lines.append(dialogue(2, name_b_text))
        lines.append(
            dialogue(
                2,
                f"{{\\an9\\pos({right},{score_b_y})\\fs{score_font}\\b1\\c&HEFF5ED&}}{score_b}",
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8-sig")
    return path

def render_full_video(
    source: Path,
    output: Path,
    duration: float,
    width: int,
    height: int,
    player_a: str,
    player_b: str,
    initial_a_score: int,
    initial_b_score: int,
    first_server: str,
    timeline: list[dict],
    on_progress: ProgressCallback | None = None,
) -> Path:
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="badminton-overlay-") as temp_dir:
        workdir = Path(temp_dir)
        write_score_ass(
            workdir / "overlay.ass",
            clip_start=0,
            clip_end=duration,
            width=width,
            height=height,
            player_a=player_a,
            player_b=player_b,
            initial_a_score=initial_a_score,
            initial_b_score=initial_b_score,
            first_server=first_server,
            timeline=timeline,
        )
        args = [
            "-i",
            str(source.resolve()),
            "-vf",
            "ass=overlay.ass",
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(output.resolve()),
        ]
        run_ffmpeg_with_progress(args, duration, on_progress, "渲染完整视频", cwd=workdir)
    return output


def render_highlight_video(
    source: Path,
    output: Path,
    duration: float,
    width: int,
    height: int,
    player_a: str,
    player_b: str,
    initial_a_score: int,
    initial_b_score: int,
    first_server: str,
    timeline: list[dict],
    rally_ids: list[str],
    on_progress: ProgressCallback | None = None,
) -> Path:
    selected = [item for item in timeline if item["id"] in set(rally_ids)]
    selected.sort(key=lambda item: item["start_time"])
    if not selected:
        raise ValueError("没有可导出的回合")
    output.parent.mkdir(parents=True, exist_ok=True)
    clip_ranges = [
        (
            item,
            float(item["start_time"]),
            min(duration, max(float(item["end_time"]), float(item["score_update_time"]) + 0.35)),
        )
        for item in selected
    ]
    selected_duration = sum(end - start for _, start, end in clip_ranges)
    with tempfile.TemporaryDirectory(prefix="badminton-highlight-") as temp_dir:
        workdir = Path(temp_dir)
        concat_lines: list[str] = []
        completed = 0.0
        for index, (item, rally_start, rally_end) in enumerate(clip_ranges):
            clip_name = f"clip-{index:04d}.mp4"
            ass_name = f"clip-{index:04d}.ass"
            write_score_ass(
                workdir / ass_name,
                clip_start=rally_start,
                clip_end=rally_end,
                width=width,
                height=height,
                player_a=player_a,
                player_b=player_b,
                initial_a_score=initial_a_score,
                initial_b_score=initial_b_score,
                first_server=first_server,
                timeline=timeline,
            )
            clip_duration = rally_end - rally_start
            args = [
                "-ss",
                f"{rally_start:.3f}",
                "-t",
                f"{clip_duration:.3f}",
                "-i",
                str(source.resolve()),
                "-vf",
                f"ass={ass_name}",
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                clip_name,
            ]

            def clip_progress(value: float, _stage: str, base=completed) -> None:
                if on_progress and selected_duration > 0:
                    on_progress(min(0.96, (base + value * clip_duration) / selected_duration), "渲染回合")

            run_ffmpeg_with_progress(args, clip_duration, clip_progress, "渲染回合", cwd=workdir)
            completed += clip_duration
            concat_lines.append(f"file '{clip_name}'")
        concat_file = workdir / "concat.txt"
        concat_file.write_text("\n".join(concat_lines), encoding="utf-8")
        args = [
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            "concat.txt",
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output.resolve()),
        ]
        run_ffmpeg_with_progress(args, selected_duration, on_progress, "合并集锦", cwd=workdir)
    return output


def suggestions_to_json(items: list[tuple[str, float]]) -> str:
    return json.dumps(items, ensure_ascii=False)
