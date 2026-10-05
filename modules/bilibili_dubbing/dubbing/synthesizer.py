"""Sinh giọng đọc tiếng Việt cho từng câu phụ đề ĐÃ DUYỆT (không dịch lại như `generate_tts_for_subtitles` cũ).

Giữ nguyên tham số khớp tốc độ của bản cũ: giọng đọc dài hơn khung thời gian quá 5% thì đọc lại nhanh hơn,
tối đa +50%. Khác bản cũ: thử lại khi lỗi, báo rõ câu nào thất bại, và chạy vài câu song song cho nhanh.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Awaitable, Callable, Dict, List, Optional, Sequence

from modules.bilibili_dubbing.domain.errors import BilibiliError, DependencyMissing
from modules.bilibili_dubbing.subtitles.document import Cue

SPEED_TOLERANCE = 1.05       # cho phép dài hơn khung 5%
MAX_SPEED_UP_PERCENT = 50    # tăng tốc tối đa để giọng không méo
MIN_WINDOW_MS = 400          # khung quá ngắn thì không ép tốc độ
PARTIAL_FILE = "tts.partial.json"

# (văn bản, giọng, tốc độ dạng "+20%", file mp3 đích)
SpeakFn = Callable[[str, str, str, Path], Awaitable[None]]
# file âm thanh -> độ dài tính bằng mili giây (None nếu không đọc được)
MeasureFn = Callable[[Path], Optional[int]]
ProgressFn = Callable[[int, int], None]


class TtsFailed(BilibiliError):
    code = "tts_failed"
    http_status = 502


@dataclass
class Clip:
    idx: int
    start_ms: int
    end_ms: int
    text: str
    audio_file: str
    audio_ms: int
    rate: str


async def edge_speak(text: str, voice: str, rate: str, path: Path) -> None:
    try:
        import edge_tts
    except ImportError as exc:
        raise DependencyMissing("Chưa cài edge-tts. Chạy: python -m pip install edge-tts") from exc
    await edge_tts.Communicate(text, voice, rate=rate).save(str(path))


def sanitize(text: str) -> str:
    """Dùng lại hàm làm sạch của pipeline cũ (`tts_generator.sanitize_vietnamese_text`)."""
    try:
        from modules.video_dubbing.tts_generator import sanitize_vietnamese_text
    except ImportError as exc:
        raise DependencyMissing(f"Không nạp được module lồng tiếng cũ của LIFE_OS: {exc}") from exc
    return sanitize_vietnamese_text(text)


def speaking_windows(cues: Sequence[Cue]) -> Dict[int, int]:
    """Khung thời gian cho mỗi câu: tới lúc câu kế tiếp bắt đầu (tận dụng khoảng lặng giữa hai câu),
    nhưng không ngắn hơn chính độ dài của câu."""
    windows: Dict[int, int] = {}
    ordered = sorted(cues, key=lambda c: c.start_ms)
    for cue, following in zip(ordered, list(ordered[1:]) + [None]):
        own = cue.end_ms - cue.start_ms
        until_next = (following.start_ms - cue.start_ms) if following else own
        windows[cue.idx] = max(own, until_next)
    return windows


class TtsSynthesizer:
    def __init__(self, measure: MeasureFn, speak: Optional[SpeakFn] = None, concurrency: int = 3,
                 retries: int = 3, retry_wait_s: float = 1.0, batch_size: int = 12):
        self._measure = measure
        self._speak = speak or edge_speak
        self._concurrency = concurrency
        self._retries = retries
        self._retry_wait_s = retry_wait_s
        self._batch_size = batch_size

    def synthesize(self, cues: Sequence[Cue], voice: str, out_dir: Path,
                   on_progress: Optional[ProgressFn] = None,
                   should_stop: Optional[Callable[[], None]] = None) -> List[Clip]:
        """Trả về danh sách clip theo thứ tự thời gian. Câu đã sinh ở lần chạy trước (cùng nội dung, cùng giọng)
        được dùng lại, nên chạy lại job không phải đọc lại từ đầu."""
        out_dir.mkdir(parents=True, exist_ok=True)
        speakable = [(cue, sanitize(cue.vi_text)) for cue in sorted(cues, key=lambda c: c.start_ms)]
        speakable = [(cue, text) for cue, text in speakable if text and any(ch.isalnum() for ch in text)]
        windows = speaking_windows([cue for cue, _ in speakable])
        done = self._load_partial(out_dir, voice)
        clips: Dict[int, Clip] = {}
        pending = []
        for cue, text in speakable:
            cached = done.get(self._key(cue, text))
            if cached and (out_dir / cached["audio_file"]).is_file() and (out_dir / cached["audio_file"]).stat().st_size > 0:
                clips[cue.idx] = Clip(**cached)
            else:
                pending.append((cue, text))

        total = len(speakable)
        if on_progress:
            on_progress(len(clips), total)
        for offset in range(0, len(pending), self._batch_size):
            if should_stop:
                should_stop()
            batch = pending[offset:offset + self._batch_size]
            results = asyncio.run(self._run_batch(batch, voice, out_dir, windows))
            failure: Optional[BaseException] = None
            for result in results:
                if isinstance(result, BaseException):
                    failure = failure or result
                    continue
                clips[result.idx] = result
                done[self._key_of(result)] = asdict(result)
            # Lưu cả khi lô có câu lỗi: các câu đã đọc xong trong lô không phải đọc lại ở lần chạy sau.
            self._save_partial(out_dir, voice, done)
            if on_progress:
                on_progress(len(clips), total)
            if failure is not None:
                raise failure
        return [clips[cue.idx] for cue, _ in speakable]

    # ── Một lô câu chạy song song có giới hạn ─────────────────────────────────
    async def _run_batch(self, batch, voice: str, out_dir: Path, windows: Dict[int, int]) -> list:
        """Trả về Clip cho câu thành công và exception cho câu thất bại (không để một câu lỗi làm mất cả lô)."""
        gate = asyncio.Semaphore(self._concurrency)

        async def one(cue: Cue, text: str) -> Clip:
            async with gate:
                return await self._make_clip(cue, text, voice, out_dir, windows[cue.idx])

        return list(await asyncio.gather(*(one(cue, text) for cue, text in batch), return_exceptions=True))

    async def _make_clip(self, cue: Cue, text: str, voice: str, out_dir: Path, window_ms: int) -> Clip:
        path = out_dir / f"audio_{cue.idx}.mp3"
        rate = "+0%"
        audio_ms = await self._speak_checked(cue, text, voice, rate, path)
        if window_ms > MIN_WINDOW_MS and audio_ms > window_ms * SPEED_TOLERANCE:
            increase = min(int((audio_ms / window_ms - 1) * 100), MAX_SPEED_UP_PERCENT)
            if increase > 0:
                rate = f"+{increase}%"
                audio_ms = await self._speak_checked(cue, text, voice, rate, path)
        return Clip(idx=cue.idx, start_ms=cue.start_ms, end_ms=cue.end_ms, text=text,
                    audio_file=path.name, audio_ms=audio_ms, rate=rate)

    async def _speak_checked(self, cue: Cue, text: str, voice: str, rate: str, path: Path) -> int:
        last_error: Optional[BaseException] = None
        for attempt in range(self._retries):
            try:
                await self._speak(text, voice, rate, path)
                audio_ms = await asyncio.to_thread(self._measure, path)
                if audio_ms and path.stat().st_size > 0:
                    return audio_ms
                last_error = RuntimeError("file âm thanh rỗng")
            except DependencyMissing:
                raise
            except Exception as exc:  # noqa: BLE001 - lỗi mạng của dịch vụ đọc: thử lại
                last_error = exc
            await asyncio.sleep(self._retry_wait_s * (attempt + 1))
        path.unlink(missing_ok=True)   # không để lại file 0 byte như pipeline cũ
        raise TtsFailed(f"Không sinh được giọng đọc cho câu số {cue.idx} sau {self._retries} lần thử "
                        f"({type(last_error).__name__}: {last_error}). Kiểm tra mạng rồi bấm Chạy lại.")

    # ── Lưu tạm để chạy lại không mất công ────────────────────────────────────
    @staticmethod
    def _key(cue: Cue, text: str) -> str:
        return hashlib.sha1(f"{cue.idx}|{cue.start_ms}|{cue.end_ms}|{text}".encode("utf-8")).hexdigest()

    @classmethod
    def _key_of(cls, clip: Clip) -> str:
        return hashlib.sha1(f"{clip.idx}|{clip.start_ms}|{clip.end_ms}|{clip.text}".encode("utf-8")).hexdigest()

    @staticmethod
    def _load_partial(out_dir: Path, voice: str) -> Dict[str, dict]:
        try:
            data = json.loads((out_dir / PARTIAL_FILE).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data.get("clips", {}) if data.get("voice") == voice else {}

    @staticmethod
    def _save_partial(out_dir: Path, voice: str, done: Dict[str, dict]) -> None:
        (out_dir / PARTIAL_FILE).write_text(json.dumps({"voice": voice, "clips": done}, ensure_ascii=False),
                                            encoding="utf-8")
