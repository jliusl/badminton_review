import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app import db
from app.config import DATA_DIR, TEMP_DIR
from app.main import app


def test_upload_temp_directory_uses_project_data_directory():
    assert TEMP_DIR == DATA_DIR / "tmp"
    assert Path(tempfile.gettempdir()) == TEMP_DIR


def test_malformed_multipart_returns_actionable_message(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "upload-test.db")
    with TestClient(app) as client:
        response = client.post(
            "/api/projects/upload",
            content=b"not a valid multipart body",
            headers={"content-type": "multipart/form-data; boundary=broken"},
        )
    assert response.status_code == 400
    assert response.json()["detail"] == (
        "上传文件解析失败。请确认数据盘有足够剩余空间，并重新上传视频。"
    )
