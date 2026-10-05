from __future__ import annotations

from typing import Iterable, List

from modules.bilibili_dubbing.domain.errors import UnsupportedUrl
from modules.bilibili_dubbing.sources.base import BaseVideoSource


class SourceRegistry:
    """Chọn nguồn video phù hợp với URL."""

    def __init__(self, sources: Iterable[BaseVideoSource]):
        self._sources: List[BaseVideoSource] = list(sources)

    def resolve(self, url: str) -> BaseVideoSource:
        for source in self._sources:
            if source.can_handle(url):
                return source
        raise UnsupportedUrl("Chỉ hỗ trợ link bilibili.com, bilibili.tv hoặc b23.tv.")

    def by_name(self, name: str) -> BaseVideoSource:
        for source in self._sources:
            if source.name == name:
                return source
        raise UnsupportedUrl(f"Không có nguồn video tên '{name}'.")
