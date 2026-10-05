"""Ba nguồn phụ đề gốc: có sẵn trên nền tảng, Whisper bóc băng, file người dùng upload."""
from __future__ import annotations

import gc
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

from modules.bilibili_dubbing.domain.errors import BilibiliError, DependencyMissing
from modules.bilibili_dubbing.subtitles.document import SubtitleDocument

PLATFORM_FILE = "subs.orig.vtt"
UPLOADED_STEM = "uploaded"
UPLOAD_EXTENSIONS = (".srt", ".vtt")


class SubtitleUnavailable(BilibiliError):
    """Nguồn phụ đề đã chọn chưa có dữ liệu: job chờ người dùng upload hoặc chuyển sang Whisper."""

    code = "subtitle_unavailable"
    http_status = 409


@dataclass
class SubtitleResult:
    document: SubtitleDocument
    source_lang: Optional[str]      # None = không rõ, để dịch vụ dịch tự nhận dạng
    note: Optional[str] = None      # điều người dùng nên biết khi duyệt (ví dụ đã phải dùng model nhỏ hơn)


class InsufficientMemory(BilibiliError):
    code = "insufficient_memory"
    http_status = 507


# Từ nặng tới nhẹ. Thiếu RAM thì lùi dần xuống model nhẹ hơn.
WHISPER_SIZES = ("large-v3", "medium", "small", "base", "tiny")
_MEMORY_MARKERS = ("allocate memory", "mkl_malloc", "out of memory", "bad allocation", "bad_alloc", "not enough memory")


def is_memory_error(exc: BaseException) -> bool:
    return isinstance(exc, MemoryError) or any(marker in str(exc).lower() for marker in _MEMORY_MARKERS)


class SubtitleProvider(ABC):
    @abstractmethod
    def obtain(self, work_dir: Path, video_path: Path, lang: Optional[str],
               report: Callable[[str], None]) -> SubtitleResult:
        ...


class PlatformSubtitleProvider(SubtitleProvider):
    """Phụ đề đã được tải cùng video ở bước tải và đổi sang WebVTT."""

    def obtain(self, work_dir, video_path, lang, report):
        path = work_dir / PLATFORM_FILE
        if not path.is_file():
            raise SubtitleUnavailable("Không tải được phụ đề có sẵn của video này.")
        document = SubtitleDocument.from_file(path)
        if not len(document):
            raise SubtitleUnavailable("Phụ đề có sẵn không chứa câu thoại nào.")
        return SubtitleResult(document, lang)


class UploadedSubtitleProvider(SubtitleProvider):
    @staticmethod
    def find(work_dir: Path) -> Optional[Path]:
        return next((work_dir / (UPLOADED_STEM + ext) for ext in UPLOAD_EXTENSIONS
                     if (work_dir / (UPLOADED_STEM + ext)).is_file()), None)

    def obtain(self, work_dir, video_path, lang, report):
        path = self.find(work_dir)
        if path is None:
            raise SubtitleUnavailable("Chờ bạn upload file phụ đề (.srt hoặc .vtt).")
        document = SubtitleDocument.from_file(path)
        if not len(document):
            raise SubtitleUnavailable("File phụ đề đã upload không chứa câu thoại nào.")
        return SubtitleResult(document, None)


# (đường dẫn video, thư mục làm việc, cỡ model) -> danh sách đoạn {start, end, text}
Transcriber = Callable[[Path, Path, str], List[dict]]


def whisper_transcribe(video_path: Path, work_dir: Path, model_size: str) -> List[dict]:
    """Dùng lại hai hàm của `modules/dynamic_subtitle.py` (không sửa file đó)."""
    try:
        import faster_whisper  # noqa: F401 - kiểm tra sớm để báo lỗi dễ hiểu
    except ImportError as exc:
        raise DependencyMissing("Chưa cài faster-whisper. Chạy: python -m pip install faster-whisper") from exc
    from modules.dynamic_subtitle import extract_temp_audio, transcribe_audio_word_level

    wav = work_dir / "audio_16k.wav"
    try:
        extract_temp_audio(str(video_path), str(wav))
        return transcribe_audio_word_level(str(wav), model_size=model_size)
    finally:
        if wav.is_file():
            wav.unlink()


class WhisperSubtitleProvider(SubtitleProvider):
    def __init__(self, model_size: Callable[[], str], transcriber: Optional[Transcriber] = None):
        self._model_size = model_size
        self._transcriber = transcriber or whisper_transcribe

    def obtain(self, work_dir, video_path, lang, report):
        wanted = self._model_size()
        # Thử model đã chọn; máy không đủ RAM để nạp thì lùi xuống model nhẹ hơn thay vì làm hỏng cả job.
        candidates = WHISPER_SIZES[WHISPER_SIZES.index(wanted):] if wanted in WHISPER_SIZES else (wanted,)
        segments = None
        used = wanted
        for size in candidates:
            report(f"Whisper ({size}) đang bóc băng, video dài có thể mất nhiều phút...")
            try:
                segments = self._transcriber(video_path, work_dir, size)
                used = size
                break
            except Exception as exc:  # noqa: BLE001 - chỉ nuốt lỗi thiếu bộ nhớ, lỗi khác ném lại
                if not is_memory_error(exc):
                    raise
                gc.collect()
                report(f"Máy không đủ RAM cho model Whisper {size}, đang thử model nhẹ hơn...")
        if segments is None:
            raise InsufficientMemory(
                f"Máy không đủ RAM để chạy Whisper, kể cả model nhẹ nhất ({candidates[-1]}). "
                "Hãy đóng bớt chương trình đang mở (trình duyệt nhiều tab, game...) rồi bấm Chạy lại."
            )
        document = SubtitleDocument.from_segments(segments)
        if not len(document):
            raise SubtitleUnavailable("Whisper không nhận ra câu thoại nào trong video.")
        note = None
        if used != wanted:
            note = (f"Whisper đã dùng model {used} vì máy không đủ RAM cho {wanted}; "
                    "phụ đề có thể kém chính xác hơn, hãy xem kỹ khi duyệt.")
        return SubtitleResult(document, None, note)
