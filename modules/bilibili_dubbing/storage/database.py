"""Kết nối SQLite và migration theo số phiên bản."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, List

# Mỗi phần tử là một phiên bản schema. Chỉ được THÊM phần tử mới, không sửa phần tử cũ.
MIGRATIONS: List[str] = [
    # v1 — schema đầy đủ theo bản thiết kế
    """
    CREATE TABLE settings (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    );
    CREATE TABLE scans (
        id           TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        created_at   TEXT NOT NULL
    );
    CREATE TABLE series (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE library_items (
        id            TEXT PRIMARY KEY,
        title         TEXT NOT NULL,
        note          TEXT NOT NULL DEFAULT '',
        series_id     INTEGER REFERENCES series(id) ON DELETE SET NULL,
        source_url    TEXT,
        episode_label TEXT,
        duration_s    INTEGER,
        quality       TEXT,
        voice         TEXT,
        video_rel     TEXT,
        sub_vi_rel    TEXT,
        sub_orig_rel  TEXT,
        source_rel    TEXT,
        thumb_rel     TEXT,
        size_bytes    INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL
    );
    CREATE TABLE jobs (
        id         TEXT PRIMARY KEY,
        scan_id    TEXT,
        source_url TEXT NOT NULL,
        episode_id TEXT NOT NULL,
        title      TEXT NOT NULL,
        spec_json  TEXT NOT NULL,
        status     TEXT NOT NULL,
        stage      TEXT,
        progress   INTEGER NOT NULL DEFAULT 0,
        message    TEXT NOT NULL DEFAULT '',
        error      TEXT,
        item_id    TEXT REFERENCES library_items(id) ON DELETE SET NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );
    CREATE INDEX idx_jobs_status ON jobs(status);
    CREATE TABLE cues (
        job_id      TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
        idx         INTEGER NOT NULL,
        start_ms    INTEGER NOT NULL,
        end_ms      INTEGER NOT NULL,
        source_text TEXT NOT NULL DEFAULT '',
        vi_text     TEXT NOT NULL DEFAULT '',
        edited      INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (job_id, idx)
    );
    CREATE TABLE tags (
        id   INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE
    );
    CREATE TABLE item_tags (
        item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
        tag_id  INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
        PRIMARY KEY (item_id, tag_id)
    );
    """,
    # v2 — thông tin phát video trong thư viện
    """
    ALTER TABLE library_items ADD COLUMN dubbed INTEGER NOT NULL DEFAULT 0;
    ALTER TABLE library_items ADD COLUMN codec TEXT;
    ALTER TABLE library_items ADD COLUMN browser_playable INTEGER NOT NULL DEFAULT 1;
    ALTER TABLE library_items ADD COLUMN sub_orig_lang TEXT;
    """,
]


class Database:
    """Mỗi thao tác mở một kết nối ngắn, nên dùng được từ nhiều thread (request + worker)."""

    def __init__(self, path: Path):
        self._path = Path(path)
        self._migrate_lock = threading.Lock()
        self._migrated = False

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self._ensure_migrated()
        conn = self._open()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _open(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self._path), timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _ensure_migrated(self) -> None:
        if self._migrated:
            return
        with self._migrate_lock:
            if self._migrated:
                return
            self._path.parent.mkdir(parents=True, exist_ok=True)
            conn = self._open()
            try:
                conn.execute("PRAGMA journal_mode = WAL")
                current = conn.execute("PRAGMA user_version").fetchone()[0]
                for version, script in enumerate(MIGRATIONS, 1):
                    if version > current:
                        conn.executescript("BEGIN;" + script + f"PRAGMA user_version = {version}; COMMIT;")
            finally:
                conn.close()
            self._migrated = True

    def schema_version(self) -> int:
        with self.connect() as conn:
            return conn.execute("PRAGMA user_version").fetchone()[0]
