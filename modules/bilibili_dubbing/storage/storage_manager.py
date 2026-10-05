"""Quản lý đường dẫn và file của module. Mọi thao tác ghi/xóa đều bị giới hạn trong 2 thư mục:
`work/` (file tạm của job) và thư mục thư viện. Không bao giờ chạm vào core/input hay core/output."""
from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Optional

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.domain.errors import FileBusy, InsufficientSpace, NotFound, UnsafePath
from modules.bilibili_dubbing.storage.repositories import SettingsRepository

LIBRARY_ROOT_KEY = "library_root"


class StorageManager:
    # Windows không cho chuyển/xóa file đang được tiến trình khác mở (trình phát, antivirus, ffmpeg vừa xong).
    # Thường chỉ kéo dài vài giây nên thử lại trước khi báo lỗi.
    BUSY_RETRIES = 8
    BUSY_WAIT_S = 0.75

    def __init__(self, settings: BilibiliSettings, settings_repo: SettingsRepository):
        self._settings = settings
        self._settings_repo = settings_repo

    def _retry_busy(self, action, description: str):
        last_error = None
        for attempt in range(self.BUSY_RETRIES):
            try:
                return action()
            except PermissionError as exc:
                last_error = exc
                time.sleep(self.BUSY_WAIT_S)
        raise FileBusy(
            f"{description} đang được chương trình khác sử dụng. Hãy đóng trình phát video đang mở file này rồi bấm Chạy lại."
        ) from last_error

    # ── Thư mục gốc ───────────────────────────────────────────────────────────
    @property
    def work_root(self) -> Path:
        return self._settings.work_dir.resolve()

    @property
    def library_root(self) -> Path:
        configured = self._settings_repo.get(LIBRARY_ROOT_KEY)
        return (Path(configured) if configured else self._settings.default_library_root).resolve()

    @property
    def has_custom_root(self) -> bool:
        return bool(self._settings_repo.get(LIBRARY_ROOT_KEY))

    # ── Đường dẫn con (id do hệ thống sinh, vẫn kiểm tra lại) ─────────────────
    def job_dir(self, job_id: str, create: bool = True) -> Path:
        return self._child(self.work_root, job_id, create)

    def item_dir(self, item_id: str, create: bool = True) -> Path:
        return self._child(self.library_root, item_id, create)

    def item_file(self, item_id: str, relative: Optional[str]) -> Path:
        """Đường dẫn tuyệt đối của một file trong thư viện; báo lỗi nếu thiếu hoặc thoát khỏi thư mục."""
        if not relative:
            raise NotFound("Video này không có file đó.")
        base = self.item_dir(item_id, create=False)
        path = (base / relative).resolve()
        if base != path and base not in path.parents:
            raise UnsafePath("Đường dẫn file không hợp lệ.")
        if not path.is_file():
            raise NotFound("File không còn trên đĩa.")
        return path

    @staticmethod
    def _child(root: Path, name: str, create: bool) -> Path:
        if not name or name in (".", "..") or any(sep in name for sep in ("/", "\\", ":")):
            raise UnsafePath("Tên thư mục không hợp lệ.")
        path = (root / name).resolve()
        if path.parent != root:
            raise UnsafePath("Đường dẫn nằm ngoài thư mục của module.")
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return path

    # ── Ghi / xóa ─────────────────────────────────────────────────────────────
    def move_into_item(self, source: Path, item_id: str, name: str) -> str:
        """Chuyển một file từ thư mục làm việc vào thư viện, trả về tên file tương đối."""
        source = Path(source).resolve()
        if self.work_root not in source.parents:
            raise UnsafePath("Chỉ chuyển được file từ thư mục làm việc của module.")
        target_dir = self.item_dir(item_id)
        target = (target_dir / name).resolve()
        if target.parent != target_dir:
            raise UnsafePath("Tên file đích không hợp lệ.")
        self._retry_busy(lambda: shutil.move(str(source), str(target)), f"File {source.name}")
        return name

    def move_back(self, item_id: str, name: str, destination: Path) -> None:
        """Hoàn tác `move_into_item` khi việc đưa vào thư viện thất bại giữa chừng."""
        source = self.item_dir(item_id, create=False) / name
        destination = Path(destination).resolve()
        if self.work_root not in destination.parents:
            raise UnsafePath("Chỉ hoàn tác được về thư mục làm việc của module.")
        if source.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(destination))

    def remove_item_file(self, item_id: str, relative: str) -> None:
        """Xóa một file của video trong thư viện (ví dụ video gốc giữ kèm). File đang bị giữ thì báo FileBusy."""
        path = self.item_file(item_id, relative)
        self._retry_busy(path.unlink, f"File {path.name}")

    def remove_job_dir(self, job_id: str, strict: bool = False) -> None:
        self._remove_tree(self.job_dir(job_id, create=False), self.work_root, strict)

    def remove_item_dir(self, item_id: str, strict: bool = False) -> None:
        self._remove_tree(self.item_dir(item_id, create=False), self.library_root, strict)

    def _remove_tree(self, path: Path, root: Path, strict: bool) -> None:
        """strict=True: báo lỗi nếu còn file không xóa được (để không mất bản ghi mà file vẫn nằm trên đĩa).
        strict=False: dọn dẹp hết sức, phần còn lại để lần dọn sau."""
        if path.parent != root or path == root:
            raise UnsafePath("Từ chối xóa thư mục ngoài phạm vi của module.")
        if not path.is_dir():
            return
        if not strict:
            shutil.rmtree(path, ignore_errors=True)
            return
        self._retry_busy(lambda: shutil.rmtree(path), "Video")

    # ── Dung lượng ────────────────────────────────────────────────────────────
    @staticmethod
    def dir_size(path: Path) -> int:
        return sum(f.stat().st_size for f in Path(path).rglob("*") if f.is_file()) if Path(path).is_dir() else 0

    def ensure_free_space(self, needed_bytes: Optional[int]) -> None:
        """Video được tải vào work/ rồi chuyển sang thư viện, nên kiểm tra cả hai nơi."""
        required = (needed_bytes or 0) + self._settings.min_free_bytes
        for root in {self.work_root, self.library_root}:
            root.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(root).free
            if free < required:
                raise InsufficientSpace(
                    f"Ổ đĩa chứa {root} chỉ còn {free // 1048576} MB, cần khoảng {required // 1048576} MB."
                )
