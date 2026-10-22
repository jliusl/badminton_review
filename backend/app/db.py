from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from .config import DB_PATH


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source_path TEXT NOT NULL,
    preview_path TEXT,
    thumbnail_path TEXT,
    source_size INTEGER NOT NULL DEFAULT 0,
    duration REAL NOT NULL DEFAULT 0,
    width INTEGER NOT NULL DEFAULT 0,
    height INTEGER NOT NULL DEFAULT 0,
    fps REAL NOT NULL DEFAULT 0,
    video_codec TEXT,
    audio_codec TEXT,
    player_a_name TEXT NOT NULL DEFAULT '球员 A',
    player_b_name TEXT NOT NULL DEFAULT '球员 B',
    initial_a_score INTEGER NOT NULL DEFAULT 0,
    initial_b_score INTEGER NOT NULL DEFAULT 0,
    first_server TEXT NOT NULL DEFAULT 'A',
    first_server_court TEXT,
    initial_a_side TEXT NOT NULL DEFAULT 'bottom',
    court_points TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    stage TEXT NOT NULL DEFAULT '等待处理',
    progress REAL NOT NULL DEFAULT 0,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS rallies (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    order_index INTEGER NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL NOT NULL,
    server_player TEXT,
    server_court TEXT,
    winner TEXT,
    is_valid INTEGER NOT NULL DEFAULT 1,
    is_let INTEGER NOT NULL DEFAULT 0,
    let_confirmed INTEGER NOT NULL DEFAULT 0,
    confidence REAL NOT NULL DEFAULT 0,
    source TEXT NOT NULL DEFAULT 'ai',
    verified INTEGER NOT NULL DEFAULT 0,
    note TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rallies_project_order
ON rallies(project_id, order_index);

CREATE TABLE IF NOT EXISTS side_swaps (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    time REAL NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS exports (
    id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,
    rally_ids TEXT,
    status TEXT NOT NULL DEFAULT 'queued',
    progress REAL NOT NULL DEFAULT 0,
    output_path TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def init_db() -> None:
    with connection() as conn:
        conn.executescript(SCHEMA)
        rally_columns = {
            row["name"] for row in conn.execute("PRAGMA table_info(rallies)").fetchall()
        }
        if "is_valid" not in rally_columns:
            conn.execute(
                "ALTER TABLE rallies ADD COLUMN is_valid INTEGER NOT NULL DEFAULT 1"
            )
        # Recover jobs that cannot survive an app restart.
        conn.execute(
            "UPDATE projects SET status='failed', stage='服务重启，分析已中断', error='分析任务在服务重启时中断，请重新分析' WHERE status IN ('analyzing','exporting')"
        )
        conn.execute(
            "UPDATE exports SET status='failed', error='导出任务在服务重启时中断，请重新导出' WHERE status IN ('queued','exporting')"
        )
