from app import db, store


def test_winner_resolves_invalid_rally_and_invalidating_removes_its_point(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", str(tmp_path / "store.db"))
    db.init_db()
    now = db.utc_now()
    with db.connection() as conn:
        conn.execute(
            "INSERT INTO projects (id, title, source_path, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            ("project-1", "测试比赛", "sample.mp4", now, now),
        )
    store.insert_rallies(
        "project-1",
        [
            {
                "id": "rally-1",
                "start_time": 0,
                "end_time": 5,
                "winner": None,
                "is_valid": False,
                "is_let": True,
                "let_confirmed": True,
                "confidence": 0.8,
                "verified": True,
            }
        ],
    )

    invalid_payload = store.project_payload(store.get_project("project-1"))
    assert invalid_payload["invalid_count"] == 1
    assert invalid_payload["final_score"] == {"A": 0, "B": 0}

    resolved = store.update_rally("rally-1", {"winner": "A"})
    assert resolved is not None
    assert bool(resolved["is_valid"]) is True
    assert bool(resolved["is_let"]) is False
    assert bool(resolved["let_confirmed"]) is True
    assert bool(resolved["verified"]) is True
    resolved_payload = store.project_payload(store.get_project("project-1"))
    assert resolved_payload["invalid_count"] == 0
    assert resolved_payload["final_score"] == {"A": 1, "B": 0}

    invalidated = store.update_rally("rally-1", {"is_valid": False})
    assert invalidated is not None
    assert bool(invalidated["is_valid"]) is False
    assert bool(invalidated["is_let"]) is False
    final_payload = store.project_payload(store.get_project("project-1"))
    assert final_payload["invalid_count"] == 1
    assert final_payload["final_score"] == {"A": 0, "B": 0}
