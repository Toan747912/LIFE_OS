"""Cấu hình tập trung của module (đường dẫn, giới hạn, giá trị mặc định)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# modules/bilibili_dubbing/config.py -> thư mục gốc dự án LIFE_OS
PROJECT_ROOT = Path(__file__).resolve().parents[2]
MODULE_ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class BilibiliSettings:
    """Giá trị cố định khi khởi động. Cấu hình người dùng đổi được nằm trong bảng `settings`."""

    data_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "data" / "bilibili_dubbing")
    web_dir: Path = field(default_factory=lambda: MODULE_ROOT / "web")
    max_urls_per_scan: int = 20
    # Số tập được quét chi tiết ngay; các tập còn lại quét khi người dùng yêu cầu.
    max_probe_per_source: int = 12
    socket_timeout_s: int = 20
    max_jobs_per_request: int = 50
    # Code cũ mặc định "base"; "small" nhận dạng tiếng Trung tốt hơn, đổi lại chậm hơn trên CPU.
    default_whisper_model: str = "small"
    tts_retry_wait_s: float = 1.0
    # Dung lượng trống tối thiểu phải còn lại sau khi trừ phần video sắp tải.
    min_free_bytes: int = 500 * 1024 * 1024

    @property
    def db_path(self) -> Path:
        return self.data_dir / "bilibili.db"

    @property
    def cookie_path(self) -> Path:
        return self.data_dir / "cookies.txt"

    @property
    def work_dir(self) -> Path:
        return self.data_dir / "work"

    @property
    def default_library_root(self) -> Path:
        return self.data_dir / "library"

    @property
    def protected_dirs(self) -> tuple:
        """Thư mục của các chức năng khác trong LIFE_OS: module này không bao giờ đặt thư viện vào đây."""
        return tuple(PROJECT_ROOT / name for name in ("core", "modules", "templates", "yt-subtitle-extension", ".git"))

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.work_dir.mkdir(parents=True, exist_ok=True)
