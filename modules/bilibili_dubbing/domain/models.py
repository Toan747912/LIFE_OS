"""Các đối tượng dữ liệu thuần (không phụ thuộc HTTP hay SQLite)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class FormatOption:
    """Một lựa chọn chất lượng hiển thị cho người dùng ở bước quét."""

    format_id: str
    selector: str               # chuỗi chọn định dạng cho yt-dlp khi tải
    height: int
    width: Optional[int]
    fps: Optional[float]
    codec: str                  # avc | hevc | av1 | other
    ext: str
    size_bytes: Optional[int]
    browser_playable: bool
    label: str


@dataclass
class SubtitleTrack:
    lang: str
    name: str
    kind: str                   # SubtitleKind
    ext: str = "srt"


@dataclass
class Episode:
    episode_id: str
    index: int
    title: str
    url: str
    duration_s: Optional[int] = None
    duration_estimated: bool = False
    thumbnail: Optional[str] = None
    probed: bool = False        # đã quét chi tiết chất lượng/phụ đề chưa
    accessible: bool = True
    error: Optional[str] = None
    error_code: Optional[str] = None
    formats: List[FormatOption] = field(default_factory=list)
    subtitles: List[SubtitleTrack] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Episode":
        data = dict(data)
        data["formats"] = [FormatOption(**f) for f in data.get("formats", [])]
        data["subtitles"] = [SubtitleTrack(**s) for s in data.get("subtitles", [])]
        return cls(**data)


@dataclass
class SourceScan:
    """Kết quả quét của một link."""

    url: str
    ok: bool
    source: Optional[str] = None
    kind: str = "video"         # video | playlist
    title: Optional[str] = None
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    episodes: List[Episode] = field(default_factory=list)

    @classmethod
    def failed(cls, url: str, message: str, code: str) -> "SourceScan":
        return cls(url=url, ok=False, error=message, error_code=code)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SourceScan":
        data = dict(data)
        data["episodes"] = [Episode.from_dict(e) for e in data.get("episodes", [])]
        return cls(**data)


@dataclass
class ScanResult:
    scan_id: str
    created_at: str
    cookie_configured: bool
    results: List[SourceScan] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScanResult":
        data = dict(data)
        data["results"] = [SourceScan.from_dict(r) for r in data.get("results", [])]
        return cls(**data)

    def find_episode(self, result_index: int, episode_id: str) -> Episode:
        from modules.bilibili_dubbing.domain.errors import NotFound

        if not 0 <= result_index < len(self.results):
            raise NotFound("Không tìm thấy link trong kết quả quét.")
        for episode in self.results[result_index].episodes:
            if episode.episode_id == episode_id:
                return episode
        raise NotFound("Không tìm thấy tập trong kết quả quét.")


# ── Tải video ─────────────────────────────────────────────────────────────────
@dataclass
class DownloadRequest:
    url: str
    selector: str                       # chuỗi chọn định dạng đã lấy từ bước quét
    dest_dir: Path
    subtitle_lang: Optional[str] = None  # tải kèm phụ đề có sẵn của nền tảng
    expected_bytes: Optional[int] = None


@dataclass
class DownloadResult:
    video_path: Path
    subtitle_path: Optional[Path] = None
    thumbnail_path: Optional[Path] = None
    title: Optional[str] = None
    duration_s: Optional[int] = None


# ── Job ───────────────────────────────────────────────────────────────────────
@dataclass
class JobSpec:
    """Mọi lựa chọn của người dùng cho một tập, cố định từ lúc tạo job."""

    scan_id: str
    result_index: int
    episode_id: str
    source: str
    url: str
    title: str
    format_id: str
    selector: str
    quality_label: str
    codec: str
    browser_playable: bool
    series_title: Optional[str] = None
    episode_label: Optional[str] = None
    expected_bytes: Optional[int] = None
    subtitle_source: str = "whisper"     # SubtitleSourceType
    subtitle_lang: Optional[str] = None
    voice: str = "vi-VN-HoaiMyNeural"
    orig_vol: float = 0.15
    dub_vol: float = 1.0
    keep_source: bool = False


@dataclass
class Job:
    id: str
    title: str
    spec: JobSpec
    status: str
    created_at: str
    updated_at: str
    stage: Optional[str] = None
    progress: int = 0
    message: str = ""
    error: Optional[str] = None
    item_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        spec = data.pop("spec")
        data.update({
            "source_url": spec["url"],
            "quality_label": spec["quality_label"],
            "subtitle_source": spec["subtitle_source"],
            "subtitle_lang": spec["subtitle_lang"],
            "series_title": spec["series_title"],
            "episode_label": spec["episode_label"],
        })
        return data


# ── Thư viện ──────────────────────────────────────────────────────────────────
@dataclass
class LibraryItem:
    id: str
    title: str
    created_at: str
    note: str = ""
    series_id: Optional[int] = None
    source_url: Optional[str] = None
    episode_label: Optional[str] = None
    duration_s: Optional[int] = None
    quality: Optional[str] = None
    voice: Optional[str] = None
    video_rel: Optional[str] = None
    sub_vi_rel: Optional[str] = None
    sub_orig_rel: Optional[str] = None
    sub_orig_lang: Optional[str] = None
    source_rel: Optional[str] = None
    thumb_rel: Optional[str] = None
    size_bytes: int = 0
    dubbed: bool = False
    codec: Optional[str] = None
    browser_playable: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Dữ liệu trả cho giao diện: không lộ đường dẫn trên đĩa, chỉ cho biết file nào tồn tại."""
        data = asdict(self)
        for key in ("video_rel", "sub_vi_rel", "sub_orig_rel", "source_rel", "thumb_rel"):
            data["has_" + key[:-4]] = bool(data.pop(key))
        return data
