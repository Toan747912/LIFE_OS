"""Repository: chỉ đọc/ghi dữ liệu, không chứa logic nghiệp vụ."""
from __future__ import annotations

import json
from typing import Dict, Optional

from modules.bilibili_dubbing.domain.errors import NotFound
from modules.bilibili_dubbing.domain.models import ScanResult
from modules.bilibili_dubbing.storage.database import Database


class SettingsRepository:
    def __init__(self, db: Database):
        self._db = db

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._db.connect() as conn:
            row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

    def set(self, key: str, value: str) -> None:
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    def all(self) -> Dict[str, str]:
        with self._db.connect() as conn:
            rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {row["key"]: row["value"] for row in rows}


class ScanRepository:
    # Chỉ giữ các lần quét gần nhất; kết quả quét cũ không còn giá trị.
    KEEP_LATEST = 50

    def __init__(self, db: Database):
        self._db = db

    def save(self, scan: ScanResult) -> None:
        payload = json.dumps(scan.to_dict(), ensure_ascii=False)
        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO scans(id, payload_json, created_at) VALUES(?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET payload_json = excluded.payload_json",
                (scan.scan_id, payload, scan.created_at),
            )
            conn.execute(
                "DELETE FROM scans WHERE id NOT IN "
                "(SELECT id FROM scans ORDER BY created_at DESC, rowid DESC LIMIT ?)",
                (self.KEEP_LATEST,),
            )

    def get(self, scan_id: str) -> ScanResult:
        with self._db.connect() as conn:
            row = conn.execute("SELECT payload_json FROM scans WHERE id = ?", (scan_id,)).fetchone()
        if row is None:
            raise NotFound("Kết quả quét không còn tồn tại, hãy quét lại.")
        return ScanResult.from_dict(json.loads(row["payload_json"]))


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class JobRepository:
    _UPDATABLE = {"status", "stage", "progress", "message", "error", "item_id"}

    def __init__(self, db: Database):
        self._db = db

    @staticmethod
    def _from_row(row) -> "Job":
        from modules.bilibili_dubbing.domain.models import Job, JobSpec

        return Job(
            id=row["id"], title=row["title"], spec=JobSpec(**json.loads(row["spec_json"])),
            status=row["status"], stage=row["stage"], progress=row["progress"], message=row["message"],
            error=row["error"], item_id=row["item_id"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def create(self, job) -> None:
        from dataclasses import asdict

        with self._db.connect() as conn:
            conn.execute(
                "INSERT INTO jobs(id, scan_id, source_url, episode_id, title, spec_json, status, stage, progress,"
                " message, error, item_id, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (job.id, job.spec.scan_id, job.spec.url, job.spec.episode_id, job.title,
                 json.dumps(asdict(job.spec), ensure_ascii=False), job.status, job.stage, job.progress,
                 job.message, job.error, job.item_id, job.created_at, job.updated_at),
            )

    def get(self, job_id: str):
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if row is None:
            raise NotFound("Không tìm thấy job.")
        return self._from_row(row)

    def list(self):
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def ids_with_status(self, statuses) -> list:
        marks = ",".join("?" for _ in statuses)
        with self._db.connect() as conn:
            rows = conn.execute(
                f"SELECT id FROM jobs WHERE status IN ({marks}) ORDER BY created_at, rowid",
                [str(getattr(s, "value", s)) for s in statuses],
            ).fetchall()
        return [row["id"] for row in rows]

    def update(self, job_id: str, **fields) -> None:
        unknown = set(fields) - self._UPDATABLE
        if unknown:
            raise ValueError(f"Không được cập nhật cột: {sorted(unknown)}")
        if "status" in fields:
            fields["status"] = str(getattr(fields["status"], "value", fields["status"]))
        fields["updated_at"] = _now()
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._db.connect() as conn:
            conn.execute(f"UPDATE jobs SET {assignments} WHERE id = ?", [*fields.values(), job_id])

    def update_spec(self, job_id: str, spec) -> None:
        from dataclasses import asdict

        with self._db.connect() as conn:
            conn.execute("UPDATE jobs SET spec_json = ?, updated_at = ? WHERE id = ?",
                         (json.dumps(asdict(spec), ensure_ascii=False), _now(), job_id))

    def reset_running(self, running_statuses, queued_status) -> int:
        """Server vừa khởi động: job đang chạy dở quay về hàng đợi, stage đã xong sẽ được bỏ qua."""
        marks = ",".join("?" for _ in running_statuses)
        with self._db.connect() as conn:
            cursor = conn.execute(
                f"UPDATE jobs SET status = ?, message = ?, updated_at = ? WHERE status IN ({marks})",
                [str(getattr(queued_status, "value", queued_status)), "Tiếp tục sau khi khởi động lại", _now(),
                 *[str(getattr(s, "value", s)) for s in running_statuses]],
            )
            return cursor.rowcount

    def delete(self, job_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))


class LibraryRepository:
    _COLUMNS = (
        "id", "title", "note", "series_id", "source_url", "episode_label", "duration_s", "quality", "voice",
        "video_rel", "sub_vi_rel", "sub_orig_rel", "source_rel", "thumb_rel", "size_bytes", "created_at",
        "dubbed", "codec", "browser_playable", "sub_orig_lang",
    )
    _BOOLEANS = ("dubbed", "browser_playable")

    def __init__(self, db: Database):
        self._db = db

    def _from_row(self, row) -> "LibraryItem":
        from modules.bilibili_dubbing.domain.models import LibraryItem

        data = {name: row[name] for name in self._COLUMNS}
        for name in self._BOOLEANS:
            data[name] = bool(data[name])
        return LibraryItem(**data)

    def create(self, item) -> None:
        values = [getattr(item, name) for name in self._COLUMNS]
        values = [int(v) if isinstance(v, bool) else v for v in values]
        marks = ",".join("?" for _ in self._COLUMNS)
        with self._db.connect() as conn:
            conn.execute(f"INSERT INTO library_items({', '.join(self._COLUMNS)}) VALUES({marks})", values)

    def get(self, item_id: str):
        with self._db.connect() as conn:
            row = conn.execute("SELECT * FROM library_items WHERE id = ?", (item_id,)).fetchone()
        if row is None:
            raise NotFound("Không tìm thấy video trong thư viện.")
        return self._from_row(row)

    def list(self):
        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM library_items ORDER BY created_at DESC, rowid DESC").fetchall()
        return [self._from_row(row) for row in rows]

    def delete(self, item_id: str) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM library_items WHERE id = ?", (item_id,))

    _UPDATABLE = {"title", "note", "series_id", "size_bytes", "source_rel"}

    def update(self, item_id: str, **fields) -> None:
        unknown = set(fields) - self._UPDATABLE
        if unknown:
            raise ValueError(f"Không được cập nhật cột: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{name} = ?" for name in fields)
        with self._db.connect() as conn:
            conn.execute(f"UPDATE library_items SET {assignments} WHERE id = ?", [*fields.values(), item_id])


class TaxonomyRepository:
    """Series (mỗi video thuộc tối đa một series) và tag (nhiều-nhiều). Tên không phân biệt hoa thường."""

    def __init__(self, db: Database):
        self._db = db

    @staticmethod
    def _find(conn, table: str, name: str):
        wanted = name.casefold()
        for row in conn.execute(f"SELECT id, name FROM {table}").fetchall():
            if row["name"].casefold() == wanted:
                return row
        return None

    def _get_or_create(self, conn, table: str, name: str) -> int:
        row = self._find(conn, table, name)
        if row is not None:
            return row["id"]
        return conn.execute(f"INSERT INTO {table}(name) VALUES(?)", (name,)).lastrowid

    # ── Series ────────────────────────────────────────────────────────────────
    def list_series(self) -> list:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT s.id, s.name, COUNT(i.id) AS item_count FROM series s "
                "LEFT JOIN library_items i ON i.series_id = s.id GROUP BY s.id ORDER BY s.name COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    def get_or_create_series(self, name: str) -> int:
        with self._db.connect() as conn:
            return self._get_or_create(conn, "series", name)

    def rename_series(self, series_id: int, name: str) -> None:
        with self._db.connect() as conn:
            if conn.execute("SELECT 1 FROM series WHERE id = ?", (series_id,)).fetchone() is None:
                raise NotFound("Không tìm thấy series.")
            clash = self._find(conn, "series", name)
            if clash is not None and clash["id"] != series_id:
                from modules.bilibili_dubbing.domain.errors import Conflict

                raise Conflict("Đã có series khác mang tên này.")
            conn.execute("UPDATE series SET name = ? WHERE id = ?", (name, series_id))

    def delete_series(self, series_id: int) -> None:
        """Chỉ xóa nhóm; video trong series được giữ lại và trở thành không thuộc series nào."""
        with self._db.connect() as conn:
            if conn.execute("DELETE FROM series WHERE id = ?", (series_id,)).rowcount == 0:
                raise NotFound("Không tìm thấy series.")

    def series_names(self) -> dict:
        with self._db.connect() as conn:
            return {row["id"]: row["name"] for row in conn.execute("SELECT id, name FROM series").fetchall()}

    # ── Tag ───────────────────────────────────────────────────────────────────
    def list_tags(self) -> list:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT t.id, t.name, COUNT(it.item_id) AS item_count FROM tags t "
                "LEFT JOIN item_tags it ON it.tag_id = t.id GROUP BY t.id ORDER BY t.name COLLATE NOCASE"
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_tag(self, tag_id: int) -> None:
        with self._db.connect() as conn:
            if conn.execute("DELETE FROM tags WHERE id = ?", (tag_id,)).rowcount == 0:
                raise NotFound("Không tìm thấy tag.")

    def set_item_tags(self, item_id: str, names: list) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM item_tags WHERE item_id = ?", (item_id,))
            for name in names:
                conn.execute("INSERT OR IGNORE INTO item_tags(item_id, tag_id) VALUES(?, ?)",
                             (item_id, self._get_or_create(conn, "tags", name)))
            # Tag không còn video nào dùng thì bỏ, để danh sách tag không đầy rác.
            conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT tag_id FROM item_tags)")

    def tags_by_item(self) -> dict:
        with self._db.connect() as conn:
            rows = conn.execute(
                "SELECT it.item_id, t.name FROM item_tags it JOIN tags t ON t.id = it.tag_id ORDER BY t.name COLLATE NOCASE"
            ).fetchall()
        result: dict = {}
        for row in rows:
            result.setdefault(row["item_id"], []).append(row["name"])
        return result


class CueRepository:
    """Các câu phụ đề của một job (bảng `cues`), dùng cho bước dịch và màn hình duyệt."""

    def __init__(self, db: Database):
        self._db = db

    def replace_all(self, job_id: str, cues) -> None:
        with self._db.connect() as conn:
            conn.execute("DELETE FROM cues WHERE job_id = ?", (job_id,))
            conn.executemany(
                "INSERT INTO cues(job_id, idx, start_ms, end_ms, source_text, vi_text, edited) VALUES(?,?,?,?,?,?,?)",
                [(job_id, c.idx, c.start_ms, c.end_ms, c.source_text, c.vi_text, int(c.edited)) for c in cues],
            )

    def list(self, job_id: str):
        from modules.bilibili_dubbing.subtitles.document import Cue

        with self._db.connect() as conn:
            rows = conn.execute("SELECT * FROM cues WHERE job_id = ? ORDER BY idx", (job_id,)).fetchall()
        return [Cue(idx=r["idx"], start_ms=r["start_ms"], end_ms=r["end_ms"], source_text=r["source_text"],
                    vi_text=r["vi_text"], edited=bool(r["edited"])) for r in rows]

    def count(self, job_id: str) -> int:
        with self._db.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM cues WHERE job_id = ?", (job_id,)).fetchone()[0]

    def set_translations(self, job_id: str, texts_by_idx: dict) -> None:
        """Kết quả dịch máy: không đánh dấu `edited`."""
        with self._db.connect() as conn:
            conn.executemany("UPDATE cues SET vi_text = ? WHERE job_id = ? AND idx = ?",
                             [(text, job_id, idx) for idx, text in texts_by_idx.items()])

    def save_edits(self, job_id: str, texts_by_idx: dict) -> int:
        """Người dùng sửa: chỉ đánh dấu `edited` cho câu thực sự thay đổi. Trả về số câu đã đổi."""
        with self._db.connect() as conn:
            changed = 0
            for idx, text in texts_by_idx.items():
                changed += conn.execute(
                    "UPDATE cues SET vi_text = ?, edited = 1 WHERE job_id = ? AND idx = ? AND vi_text <> ?",
                    (text, job_id, idx, text),
                ).rowcount
            return changed
