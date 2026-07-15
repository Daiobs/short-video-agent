from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import close_all_sessions

from app.config import settings
from app.database import Base, SessionLocal, engine as application_engine


@pytest.fixture(autouse=True)
def isolate_application_runtime(monkeypatch, tmp_path: Path):
    """Keep API tests away from the developer database and output archive."""

    runtime_root = tmp_path / "runtime"
    output_dir = runtime_root / "outputs"
    database_path = runtime_root / "short_video_agent.db"
    database_url = f"sqlite:///{database_path.as_posix()}"
    runtime_root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(settings, "output_dir", output_dir)
    monkeypatch.setattr(settings, "uploads_dir", output_dir / "uploads")
    monkeypatch.setattr(settings, "cases_dir", output_dir / "cases")
    monkeypatch.setattr(settings, "downloads_dir", output_dir / "downloads")
    monkeypatch.setattr(settings, "calibration_dir", output_dir / "calibration")
    monkeypatch.setattr(settings, "creator_clones_dir", output_dir / "creator_clones")
    monkeypatch.setattr(settings, "creator_state_dir", output_dir / "creator_state")
    monkeypatch.setattr(settings, "database_url", database_url)
    monkeypatch.setattr(
        "app.services.runtime_settings.LOCAL_SETTINGS_PATH",
        runtime_root / ".local_settings.json",
    )
    settings.ensure_directories()

    test_engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False},
    )
    close_all_sessions()
    SessionLocal.configure(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    try:
        yield
    finally:
        close_all_sessions()
        SessionLocal.configure(bind=application_engine)
        test_engine.dispose()
