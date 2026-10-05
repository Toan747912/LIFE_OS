"""Nguồn Bilibili: quét thông tin video bằng yt-dlp (không tải gì ở bước quét)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

from modules.bilibili_dubbing.domain.enums import SubtitleKind
from modules.bilibili_dubbing.domain.errors import (
    AccessDenied,
    BilibiliError,
    ContentUnavailable,
    DependencyMissing,
    ScanFailed,
)
from modules.bilibili_dubbing.domain.models import (
    DownloadRequest,
    DownloadResult,
    Episode,
    FormatOption,
    SourceScan,
    SubtitleTrack,
)
from modules.bilibili_dubbing.sources.base import BaseVideoSource, ProgressCallback

# Hàm lấy metadata: (url, flat) -> dict thông tin. Tách ra để test không cần mạng.
Extractor = Callable[[str, bool], Dict[str, Any]]

_BV_ID = re.compile(r"^(BV[0-9A-Za-z]{10}|av\d+)$")
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
# Kênh không phải phụ đề lời thoại (bình luận chạy trên màn hình, chat trực tiếp).
_NON_SUBTITLE_LANGS = {"danmaku", "live_chat"}
_BROWSER_PLAYABLE_CODECS = {"avc"}

_LANG_NAMES = {
    "zh": "Tiếng Trung", "zh-cn": "Tiếng Trung (giản thể)", "zh-hans": "Tiếng Trung (giản thể)",
    "zh-tw": "Tiếng Trung (phồn thể)", "zh-hant": "Tiếng Trung (phồn thể)", "zh-hk": "Tiếng Trung (Hồng Kông)",
    "en": "Tiếng Anh", "en-us": "Tiếng Anh", "vi": "Tiếng Việt", "ja": "Tiếng Nhật", "ko": "Tiếng Hàn",
    "th": "Tiếng Thái", "id": "Tiếng Indonesia",
}


class BilibiliSource(BaseVideoSource):
    name = "bilibili"
    HOSTS = ("bilibili.com", "b23.tv", "bilibili.tv")

    def __init__(
        self,
        cookie_path: Optional[Path] = None,
        socket_timeout_s: int = 20,
        extractor: Optional[Extractor] = None,
    ):
        self._cookie_path = cookie_path
        self._socket_timeout_s = socket_timeout_s
        self._extract: Extractor = extractor or self._extract_with_ytdlp

    # ── Nhận diện và chuẩn hóa URL ────────────────────────────────────────────
    def normalize(self, raw: str) -> str:
        value = raw.strip()
        if _BV_ID.match(value):
            return f"https://www.bilibili.com/video/{value}"
        if not re.match(r"^https?://", value, re.IGNORECASE):
            value = "https://" + value
        return value

    def can_handle(self, url: str) -> bool:
        try:
            parsed = urlparse(self.normalize(url))
        except ValueError:
            return False
        host = (parsed.hostname or "").lower()
        return parsed.scheme in ("http", "https") and any(
            host == h or host.endswith("." + h) for h in self.HOSTS
        )

    # ── Quét ──────────────────────────────────────────────────────────────────
    def scan(self, url: str, max_probe: int) -> SourceScan:
        info = self._extract(url, True)
        result = SourceScan(
            url=url,
            ok=True,
            source=self.name,
            title=info.get("title"),
            uploader=info.get("uploader") or info.get("channel"),
            thumbnail=info.get("thumbnail"),
        )
        if info.get("_type") in ("playlist", "multi_video"):
            result.kind = "playlist"
            entries = [e for e in (info.get("entries") or []) if e]
            for index, entry in enumerate(entries, 1):
                result.episodes.append(self._episode_from_flat(entry, index))
            if not result.episodes:
                raise ContentUnavailable("Link không chứa video nào xem được.")
            for episode in result.episodes[:max_probe]:
                self._probe_safely(episode)
        else:
            episode = Episode(episode_id="p1", index=1, title=info.get("title") or "Video", url=url)
            self._fill_details(episode, info)
            result.episodes.append(episode)
        if not result.thumbnail:
            result.thumbnail = next((e.thumbnail for e in result.episodes if e.thumbnail), None)
        return result

    def probe(self, episode: Episode) -> Episode:
        info = self._extract(episode.url, False)
        self._fill_details(episode, info)
        return episode

    def _probe_safely(self, episode: Episode) -> None:
        """Một tập lỗi (khóa vùng, VIP...) không làm hỏng cả lần quét."""
        try:
            self.probe(episode)
        except BilibiliError as exc:
            episode.probed = True
            episode.accessible = False
            episode.error = exc.message
            episode.error_code = exc.code

    # ── Chuyển dữ liệu yt-dlp sang mô hình của module ─────────────────────────
    @staticmethod
    def _episode_from_flat(entry: Dict[str, Any], index: int) -> Episode:
        url = entry.get("url") or entry.get("webpage_url") or ""
        return Episode(
            episode_id=f"p{index}",
            index=index,
            title=entry.get("title") or f"Tập {index}",
            url=url,
            duration_s=_to_int(entry.get("duration")),
            thumbnail=entry.get("thumbnail"),
        )

    def _fill_details(self, episode: Episode, info: Dict[str, Any]) -> None:
        episode.title = info.get("title") or episode.title
        duration = _to_int(info.get("duration"))
        if duration:
            episode.duration_s, episode.duration_estimated = duration, False
        elif not episode.duration_s:
            # Một số trang (bilibili.tv) không trả thời lượng: ước lượng từ dung lượng và bitrate.
            episode.duration_s = _estimate_duration(info.get("formats") or [])
            episode.duration_estimated = episode.duration_s is not None
        episode.thumbnail = info.get("thumbnail") or episode.thumbnail
        episode.formats = self.build_format_options(info.get("formats") or [], episode.duration_s)
        episode.subtitles = self.build_subtitle_tracks(
            info.get("subtitles") or {}, info.get("automatic_captions") or {}
        )
        episode.probed = True
        episode.accessible = bool(episode.formats)
        if not episode.formats:
            episode.error = "Không lấy được định dạng video nào (có thể cần đăng nhập hoặc VIP)."
            episode.error_code = AccessDenied.code
        else:
            episode.error = None
            episode.error_code = None

    @staticmethod
    def build_format_options(formats: List[Dict[str, Any]], duration_s: Optional[int]) -> List[FormatOption]:
        """Gom các luồng video theo (độ phân giải, codec), giữ luồng bitrate cao nhất mỗi nhóm."""
        def has(stream: Dict[str, Any], key: str) -> bool:
            return stream.get(key) not in (None, "none")

        audio_only = [f for f in formats if has(f, "acodec") and not has(f, "vcodec")]
        best_audio = max(audio_only, key=lambda f: _kbps(f) or 0, default=None)
        audio_size = _stream_size(best_audio, duration_s) if best_audio else 0

        best: Dict[tuple, Dict[str, Any]] = {}
        for stream in formats:
            if not has(stream, "vcodec") or not stream.get("height"):
                continue
            key = (int(stream["height"]), _codec_family(stream.get("vcodec")))
            current = best.get(key)
            if current is None or (_kbps(stream) or 0) > (_kbps(current) or 0):
                best[key] = stream

        options: List[FormatOption] = []
        for (height, codec), stream in best.items():
            muxed = has(stream, "acodec")
            video_size = _stream_size(stream, duration_s)
            size = None
            if video_size is not None:
                size = video_size + (0 if muxed else (audio_size or 0))
            fps = stream.get("fps")
            label = f"{height}p · {codec.upper()}"
            if fps and fps > 30:
                label += f" · {round(fps)}fps"
            format_id = str(stream.get("format_id"))
            options.append(FormatOption(
                format_id=format_id,
                selector=format_id if muxed else f"{format_id}+bestaudio",
                height=height,
                width=_to_int(stream.get("width")),
                fps=fps,
                codec=codec,
                ext=stream.get("ext") or "mp4",
                size_bytes=size,
                browser_playable=codec in _BROWSER_PLAYABLE_CODECS,
                label=label,
            ))
        options.sort(key=lambda o: (o.height, o.browser_playable), reverse=True)
        return options

    @staticmethod
    def build_subtitle_tracks(subtitles: Dict[str, Any], automatic: Dict[str, Any]) -> List[SubtitleTrack]:
        tracks: List[SubtitleTrack] = []
        seen = set()
        for source, default_kind in ((subtitles, SubtitleKind.UPLOADED), (automatic, SubtitleKind.AUTO)):
            for lang, variants in source.items():
                if lang in _NON_SUBTITLE_LANGS or lang in seen or not variants:
                    continue
                seen.add(lang)
                is_ai = lang.lower().startswith("ai-")
                kind = SubtitleKind.AUTO if is_ai else default_kind
                base = lang[3:] if is_ai else lang
                name = _LANG_NAMES.get(base.lower(), base)
                if kind is SubtitleKind.AUTO:
                    name += " (AI tự tạo)"
                tracks.append(SubtitleTrack(
                    lang=lang, name=name, kind=kind.value, ext=(variants[0] or {}).get("ext") or "srt",
                ))
        return tracks

    # ── Gọi yt-dlp ────────────────────────────────────────────────────────────
    def _extract_with_ytdlp(self, url: str, flat: bool) -> Dict[str, Any]:
        try:
            import yt_dlp
        except ImportError as exc:
            raise DependencyMissing("Chưa cài yt-dlp. Chạy: pip install -r requirements.txt") from exc

        options: Dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            # yt-dlp chỉ hỏi danh sách phụ đề khi hai cờ này bật; skip_download nên không ghi file nào.
            "writesubtitles": True,
            "writeautomaticsub": True,
            "extract_flat": "in_playlist" if flat else False,
            "noplaylist": not flat,
            "socket_timeout": self._socket_timeout_s,
            "ignore_no_formats_error": True,
            "logger": _SilentLogger(),
        }
        if self._cookie_path and self._cookie_path.is_file():
            options["cookiefile"] = str(self._cookie_path)
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise ContentUnavailable("Không lấy được thông tin video.")
                if info.get("entries") is not None:
                    info["entries"] = list(info["entries"])
                return ydl.sanitize_info(info)
        except yt_dlp.utils.DownloadError as exc:
            raise self.classify_error(str(exc)) from exc

    # ── Tải ───────────────────────────────────────────────────────────────────
    _VIDEO_EXTS = (".mp4", ".mkv", ".webm", ".flv", ".mov")
    _SUBTITLE_EXTS = (".srt", ".ass", ".vtt", ".ssa")
    _IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp")

    def download(self, request: DownloadRequest, on_progress: ProgressCallback) -> DownloadResult:
        try:
            import yt_dlp
        except ImportError as exc:
            raise DependencyMissing("Chưa cài yt-dlp. Chạy: python -m pip install -r requirements.txt") from exc

        request.dest_dir.mkdir(parents=True, exist_ok=True)
        finished_bytes, current_bytes = [0], [0]

        def hook(event: Dict[str, Any]) -> None:
            status = event.get("status")
            if status == "downloading":
                current_bytes[0] = event.get("downloaded_bytes") or 0
            elif status == "finished":
                finished_bytes[0] += event.get("total_bytes") or event.get("downloaded_bytes") or current_bytes[0]
                current_bytes[0] = 0
            got = finished_bytes[0] + current_bytes[0]
            fraction = min(got / request.expected_bytes, 0.99) if request.expected_bytes else None
            on_progress(fraction, got)

        try:
            with yt_dlp.YoutubeDL(self.build_download_options(request, hook)) as ydl:
                info = ydl.sanitize_info(ydl.extract_info(request.url, download=True)) or {}
        except yt_dlp.utils.DownloadError as exc:
            raise self.classify_error(str(exc)) from exc

        video = self._first_file(request.dest_dir, self._VIDEO_EXTS)
        if video is None:
            raise ScanFailed("Tải xong nhưng không thấy file video. Hãy thử lại hoặc chọn chất lượng khác.")
        return DownloadResult(
            video_path=video,
            subtitle_path=self._first_file(request.dest_dir, self._SUBTITLE_EXTS),
            thumbnail_path=self._first_file(request.dest_dir, self._IMAGE_EXTS),
            title=info.get("title"),
            duration_s=_to_int(info.get("duration")),
        )

    def build_download_options(self, request: DownloadRequest, hook: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        options: Dict[str, Any] = {
            "format": request.selector,           # đúng định dạng người dùng đã chọn, không tự đổi sang cái khác
            "outtmpl": str(request.dest_dir / "source.%(ext)s"),
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "noprogress": True,
            "logger": _SilentLogger(),
            "progress_hooks": [hook],
            "socket_timeout": self._socket_timeout_s,
            "retries": 3,
            "fragment_retries": 3,
            "continuedl": True,                   # chạy lại job thì tải tiếp phần còn thiếu
            "writethumbnail": True,
            "postprocessors": [{"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"}],
        }
        if request.subtitle_lang:
            options.update(
                writesubtitles=True, writeautomaticsub=True,
                subtitleslangs=[request.subtitle_lang], subtitlesformat="srt/ass/vtt/best",
            )
        if self._cookie_path and self._cookie_path.is_file():
            options["cookiefile"] = str(self._cookie_path)
        return options

    @staticmethod
    def _first_file(folder: Path, extensions: tuple) -> Optional[Path]:
        matches = sorted(
            f for f in folder.glob("source*")
            if f.is_file() and f.suffix.lower() in extensions and not f.name.endswith(".part")
        )
        return matches[0] if matches else None

    @staticmethod
    def classify_error(raw_message: str) -> BilibiliError:
        """Đổi thông báo lỗi của yt-dlp thành lỗi có nghĩa với người dùng."""
        message = _ANSI.sub("", raw_message).replace("ERROR: ", "").strip()
        lower = message.lower()
        if any(k in lower for k in ("geo", "region", "not available in your", "地区", "地域")):
            return AccessDenied("Nội dung bị khóa vùng, tài khoản của bạn không xem được ở khu vực này.")
        if any(k in lower for k in ("premium", "vip", "大会员", "paid", "purchase")):
            return AccessDenied("Nội dung yêu cầu tài khoản VIP hoặc đã mua.")
        if any(k in lower for k in ("login", "logged in", "cookies", "sign in")):
            return AccessDenied("Nội dung yêu cầu đăng nhập. Hãy nhập cookie ở tab Cài đặt.")
        if "drm" in lower:
            return AccessDenied("Nội dung được bảo vệ DRM nên không tải được.")
        if any(k in lower for k in ("404", "not found", "does not exist", "removed", "deleted", "不存在")):
            return ContentUnavailable("Video không tồn tại hoặc đã bị xóa.")
        if "ffmpeg" in lower or "ffprobe" in lower:
            return DependencyMissing("Cần ffmpeg để ghép video và âm thanh. Hãy cài ffmpeg và thêm vào PATH.")
        if "requested format is not available" in lower:
            return ContentUnavailable("Chất lượng đã chọn không còn khả dụng. Hãy quét lại link và chọn lại.")
        if "unsupported url" in lower:
            return ContentUnavailable("Link này không phải trang video Bilibili được hỗ trợ.")
        if any(k in lower for k in ("unable to connect", "timed out", "connection", "proxy", "getaddrinfo", "ssl")):
            return ScanFailed("Không kết nối được tới Bilibili. Hãy kiểm tra mạng rồi quét lại.")
        message = message.split("; please report this issue")[0]
        return ScanFailed(f"Không quét được link: {message[:300]}")


class _SilentLogger:
    """yt-dlp ghi lỗi qua logger; lỗi đã được đổi thành BilibiliError nên không in lặp ra console."""

    def debug(self, message: str) -> None:
        pass

    def info(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def _to_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _codec_family(vcodec: Optional[str]) -> str:
    codec = (vcodec or "").lower()
    if codec.startswith(("avc", "h264")):
        return "avc"
    if codec.startswith(("hev", "hvc", "h265")):
        return "hevc"
    if codec.startswith("av01"):
        return "av1"
    return "other"


def _kbps(stream: Dict[str, Any]) -> Optional[float]:
    """Bitrate theo kbps. Extractor bilibili.tv trả bit/giây thay vì kbps nên phải quy đổi."""
    value = stream.get("tbr") or stream.get("vbr") or stream.get("abr")
    if not value:
        return None
    # Không luồng video thực tế nào vượt 100 Mbps, nên số lớn hơn mức đó là đang tính bằng bit/giây.
    return value / 1000 if value > 100_000 else float(value)


def _estimate_duration(formats: List[Dict[str, Any]]) -> Optional[int]:
    """Ước lượng thô: bitrate khai báo thường là mức đỉnh nên kết quả có thể ngắn hơn thực tế."""
    for stream in formats:
        size = stream.get("filesize") or stream.get("filesize_approx")
        bitrate_kbps = _kbps(stream)
        if size and bitrate_kbps:
            seconds = int(size * 8 / (bitrate_kbps * 1000))
            if 10 <= seconds <= 12 * 3600:
                return seconds
    return None


def _stream_size(stream: Optional[Dict[str, Any]], duration_s: Optional[int]) -> Optional[int]:
    if not stream:
        return None
    size = stream.get("filesize") or stream.get("filesize_approx")
    if size:
        return int(size)
    bitrate_kbps = _kbps(stream)
    if bitrate_kbps and duration_s:
        return int(bitrate_kbps * 1000 / 8 * duration_s)
    return None
