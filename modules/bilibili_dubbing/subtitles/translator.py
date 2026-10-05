"""Dịch phụ đề sang tiếng Việt. Thay dịch vụ dịch = thêm một lớp con của Translator."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Callable, List, Optional, Sequence

from modules.bilibili_dubbing.domain.errors import DependencyMissing

ProgressFn = Callable[[int, int], None]

_GOOGLE_CODES = {
    "zh": "zh-CN", "zh-cn": "zh-CN", "zh-hans": "zh-CN", "zh-sg": "zh-CN",
    "zh-tw": "zh-TW", "zh-hant": "zh-TW", "zh-hk": "zh-TW",
    "en": "en", "en-us": "en", "en-gb": "en", "ja": "ja", "ko": "ko", "th": "th", "id": "id",
}
_ERROR_MARKERS = ("error 500", "server error", "too many requests", "<html", "<!doctype")


def is_vietnamese(lang: Optional[str]) -> bool:
    return bool(lang) and lang.lower().split("-")[0] == "vi"


def to_google_lang(lang: Optional[str]) -> str:
    """Mã ngôn ngữ của Bilibili (zh-Hans, ai-zh...) -> mã của Google; không rõ thì để tự nhận dạng."""
    code = (lang or "").lower()
    if code.startswith("ai-"):
        code = code[3:]
    return _GOOGLE_CODES.get(code, "auto")


class Translator(ABC):
    @abstractmethod
    def translate_batch(self, texts: Sequence[str], source_lang: Optional[str],
                        on_progress: Optional[ProgressFn] = None) -> List[str]:
        """Dịch từng câu sang tiếng Việt, giữ nguyên thứ tự. Câu không dịch được trả về chuỗi rỗng."""


class GoogleTranslatorAdapter(Translator):
    """Dùng deep-translator (đã có trong requirements). Gom nhiều câu vào một lần gọi để nhanh và ít bị giới hạn."""

    def __init__(self, max_chars: int = 3500, retries: int = 3, pause_s: float = 0.4,
                 call: Optional[Callable[[str, str], str]] = None):
        self._max_chars = max_chars
        self._retries = retries
        self._pause_s = pause_s
        self._call = call or self._call_google

    @staticmethod
    def _call_google(text: str, source: str) -> str:
        try:
            from deep_translator import GoogleTranslator
        except ImportError as exc:
            raise DependencyMissing("Chưa cài deep-translator. Chạy: python -m pip install -r requirements.txt") from exc
        return GoogleTranslator(source=source, target="vi").translate(text) or ""

    def translate_batch(self, texts, source_lang, on_progress=None):
        source = to_google_lang(source_lang)
        cleaned = [" ".join((t or "").split()) for t in texts]
        results = [""] * len(cleaned)
        done = 0
        for chunk in self._chunks(cleaned):
            lines = [cleaned[i] for i in chunk]
            translated = self._translate_text("\n".join(lines), source)
            parts = [p.strip() for p in translated.split("\n")] if translated else []
            if len(parts) != len(chunk):
                # Dịch vụ gộp hoặc tách dòng: dịch lại từng câu để không lệch mốc thời gian.
                parts = [self._translate_text(line, source) for line in lines]
            for index, part in zip(chunk, parts):
                results[index] = part
            done += len(chunk)
            if on_progress:
                on_progress(done, len(cleaned))
            time.sleep(self._pause_s)
        return results

    def _chunks(self, texts: List[str]) -> List[List[int]]:
        chunks, current, size = [], [], 0
        for index, text in enumerate(texts):
            if not text:
                continue
            if current and size + len(text) + 1 > self._max_chars:
                chunks.append(current)
                current, size = [], 0
            current.append(index)
            size += len(text) + 1
        if current:
            chunks.append(current)
        return chunks

    def _translate_text(self, text: str, source: str) -> str:
        for attempt in range(self._retries):
            try:
                result = self._call(text, source)
                if result and not any(marker in result.lower() for marker in _ERROR_MARKERS):
                    return result
            except DependencyMissing:
                raise
            except Exception:  # noqa: BLE001 - lỗi mạng/giới hạn tần suất: thử lại
                pass
            time.sleep(self._pause_s * (attempt + 1))
        return ""
