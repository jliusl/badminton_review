from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import FRONTEND_DIST, PROJECTS_DIR
from .db import connection, init_db, utc_now
from .jobs import remove_project_data, submit_analysis, submit_export
from .models import (
    ExportCreate,
    ProjectImport,
    ProjectUpdate,
    RallyCreate,
    RallyMerge,
    RallySplit,
    RallyUpdate,
    SideSwapCreate,
)
from .store import (
    add_side_swap,
    create_export_record,
    delete_rally,
    delete_side_swap,
    get_export,
    get_project,
    get_rally,
    insert_rallies,
    list_exports,
    list_projects,
    normalize_rally_order,
    project_payload,
    set_project_progress,
    update_project,
    update_rally,
)

SUPPORTED_VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".avi", ".m4v", ".webm"}


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    init_db()
    yield


app = FastAPI(title="羽球飞扬", version="0.1.0", lifespan=lifespan)


@app.exception_handler(StarletteHTTPException)
async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    if exc.status_code == 400 and exc.detail in {
        "There was an error parsing the body",
        "Invalid multipart data.",
    }:

        exc.detail = "上传文件解析失败。请确认数据盘有足够剩余空间，并重新上传视频。"
    return await http_exception_handler(request, exc)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def create_project_record(
    *,
    source_path: Path,
    title: str,
    player_a_name: str,
    player_b_name: str,
    initial_a_score: int,
    initial_b_score: int,
    first_server: str,
    first_server_court: str | None,
    initial_a_side: str,
) -> dict:
    project_id = str(uuid.uuid4())
    now = utc_now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO projects (
                id, title, source_path, source_size, player_a_name, player_b_name,
                initial_a_score, initial_b_score, first_server, first_server_court,
                initial_a_side, status, stage, progress, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', '等待分析', 0, ?, ?)
            """,
            (
                project_id,
                title,
                str(source_path),
                source_path.stat().st_size if source_path.exists() else 0,
                player_a_name.strip() or "球员 A",
                player_b_name.strip() or "球员 B",
                initial_a_score,
                initial_b_score,
                first_server,
                first_server_court,
                initial_a_side,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    submit_analysis(project_id)
    return project_payload(dict(row))


def require_project(project_id: str) -> dict:
    project = get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project


@app.get("/api/health")
def health() -> dict:
    from .media import ffmpeg_version

    return {"ok": True, "ffmpeg": ffmpeg_version()}


@app.get("/api/projects")
def projects() -> list[dict]:
    return list_projects()


@app.post("/api/projects/import-path", status_code=201)
def import_path(payload: ProjectImport) -> dict:
    source = Path(payload.path).expanduser().resolve()
    if not source.exists() or not source.is_file():
        raise HTTPException(status_code=400, detail="找不到视频文件")
    if source.suffix.lower() not in SUPPORTED_VIDEO_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持该视频格式")
    return create_project_record(
        source_path=source,
        title=payload.title or source.stem,
        player_a_name=payload.player_a_name,
        player_b_name=payload.player_b_name,
        initial_a_score=payload.initial_a_score,
        initial_b_score=payload.initial_b_score,
        first_server=payload.first_server,
        first_server_court=payload.first_server_court,
        initial_a_side=payload.initial_a_side,
    )


@app.post("/api/projects/upload", status_code=201)
async def upload_project(
    video: UploadFile = File(...),
    title: str = Form(""),
    player_a_name: str = Form("球员 A"),
    player_b_name: str = Form("球员 B"),
    initial_a_score: int = Form(0),
    initial_b_score: int = Form(0),
    first_server: str = Form("A"),
    first_server_court: str = Form(""),
    initial_a_side: str = Form("bottom"),
) -> dict:
    suffix = Path(video.filename or "video.mp4").suffix.lower()
    if suffix not in SUPPORTED_VIDEO_SUFFIXES:
        raise HTTPException(status_code=400, detail="不支持该视频格式")
    if first_server not in {"A", "B"} or initial_a_side not in {"top", "bottom"}:
        raise HTTPException(status_code=400, detail="项目参数不合法")
    if initial_a_score < 0 or initial_b_score < 0:
        raise HTTPException(status_code=400, detail="起始比分不能为负数")
    project_id = str(uuid.uuid4())
    project_dir = PROJECTS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    target = project_dir / f"source{suffix}"
    try:
        with target.open("wb") as output:
            while chunk := await video.read(1024 * 1024 * 4):
                output.write(chunk)
    finally:
        await video.close()
    return create_project_record(
        source_path=target,
        title=title.strip() or Path(video.filename or "羽毛球比赛").stem,
        player_a_name=player_a_name,
        player_b_name=player_b_name,
        initial_a_score=initial_a_score,
        initial_b_score=initial_b_score,
        first_server=first_server,
        first_server_court=first_server_court or None,
        initial_a_side=initial_a_side,
    )


@app.get("/api/projects/{project_id}")
def project_detail(project_id: str) -> dict:
    return project_payload(require_project(project_id))


@app.patch("/api/projects/{project_id}")
def patch_project(project_id: str, payload: ProjectUpdate) -> dict:
    require_project(project_id)
    changes = payload.model_dump(exclude_unset=True)
    updated = update_project(project_id, changes)
    if not updated:
        raise HTTPException(status_code=404, detail="项目不存在")
    return project_payload(updated)


@app.delete("/api/projects/{project_id}", status_code=204)
def delete_project(project_id: str) -> None:
    require_project(project_id)
    with connection() as conn:
        conn.execute("DELETE FROM projects WHERE id=?", (project_id,))
    remove_project_data(project_id)


@app.post("/api/projects/{project_id}/reanalyze", status_code=202)
def reanalyze(project_id: str) -> dict:
    project = require_project(project_id)
    if project["status"] == "analyzing":
        raise HTTPException(status_code=409, detail="项目正在分析")
    with connection() as conn:
        conn.execute("DELETE FROM rallies WHERE project_id=?", (project_id,))
    set_project_progress(project_id, status="queued", stage="等待重新分析", progress=0, error="")
    submit_analysis(project_id)
    return {"ok": True}


@app.get("/api/projects/{project_id}/video")
def project_video(project_id: str) -> FileResponse:
    project = require_project(project_id)
    path = Path(project.get("preview_path") or project["source_path"])
    if not path.exists():
        path = Path(project["source_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="视频文件不存在，请重新定位")
    media_type = "video/mp4" if path.suffix.lower() in {".mp4", ".m4v", ".mov"} else "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=path.name)


@app.get("/api/projects/{project_id}/thumbnail")
def project_thumbnail(project_id: str) -> FileResponse:
    project = require_project(project_id)
    path = Path(project.get("thumbnail_path") or "")
    if not path.exists():
        raise HTTPException(status_code=404, detail="缩略图不存在")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/projects/{project_id}/events")
async def project_events(project_id: str) -> StreamingResponse:
    require_project(project_id)

    async def stream() -> AsyncIterator[str]:
        while True:
            project = get_project(project_id)
            if not project:
                break
            payload = {
                "status": project["status"],
                "stage": project["stage"],
                "progress": project["progress"],
                "error": project["error"],
            }
            yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            if project["status"] in {"ready", "failed"}:
                break
            await asyncio.sleep(0.75)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.patch("/api/rallies/{rally_id}")
def patch_rally(rally_id: str, payload: RallyUpdate) -> dict:
    rally = get_rally(rally_id)
    if not rally:
        raise HTTPException(status_code=404, detail="回合不存在")
    changes = payload.model_dump(exclude_unset=True)
    if "start_time" in changes or "end_time" in changes:
        start = float(changes.get("start_time", rally["start_time"]))
        end = float(changes.get("end_time", rally["end_time"]))
        if end <= start:
            raise HTTPException(status_code=400, detail="回合结束时间必须晚于开始时间")
    update_rally(rally_id, changes)
    normalize_rally_order(rally["project_id"])
    return project_payload(require_project(rally["project_id"]))


@app.post("/api/projects/{project_id}/rallies", status_code=201)
def add_rally(project_id: str, payload: RallyCreate) -> dict:
    require_project(project_id)
    if payload.end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="回合结束时间必须晚于开始时间")
    rally = {
        "id": str(uuid.uuid4()),
        "start_time": payload.start_time,
        "end_time": payload.end_time,
        "winner": payload.winner,
        "is_valid": payload.is_valid,
        "is_let": payload.is_let,
        "let_confirmed": payload.is_let,
        "confidence": 1.0,
        "source": "manual",
        "verified": True,
        "note": payload.note,
    }
    insert_rallies(project_id, [rally])
    return project_payload(require_project(project_id))


@app.delete("/api/rallies/{rally_id}")
def remove_rally(rally_id: str) -> dict:
    project_id = delete_rally(rally_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="回合不存在")
    return project_payload(require_project(project_id))


@app.post("/api/rallies/{rally_id}/split")
def split_rally(rally_id: str, payload: RallySplit) -> dict:
    rally = get_rally(rally_id)
    if not rally:
        raise HTTPException(status_code=404, detail="回合不存在")
    if not float(rally["start_time"]) < payload.time < float(rally["end_time"]):
        raise HTTPException(status_code=400, detail="拆分点必须位于回合内部")
    project_id = rally["project_id"]
    delete_rally(rally_id)
    new_rows = [
        {
            "id": str(uuid.uuid4()),
            "start_time": rally["start_time"],
            "end_time": payload.time,
            "winner": None,
            "is_valid": bool(rally["is_valid"]),
            "is_let": False,
            "let_confirmed": False,
            "confidence": 0.0,
            "source": "split",
            "verified": False,
            "note": "拆分后的前半段，请确认得分",
        },
        {
            "id": str(uuid.uuid4()),
            "start_time": payload.time,
            "end_time": rally["end_time"],
            "winner": rally["winner"],
            "is_valid": bool(rally["is_valid"]),
            "is_let": bool(rally["is_let"]),
            "let_confirmed": bool(rally["let_confirmed"]),
            "confidence": rally["confidence"],
            "source": "split",
            "verified": bool(rally["verified"]),
            "note": "拆分后的后半段",
        },
    ]
    insert_rallies(project_id, new_rows)
    return project_payload(require_project(project_id))


@app.post("/api/rallies/merge")
def merge_rallies(payload: RallyMerge) -> dict:
    first = get_rally(payload.first_id)
    second = get_rally(payload.second_id)
    if not first or not second or first["project_id"] != second["project_id"]:
        raise HTTPException(status_code=400, detail="只能合并同一项目中的两个回合")
    if second["start_time"] < first["start_time"]:
        first, second = second, first
    project_id = first["project_id"]
    update_rally(
        first["id"],
        {
            "end_time": max(first["end_time"], second["end_time"]),
            "winner": second["winner"] if first["is_valid"] and second["is_valid"] else None,
            "is_valid": bool(first["is_valid"] and second["is_valid"]),
            "is_let": bool(second["is_let"]),
            "verified": bool(second["verified"]),
            "note": "合并后的回合",
        },
    )
    delete_rally(second["id"])
    normalize_rally_order(project_id)
    return project_payload(require_project(project_id))


@app.post("/api/projects/{project_id}/side-swaps", status_code=201)
def create_side_swap(project_id: str, payload: SideSwapCreate) -> dict:
    require_project(project_id)
    add_side_swap(project_id, str(uuid.uuid4()), payload.time)
    return project_payload(require_project(project_id))


@app.delete("/api/side-swaps/{swap_id}")
def remove_side_swap(swap_id: str) -> dict:
    project_id = delete_side_swap(swap_id)
    if not project_id:
        raise HTTPException(status_code=404, detail="换边事件不存在")
    return project_payload(require_project(project_id))


@app.get("/api/projects/{project_id}/exports")
def project_exports(project_id: str) -> list[dict]:
    require_project(project_id)
    return list_exports(project_id)


@app.post("/api/projects/{project_id}/exports", status_code=202)
def start_export(project_id: str, payload: ExportCreate) -> dict:
    project = require_project(project_id)
    if project["status"] != "ready":
        raise HTTPException(status_code=409, detail="项目尚未分析完成")
    export_id = str(uuid.uuid4())
    record = create_export_record(export_id, project_id, payload.kind, payload.rally_ids)
    submit_export(export_id)
    return record


@app.get("/api/exports/{export_id}")
def export_detail(export_id: str) -> dict:
    record = get_export(export_id)
    if not record:
        raise HTTPException(status_code=404, detail="导出任务不存在")
    return record


@app.get("/api/exports/{export_id}/file")
def download_export(export_id: str) -> FileResponse:
    record = get_export(export_id)
    if not record or record["status"] != "ready" or not record.get("output_path"):
        raise HTTPException(status_code=404, detail="导出文件尚未生成")
    path = Path(record["output_path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail="导出文件已丢失")
    return FileResponse(path, media_type="video/mp4", filename=path.name)


@app.get("/{full_path:path}", include_in_schema=False)
def frontend_app(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="接口不存在")
    index = FRONTEND_DIST / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="前端尚未构建，请运行 npm run build")
    candidate = (FRONTEND_DIST / full_path).resolve()
    dist_root = FRONTEND_DIST.resolve()
    if candidate.is_file() and candidate.is_relative_to(dist_root):
        return FileResponse(candidate)
    return FileResponse(index, media_type="text/html")