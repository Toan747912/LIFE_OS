"""Nghiệp vụ quét: tách link, quét từng link độc lập, lưu kết quả để bước chọn dùng lại."""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from modules.bilibili_dubbing.domain.errors import BilibiliError, InvalidRequest
from modules.bilibili_dubbing.domain.models import Episode, ScanResult, SourceScan
from modules.bilibili_dubbing.sources.registry import SourceRegistry
from modules.bilibili_dubbing.storage.repositories import ScanRepository


class ScanService:
    def __init__(
        self,
        registry: SourceRegistry,
        scans: ScanRepository,
        cookie_path: Path,
        max_urls: int,
        max_probe: int,
    ):
        self._registry = registry
        self._scans = scans
        self._cookie_path = cookie_path
        self._max_urls = max_urls
        self._max_probe = max_probe

    @staticmethod
    def parse_urls(raw: str) -> List[str]:
        """Tách chuỗi nhập (mỗi dòng/khoảng trắng/dấu phẩy một link), bỏ trùng, giữ thứ tự."""
        seen, urls = set(), []
        for token in re.split(r"[\s,]+", raw or ""):
            token = token.strip()
            if token and token not in seen:
                seen.add(token)
                urls.append(token)
        return urls

    def scan(self, raw_urls: List[str]) -> ScanResult:
        urls = self.parse_urls("\n".join(raw_urls))
        if not urls:
            raise InvalidRequest("Chưa nhập link nào.")
        if len(urls) > self._max_urls:
            raise InvalidRequest(f"Mỗi lần quét tối đa {self._max_urls} link.")

        result = ScanResult(
            scan_id="sc_" + uuid.uuid4().hex[:12],
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
            cookie_configured=self._cookie_path.is_file(),
        )
        for raw in urls:
            result.results.append(self._scan_one(raw))
        self._scans.save(result)
        return result

    def _scan_one(self, raw: str) -> SourceScan:
        """Lỗi của một link được ghi vào kết quả của chính nó, không làm hỏng các link khác."""
        try:
            source = self._registry.resolve(raw)
            return source.scan(source.normalize(raw), self._max_probe)
        except BilibiliError as exc:
            return SourceScan.failed(raw, exc.message, exc.code)
        except Exception as exc:  # lỗi ngoài dự kiến của thư viện bên ngoài
            return SourceScan.failed(raw, f"Lỗi không xác định khi quét: {exc}", "scan_failed")

    def get(self, scan_id: str) -> ScanResult:
        return self._scans.get(scan_id)

    def probe_episode(self, scan_id: str, result_index: int, episode_id: str) -> Episode:
        """Quét chi tiết một tập chưa được quét (series dài) rồi lưu lại vào kết quả quét."""
        result = self._scans.get(scan_id)
        episode = result.find_episode(result_index, episode_id)
        source = self._registry.by_name(result.results[result_index].source or "")
        try:
            source.probe(episode)
        except BilibiliError as exc:
            episode.probed = True
            episode.accessible = False
            episode.error = exc.message
            episode.error_code = exc.code
        self._scans.save(result)
        return episode
