from __future__ import annotations

import json
import sqlite3
from typing import Any

from .db import connection, utc_now
from .score import RallyInput, ScoreRules, derive_score_timeline

PROJECT_FIELDS = {
    "title",
    "player_a_name",
    "player_b_name",
    "initial_a_score",
    "initial_b_score",
    "first_server",
    "first_server_court",
    "initial_a_side",
    "court_points",
}


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


def project_rules(project: dict[str, Any]) -> ScoreRules:
    return ScoreRules(
        initial_a_score=int(project["initial_a_score"]),
        initial_b_score=int(project["initial_b_score"]),
        first_server=project["first_server"],
        first_server_court=project.get("first_server_court"),
    )


def get_project(project_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return row_to_dict(row)


def list_projects() -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            """
            SELECT p.*,
                   (SELECT COUNT(*) FROM rallies r WHERE r.project_id=p.id) AS rally_count,
                   (SELECT COUNT(*) FROM rallies r WHERE r.project_id=p.id AND r.is_let=1) AS let_count,
                   (SELECT COUNT(*) FROM rallies r WHERE r.project_id=p.id AND (r.is_valid=0 OR r.is_let=1)) AS invalid_count
            FROM projects p
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_rally_rows(project_id: str) -> list[sqlite3.Row]:
    with connection() as conn:
        return conn.execute(
            "SELECT * FROM rallies WHERE project_id=? ORDER BY start_time, end_time, order_index",
            (project_id,),
        ).fetchall()


def get_rallies(project_id: str) -> list[RallyInput]:
    rows = get_rally_rows(project_id)
    return [
        RallyInput(
            id=row["id"],
            start_time=float(row["start_time"]),
            end_time=float(row["end_time"]),
            winner=row["winner"],
            is_valid=bool(row["is_valid"]),
            is_let=bool(row["is_let"]),
            let_confirmed=bool(row["let_confirmed"]),
            confidence=float(row["confidence"]),
            verified=bool(row["verified"]),
            source=row["source"],
            note=row["note"],
        )
        for row in rows
    ]


def get_timeline(project: dict[str, Any]) -> list[dict[str, Any]]:
    return derive_score_timeline(project_rules(project), get_rallies(project["id"]))


def get_side_swaps(project_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM side_swaps WHERE project_id=? ORDER BY time", (project_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def project_payload(project: dict[str, Any], include_timeline: bool = True) -> dict[str, Any]:
    payload = dict(project)
    for key in ("court_points",):
        if payload.get(key):
            try:
                payload[key] = json.loads(payload[key])
            except json.JSONDecodeError:
                payload[key] = None
    if include_timeline:
        timeline = get_timeline(project)
        payload["timeline"] = timeline
        payload["final_score"] = (
            timeline[-1]["score_after"] if timeline else {
                "A": int(project["initial_a_score"]),
                "B": int(project["initial_b_score"]),
            }
        )
        payload["unresolved_count"] = sum(1 for item in timeline if item["unresolved"])
        payload["let_count"] = sum(1 for item in timeline if item["is_let"])
        payload["invalid_count"] = sum(1 for item in timeline if not item["is_valid"] or item["is_let"])
        payload["side_swaps"] = get_side_swaps(project["id"])
    return payload


def update_project(project_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    allowed: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in PROJECT_FIELDS or value is None:
            continue
        if key == "court_points":
            allowed[key] = json.dumps(value, ensure_ascii=False)
        else:
            allowed[key] = value
    if not allowed:
        return get_project(project_id)
    allowed["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in allowed)
    with connection() as conn:
        conn.execute(
            f"UPDATE projects SET {assignments} WHERE id=?",
            (*allowed.values(), project_id),
        )
        row = conn.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
    return row_to_dict(row)


def touch_project(project_id: str) -> None:
    with connection() as conn:
        conn.execute(
            "UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), project_id)
        )


def set_project_progress(
    project_id: str,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress: float | None = None,
    error: str | None = None,
) -> None:
    changes: dict[str, Any] = {"updated_at": utc_now()}
    if status is not None:
        changes["status"] = status
    if stage is not None:
        changes["stage"] = stage
    if progress is not None:
        changes["progress"] = max(0.0, min(1.0, progress))
    if error is not None:
        changes["error"] = error
    assignments = ", ".join(f"{key}=?" for key in changes)
    with connection() as conn:
        conn.execute(
            f"UPDATE projects SET {assignments} WHERE id=?",
            (*changes.values(), project_id),
        )


def set_project_metadata(project_id: str, metadata: dict[str, Any]) -> None:
    allowed = {
        "source_size",
        "duration",
        "width",
        "height",
        "fps",
        "video_codec",
        "audio_codec",
        "preview_path",
        "thumbnail_path",
    }
    changes = {key: value for key, value in metadata.items() if key in allowed}
    changes["updated_at"] = utc_now()
    assignments = ", ".join(f"{key}=?" for key in changes)
    with connection() as conn:
        conn.execute(
            f"UPDATE projects SET {assignments} WHERE id=?",
            (*changes.values(), project_id),
        )


def normalize_rally_order(project_id: str) -> None:
    with connection() as conn:
        rows = conn.execute(
            "SELECT id FROM rallies WHERE project_id=? ORDER BY start_time, end_time",
            (project_id,),
        ).fetchall()
        for index, row in enumerate(rows):
            conn.execute("UPDATE rallies SET order_index=? WHERE id=?", (index, row["id"]))
        conn.execute(
            "UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), project_id)
        )


def insert_rallies(project_id: str, rallies: list[dict[str, Any]], replace: bool = False) -> None:
    now = utc_now()
    with connection() as conn:
        if replace:
            conn.execute("DELETE FROM rallies WHERE project_id=?", (project_id,))
        for index, rally in enumerate(sorted(rallies, key=lambda item: item["start_time"])):
            conn.execute(
                """
                INSERT INTO rallies (
                    id, project_id, order_index, start_time, end_time,
                    server_player, server_court, winner, is_valid, is_let, let_confirmed,
                    confidence, source, verified, note, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    rally["id"],
                    project_id,
                    index,
                    rally["start_time"],
                    rally["end_time"],
                    rally.get("server_player"),
                    rally.get("server_court"),
                    rally.get("winner"),
                    int(bool(rally.get("is_valid", True))),
                    int(bool(rally.get("is_let", False))),
                    int(bool(rally.get("let_confirmed", False))),
                    float(rally.get("confidence", 0)),
                    rally.get("source", "ai"),
                    int(bool(rally.get("verified", False))),
                    rally.get("note"),
                    now,
                    now,
                ),
            )
        conn.execute(
            "UPDATE projects SET updated_at=? WHERE id=?", (now, project_id)
        )


def get_rally(rally_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM rallies WHERE id=?", (rally_id,)).fetchone()
    return row_to_dict(row)


def update_rally(rally_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
    allowed = {
        "start_time",
        "end_time",
        "winner",
        "is_valid",
        "is_let",
        "let_confirmed",
        "verified",
        "note",
    }
    values: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in allowed:
            continue
        if key == "winner" and value is not None:
            values[key] = value
            values["is_valid"] = 1
            values["is_let"] = 0
            values["let_confirmed"] = 1
            values["verified"] = True
            values["confidence"] = 1.0
        elif key == "is_valid":
            valid = bool(value)
            values[key] = int(valid)
            values["verified"] = True
            values["confidence"] = 1.0
            if not valid:
                values["is_let"] = 0
                values["let_confirmed"] = 1
        elif key == "is_let":
            values[key] = int(bool(value))
            values["let_confirmed"] = True
            values["verified"] = True
            values["confidence"] = 1.0
        elif key == "verified":
            values[key] = int(bool(value))
        elif key in {"is_let", "let_confirmed"}:
            values[key] = int(bool(value))
        else:
            values[key] = value

    if values:
        values["updated_at"] = utc_now()
        assignments = ", ".join(f"{key}=?" for key in values)
        with connection() as conn:
            conn.execute(
                f"UPDATE rallies SET {assignments} WHERE id=?",
                (*values.values(), rally_id),
            )
    return get_rally(rally_id)


def delete_rally(rally_id: str) -> str | None:
    with connection() as conn:
        row = conn.execute("SELECT project_id FROM rallies WHERE id=?", (rally_id,)).fetchone()
        if not row:
            return None
        project_id = row["project_id"]
        conn.execute("DELETE FROM rallies WHERE id=?", (rally_id,))
        conn.execute(
            "UPDATE projects SET updated_at=? WHERE id=?", (utc_now(), project_id)
        )
    normalize_rally_order(project_id)
    return project_id


def add_side_swap(project_id: str, swap_id: str, time: float) -> dict[str, Any]:
    with connection() as conn:
        conn.execute(
            "INSERT INTO side_swaps (id, project_id, time, created_at) VALUES (?, ?, ?, ?)",
            (swap_id, project_id, time, utc_now()),
        )
    touch_project(project_id)
    return {"id": swap_id, "project_id": project_id, "time": time}


def delete_side_swap(swap_id: str) -> str | None:
    with connection() as conn:
        row = conn.execute("SELECT project_id FROM side_swaps WHERE id=?", (swap_id,)).fetchone()
        if not row:
            return None
        project_id = row["project_id"]
        conn.execute("DELETE FROM side_swaps WHERE id=?", (swap_id,))
    touch_project(project_id)
    return project_id


def create_export_record(export_id: str, project_id: str, kind: str, rally_ids: list[str] | None) -> dict[str, Any]:
    now = utc_now()
    with connection() as conn:
        conn.execute(
            """
            INSERT INTO exports (
                id, project_id, kind, rally_ids, status, progress, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'queued', 0, ?, ?)
            """,
            (
                export_id,
                project_id,
                kind,
                json.dumps(rally_ids, ensure_ascii=False) if rally_ids is not None else None,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM exports WHERE id=?", (export_id,)).fetchone()
    return dict(row)


def get_export(export_id: str) -> dict[str, Any] | None:
    with connection() as conn:
        row = conn.execute("SELECT * FROM exports WHERE id=?", (export_id,)).fetchone()
    return row_to_dict(row)


def list_exports(project_id: str) -> list[dict[str, Any]]:
    with connection() as conn:
        rows = conn.execute(
            "SELECT * FROM exports WHERE project_id=? ORDER BY created_at DESC",
            (project_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_export(
    export_id: str,
    *,
    status: str | None = None,
    progress: float | None = None,
    output_path: str | None = None,
    error: str | None = None,
) -> None:
    values: dict[str, Any] = {"updated_at": utc_now()}
    if status is not None:
        values["status"] = status
    if progress is not None:
        values["progress"] = max(0.0, min(1.0, progress))
    if output_path is not None:
        values["output_path"] = output_path
    if error is not None:
        values["error"] = error
    assignments = ", ".join(f"{key}=?" for key in values)
    with connection() as conn:
        conn.execute(
            f"UPDATE exports SET {assignments} WHERE id=?",
            (*values.values(), export_id),
        )