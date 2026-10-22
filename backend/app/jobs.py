from __future__ import annotations

import json
import shutil
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .config import EXPORTS_DIR, PROJECTS_DIR
from .media import (
    create_preview,
    create_thumbnail,
    detect_rallies_from_audio,
    extract_analysis_audio,
    infer_winners,
    probe_video,
    render_full_video,
    render_highlight_video,
)
from .store import (
    get_export,
    get_project,
    get_rallies,
    get_side_swaps,
    insert_rallies,
    set_project_metadata,
    set_project_progress,
    update_export,
)

EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="badminton-worker")


def _analysis_progress(project_id: str):
    def callback(value: float, stage: str) -> None:
        set_project_progress(project_id, stage=stage, progress=value)

    return callback


def run_analysis(project_id: str) -> None:
    project = get_project(project_id)
    if not project:
        return
    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    source = Path(project["source_path"])
    preview: Path | None = None
    audio_path: Path | None = None

    try:
        set_project_progress(project_id, status="analyzing", stage="读取视频", progress=0.01, error="")
        info = probe_video(source)
        set_project_metadata(
            project_id,
            {
                "source_size": source.stat().st_size,
                "duration": info.duration,
                "width": info.width,
                "height": info.height,
                "fps": info.fps,
                "video_codec": info.video_codec,
                "audio_codec": info.audio_codec or "",
            },
        )

        set_project_progress(project_id, stage="生成预览", progress=0.03)
        preview = create_preview(
            source,
            project_dir / "preview.mp4",
            info,
            lambda value, stage: set_project_progress(
                project_id, stage=stage, progress=0.03 + value * 0.27
            ),
        )
        set_project_metadata(project_id, {"preview_path": str(preview)})

        set_project_progress(project_id, stage="生成缩略图", progress=0.31)
        thumbnail = create_thumbnail(preview, project_dir / "thumbnail.jpg", info.duration)
        set_project_metadata(project_id, {"thumbnail_path": str(thumbnail)})

        if not info.has_audio:
            raise RuntimeError("视频没有音轨，当前版本无法自动识别回合，请使用带现场声音的视频")

        set_project_progress(project_id, stage="提取击球音频", progress=0.34)
        audio_path = extract_analysis_audio(preview, project_dir / "analysis.wav")
        court_points = None
        if project.get("court_points"):
            try:
                court_points = json.loads(project["court_points"])
            except (json.JSONDecodeError, TypeError):
                court_points = None
        detections = detect_rallies_from_audio(
            audio_path,
            info.duration,
            lambda value, stage: set_project_progress(
                project_id, stage=stage, progress=0.34 + value * 0.08
            ),
            preview,
            court_points,
        )
        if not detections:
            raise RuntimeError("没有从音频中识别到有效回合，请检查视频声音或改用手工补录")

        set_project_progress(project_id, stage="推断得分方", progress=0.45)
        side_swaps = [float(item["time"]) for item in get_side_swaps(project_id)]
        suggestions = infer_winners(
            preview,
            detections,
            info.duration,
            project["initial_a_side"],
            side_swaps,
            court_points,
        )
        set_project_progress(project_id, stage="生成复盘时间线", progress=0.88)

        rows: list[dict] = []
        for detection, (winner, winner_confidence, used_trajectory) in zip(detections, suggestions):
            merged_confidence = round(
                min(0.92, 0.35 * detection.confidence + 0.65 * winner_confidence), 3
            )
            notes: list[str] = []
            if detection.hit_count <= 1:
                notes.append("仅检测到一次击球，可能为发球得分或重发球，请确认")
            if used_trajectory:
                notes.append("已结合羽毛球轨迹与落点判断")
            note = "；".join(notes) or None
            rows.append(
                {
                    "id": str(uuid.uuid4()),
                    "start_time": detection.start_time,
                    "end_time": detection.end_time,
                    "winner": winner,
                    "is_valid": True,
                    "is_let": False,
                    "let_confirmed": False,
                    "confidence": merged_confidence,
                    "source": "ai",
                    "verified": False,
                    "note": note,
                }
            )
        insert_rallies(project_id, rows, replace=True)

        set_project_progress(
            project_id,
            status="ready",
            stage=f"分析完成：{len(rows)} 个回合",
            progress=1.0,
            error="",
        )
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        detail = traceback.format_exc()
        (project_dir / "analysis-error.log").write_text(detail, encoding="utf-8")
        set_project_progress(
            project_id,
            status="failed",
            stage="分析失败",
            progress=0.0,
            error=message,
        )
    finally:
        if audio_path and audio_path.exists():
            try:
                audio_path.unlink()
            except OSError:
                pass


def submit_analysis(project_id: str) -> None:
    EXECUTOR.submit(run_analysis, project_id)


def run_export(export_id: str) -> None:
    export = get_export(export_id)
    if not export:
        return
    project = get_project(export["project_id"])
    if not project:
        update_export(export_id, status="failed", error="项目不存在")
        return

    output_dir = EXPORTS_DIR / project["id"]
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{export_id}.mp4"
    try:
        update_export(export_id, status="exporting", progress=0.01, error="")
        from .store import get_timeline

        timeline = get_timeline(project)
        if not timeline:
            raise ValueError("时间线为空，无法导出")
        source = Path(project.get("preview_path") or project["source_path"])
        if not source.exists():
            source = Path(project["source_path"])
        first_server = project["first_server"]
        if export["kind"] == "full":
            render_full_video(
                source,
                output_path,
                float(project["duration"]),
                int(project["width"]),
                int(project["height"]),
                project["player_a_name"],
                project["player_b_name"],
                int(project["initial_a_score"]),
                int(project["initial_b_score"]),
                first_server,
                timeline,
                lambda value, stage: update_export(
                    export_id, progress=max(0.01, value), error=None
                ),
            )
        else:
            rally_ids = json.loads(export["rally_ids"]) if export.get("rally_ids") else None
            if not rally_ids:
                rally_ids = [item["id"] for item in timeline if item["is_valid"] and not item["is_let"]]
            render_highlight_video(
                source,
                output_path,
                float(project["duration"]),
                int(project["width"]),
                int(project["height"]),
                project["player_a_name"],
                project["player_b_name"],
                int(project["initial_a_score"]),
                int(project["initial_b_score"]),
                first_server,
                timeline,
                rally_ids,
                lambda value, stage: update_export(
                    export_id, progress=max(0.01, value), error=None
                ),
            )
        update_export(
            export_id,
            status="ready",
            progress=1.0,
            output_path=str(output_path),
            error="",
        )
    except Exception as exc:
        message = str(exc).strip() or exc.__class__.__name__
        log_path = output_dir / f"{export_id}-error.log"
        log_path.write_text(traceback.format_exc(), encoding="utf-8")
        update_export(export_id, status="failed", progress=0.0, error=message)


def submit_export(export_id: str) -> None:
    EXECUTOR.submit(run_export, export_id)


def remove_project_data(project_id: str) -> None:
    project_dir = (PROJECTS_DIR / project_id).resolve()
    root = PROJECTS_DIR.resolve()
    if project_dir.parent == root and project_dir.exists():
        shutil.rmtree(project_dir)
    output_dir = (EXPORTS_DIR / project_id).resolve()
    output_root = EXPORTS_DIR.resolve()
    if output_dir.parent == output_root and output_dir.exists():
        shutil.rmtree(output_dir)