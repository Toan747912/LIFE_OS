"""Dữ liệu giả có hình dạng giống kết quả của yt-dlp, để test không cần mạng."""
from __future__ import annotations

from typing import Any, Dict

SINGLE_URL = "https://www.bilibili.com/video/BV1xx411c7mD"
SERIES_URL = "https://www.bilibili.com/video/BV1yy411c7mE"
LOCKED_URL = "https://www.bilibili.com/bangumi/play/ep123"


def video_info(title: str = "Video mẫu") -> Dict[str, Any]:
    return {
        "id": "BV1xx411c7mD",
        "title": title,
        "uploader": "Kênh mẫu",
        "duration": 600,
        "thumbnail": "https://example.invalid/thumb.jpg",
        "formats": [
            {"format_id": "30280", "acodec": "mp4a.40.2", "vcodec": "none", "abr": 192, "tbr": 192, "ext": "m4a"},
            {"format_id": "30216", "acodec": "mp4a.40.2", "vcodec": "none", "abr": 64, "tbr": 64, "ext": "m4a"},
            {"format_id": "30080", "vcodec": "avc1.640032", "acodec": "none", "height": 1080, "width": 1920,
             "fps": 30, "tbr": 2000, "ext": "mp4", "filesize": 150_000_000},
            {"format_id": "30077", "vcodec": "hev1.1.6.L120.90", "acodec": "none", "height": 1080, "width": 1920,
             "fps": 30, "tbr": 1200, "ext": "mp4"},
            {"format_id": "100050", "vcodec": "av01.0.08M.08", "acodec": "none", "height": 1080, "width": 1920,
             "fps": 60, "tbr": 1000, "ext": "mp4"},
            {"format_id": "30032", "vcodec": "avc1.64001F", "acodec": "none", "height": 480, "width": 852,
             "fps": 30, "tbr": 500, "ext": "mp4"},
            {"format_id": "30033", "vcodec": "avc1.64001F", "acodec": "none", "height": 480, "width": 852,
             "fps": 30, "tbr": 300, "ext": "mp4"},
        ],
        "subtitles": {
            "danmaku": [{"ext": "xml", "url": "https://example.invalid/1.xml"}],
            "zh-CN": [{"ext": "srt", "data": "1\n00:00:01,000 --> 00:00:02,000\n你好\n"}],
            "ai-zh": [{"ext": "srt", "data": "..."}],
        },
    }


def fake_extractor(url: str, flat: bool) -> Dict[str, Any]:
    from modules.bilibili_dubbing.domain.errors import AccessDenied

    if url.startswith(SERIES_URL):
        if "?p=" in url:
            part = url.split("?p=")[1]
            if part == "2":
                raise AccessDenied("Nội dung yêu cầu tài khoản VIP hoặc đã mua.")
            return video_info(f"Series mẫu p{part}")
        return {
            "_type": "playlist",
            "title": "Series mẫu",
            "entries": [{"_type": "url", "url": f"{SERIES_URL}?p={n}"} for n in (1, 2, 3)],
        }
    if url == LOCKED_URL:
        raise AccessDenied("Nội dung bị khóa vùng, tài khoản của bạn không xem được ở khu vực này.")
    return video_info()


# ── Nguồn giả có tải video ────────────────────────────────────────────────────
import shutil
import subprocess
import threading
from pathlib import Path

from modules.bilibili_dubbing.domain.models import DownloadRequest, DownloadResult
from modules.bilibili_dubbing.sources.bilibili import BilibiliSource

HAS_FFMPEG = shutil.which("ffmpeg") is not None

SAMPLE_SRT = "1\n00:00:00,200 --> 00:00:01,200\nXin chào\n\n2\n00:00:01,300 --> 00:00:01,900\nTạm biệt\n"


def make_sample_video(path: Path, seconds: int = 2) -> None:
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"testsrc=size=160x90:rate=10:duration={seconds}",
         "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}", "-c:v", "libx264", "-pix_fmt", "yuv420p",
         "-c:a", "aac", "-shortest", str(path)],
        check=True,
    )


class FakeDownloadSource(BilibiliSource):
    """Quét bằng dữ liệu giả; tải = sinh một video nhỏ bằng ffmpeg. Có thể giả lập lỗi và tải chậm."""

    def __init__(self):
        super().__init__(extractor=fake_extractor)
        self.fail_times = 0                 # số lần tải kế tiếp sẽ lỗi
        self.gate = None                    # threading.Event: nếu đặt, việc tải chờ tới khi được mở
        self.started = threading.Event()
        self.requests = []

    def download(self, request: DownloadRequest, on_progress) -> DownloadResult:
        from modules.bilibili_dubbing.domain.errors import ScanFailed

        self.requests.append(request)
        self.started.set()
        on_progress(0.1, 1000)
        if self.gate is not None:
            while not self.gate.wait(0.05):
                on_progress(0.2, 2000)      # ném JobCancelled nếu job bị hủy trong lúc chờ
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ScanFailed("Không kết nối được tới Bilibili. Hãy kiểm tra mạng rồi quét lại.")
        video = request.dest_dir / "source.mp4"
        make_sample_video(video)
        subtitle = None
        if request.subtitle_lang:
            subtitle = request.dest_dir / f"source.{request.subtitle_lang}.srt"
            subtitle.write_text(SAMPLE_SRT, encoding="utf-8")
        on_progress(0.99, 9000)
        return DownloadResult(video_path=video, subtitle_path=subtitle, title="Video mẫu", duration_s=None)


# ── Dịch và bóc băng giả ──────────────────────────────────────────────────────
from modules.bilibili_dubbing.subtitles.translator import Translator


class FakeTranslator(Translator):
    """Thêm tiền tố [vi] để nhận ra câu đã qua bước dịch. `fail_texts`: các câu giả lập dịch lỗi."""

    def __init__(self, fail_texts=()):
        self.fail_texts = set(fail_texts)
        self.calls = []

    def translate_batch(self, texts, source_lang, on_progress=None):
        self.calls.append((list(texts), source_lang))
        if on_progress:
            on_progress(len(texts), len(texts))
        return ["" if text in self.fail_texts else f"[vi] {text}" for text in texts]


class FakeTranscriber:
    def __init__(self, segments=None):
        self.segments = segments if segments is not None else [
            {"start": 0.0, "end": 1.0, "text": " 大家好 "},
            {"start": 1.1, "end": 1.9, "text": "再见"},
        ]
        self.calls = []

    def __call__(self, video_path, work_dir, model_size):
        self.calls.append((Path(video_path).name, model_size))
        return self.segments


# ── Giọng đọc giả ─────────────────────────────────────────────────────────────
class FakeSpeaker:
    """Thay edge-tts: sinh file mp3 thật bằng ffmpeg, dài tỉ lệ với số ký tự và ngắn lại khi tăng tốc độ."""

    def __init__(self, ms_per_char: int = 40):
        self.ms_per_char = ms_per_char
        self.calls = []                 # (text, voice, rate)
        self.fail_times = {}            # text -> số lần lỗi còn lại
        self.empty_times = {}           # text -> số lần sinh file rỗng còn lại

    async def __call__(self, text, voice, rate, path):
        self.calls.append((text, voice, rate))
        if self.fail_times.get(text, 0) > 0:
            self.fail_times[text] -= 1
            raise ConnectionError("giả lập mất mạng tới dịch vụ đọc")
        if self.empty_times.get(text, 0) > 0:
            self.empty_times[text] -= 1
            Path(path).write_bytes(b"")
            return
        speed = 1 + int(rate.strip("+%")) / 100
        seconds = max(len(text) * self.ms_per_char / speed, 120) / 1000
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=300:duration={seconds:.3f}",
                        "-c:a", "libmp3lame", "-b:a", "48k", str(path)], check=True)
