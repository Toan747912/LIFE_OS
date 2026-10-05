"""Lớp trừu tượng cho một nền tảng video. Thêm nền tảng mới = thêm một lớp con."""
from __future__ import annotations

from abc import ABC, abstractmethod

from typing import Callable, Optional

from modules.bilibili_dubbing.domain.models import DownloadRequest, DownloadResult, Episode, SourceScan

# (tỉ lệ hoàn thành 0..1 hoặc None nếu chưa biết tổng, số byte đã tải). Được phép ném lỗi để dừng việc tải.
ProgressCallback = Callable[[Optional[float], int], None]


class BaseVideoSource(ABC):
    name: str = "base"

    @abstractmethod
    def can_handle(self, url: str) -> bool:
        """URL này có thuộc nền tảng của source không."""

    @abstractmethod
    def normalize(self, raw: str) -> str:
        """Chuẩn hóa chuỗi người dùng nhập thành URL đầy đủ."""

    @abstractmethod
    def scan(self, url: str, max_probe: int) -> SourceScan:
        """Liệt kê các tập của link; quét chi tiết tối đa `max_probe` tập đầu."""

    @abstractmethod
    def probe(self, episode: Episode) -> Episode:
        """Quét chi tiết chất lượng và phụ đề của một tập (ghi vào chính `episode`)."""

    @abstractmethod
    def download(self, request: DownloadRequest, on_progress: ProgressCallback) -> DownloadResult:
        """Tải video (và phụ đề có sẵn nếu được yêu cầu) vào `request.dest_dir`."""
