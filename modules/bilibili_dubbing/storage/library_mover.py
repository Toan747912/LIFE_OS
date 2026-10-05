"""Chuyển thư viện sang thư mục khác: sao chép, kiểm tra đủ file, đổi cấu hình, rồi mới xóa nơi cũ."""
from __future__ import annotations

import shutil
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.domain.errors import Conflict, InsufficientSpace, InvalidRequest
from modules.bilibili_dubbing.storage.repositories import LibraryRepository, SettingsRepository
from modules.bilibili_dubbing.storage.storage_manager import LIBRARY_ROOT_KEY, StorageManager

ITEM_PREFIX = "it_"


class LibraryMover:
    def __init__(self, settings: BilibiliSettings, storage: StorageManager, library: LibraryRepository,
                 settings_repo: SettingsRepository, pause_jobs: Callable[[], bool], resume_jobs: Callable[[], None]):
        self._settings = settings
        self._storage = storage
        self._library = library
        self._settings_repo = settings_repo
        self._pause_jobs = pause_jobs
        self._resume_jobs = resume_jobs
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._state: Dict[str, Any] = {"status": "idle"}

    def status(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._state)

    def wait(self, timeout: float = 60) -> Dict[str, Any]:
        thread = self._thread
        if thread is not None:
            thread.join(timeout)
        return self.status()

    # ── Kiểm tra đích ─────────────────────────────────────────────────────────
    def validate_target(self, raw: str) -> Path:
        text = (raw or "").strip().strip('"')
        if not text:
            raise InvalidRequest("Chưa nhập đường dẫn thư mục.")
        candidate = Path(text).expanduser()
        if not candidate.is_absolute():
            raise InvalidRequest(r"Hãy nhập đường dẫn tuyệt đối, ví dụ D:\Videos\Bilibili.")
        target = candidate.resolve()
        old = self._storage.library_root
        if target == old:
            raise InvalidRequest("Thư viện đang nằm ở chính thư mục này.")
        if old in target.parents or target in old.parents:
            raise InvalidRequest("Thư mục mới không được nằm trong thư mục thư viện hiện tại, và ngược lại.")
        work = self._storage.work_root
        if target == work or work in target.parents:
            raise InvalidRequest("Không đặt thư viện trong thư mục làm việc tạm của module.")
        for protected in self._settings.protected_dirs:
            protected = protected.resolve()
            if target == protected or protected in target.parents:
                raise InvalidRequest("Không đặt thư viện trong thư mục của các chức năng khác trong LIFE_OS.")
        if target.exists():
            if not target.is_dir():
                raise InvalidRequest("Đường dẫn này là một file, không phải thư mục.")
            foreign = [p.name for p in target.iterdir() if not (p.is_dir() and p.name.startswith(ITEM_PREFIX))]
            if foreign:
                raise InvalidRequest("Thư mục đích phải trống (hoặc là một thư viện cũ của module) để không lẫn "
                                     f"với file khác. Đang có: {', '.join(sorted(foreign)[:3])}.")
        return target

    # ── Chạy ──────────────────────────────────────────────────────────────────
    def start(self, raw: str) -> Dict[str, Any]:
        target = self.validate_target(raw)
        with self._lock:
            if self._state.get("status") == "running":
                raise Conflict("Đang chuyển thư viện, hãy chờ xong.")
            old = self._storage.library_root
            item_ids = [item.id for item in self._library.list()]
            try:
                target.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise InvalidRequest(f"Không tạo được thư mục: {exc}") from exc
            needed = sum(self._storage.dir_size(old / item_id) for item_id in item_ids)
            free = shutil.disk_usage(target).free
            if free < needed + self._settings.min_free_bytes:
                raise InsufficientSpace(f"Ổ đĩa đích chỉ còn {free // 1048576} MB, cần khoảng "
                                        f"{(needed + self._settings.min_free_bytes) // 1048576} MB.")
            if not self._pause_jobs():
                raise Conflict("Đang có job chạy dở. Hãy chờ job xong hoặc hủy nó rồi chuyển thư viện.")
            self._state = {"status": "running", "done": 0, "total": len(item_ids), "current": None,
                           "old_root": str(old), "new_root": str(target), "error": None, "leftover": []}
            self._thread = threading.Thread(target=self._run, args=(old, target, item_ids),
                                            name="bilibili-library-mover", daemon=True)
            self._thread.start()
            return dict(self._state)

    def _set(self, **changes) -> None:
        with self._lock:
            self._state.update(changes)

    def _run(self, old: Path, target: Path, item_ids: List[str]) -> None:
        copied: List[Path] = []
        try:
            for index, item_id in enumerate(item_ids):
                self._set(current=item_id, done=index)
                source = old / item_id
                if not source.is_dir():
                    continue                              # bản ghi không còn file: bỏ qua, không chặn việc chuyển
                destination = target / item_id
                if destination.exists():
                    shutil.rmtree(destination)            # phần sao chép dở của lần trước
                copied.append(destination)
                shutil.copytree(source, destination)
                if self._listing(source) != self._listing(destination):
                    raise OSError(f"Sao chép {item_id} không đủ file.")
            # Chỉ đổi cấu hình khi mọi thứ đã nằm đủ ở nơi mới.
            self._settings_repo.set(LIBRARY_ROOT_KEY, str(target))
        except Exception as exc:  # noqa: BLE001 - mọi lỗi đều phải trả thư viện về trạng thái cũ
            for destination in copied:
                shutil.rmtree(destination, ignore_errors=True)
            self._set(status="failed", error=f"{type(exc).__name__}: {exc}", current=None)
            self._resume_jobs()
            return
        leftover = []
        for item_id in item_ids:                          # nơi mới đã dùng được, giờ mới xóa nơi cũ
            source = old / item_id
            if source.is_dir():
                shutil.rmtree(source, ignore_errors=True)
                if source.exists():
                    leftover.append(item_id)
        self._set(status="done", done=len(item_ids), current=None, leftover=leftover)
        self._resume_jobs()

    @staticmethod
    def _listing(folder: Path) -> dict:
        return {str(f.relative_to(folder)): f.stat().st_size for f in folder.rglob("*") if f.is_file()}
