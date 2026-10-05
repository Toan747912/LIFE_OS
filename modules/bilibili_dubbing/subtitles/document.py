"""Phụ đề của một video: danh sách câu có mốc thời gian, đọc SRT/VTT và ghi WebVTT."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from modules.bilibili_dubbing.domain.errors import InvalidRequest


@dataclass
class Cue:
    idx: int
    start_ms: int
    end_ms: int
    source_text: str = ""
    vi_text: str = ""
    edited: bool = False

    def to_dict(self) -> dict:
        return {"idx": self.idx, "start_ms": self.start_ms, "end_ms": self.end_ms,
                "source_text": self.source_text, "vi_text": self.vi_text, "edited": self.edited}


def _timestamp(ms: int) -> str:
    ms = max(int(ms), 0)
    hours, rest = divmod(ms, 3_600_000)
    minutes, rest = divmod(rest, 60_000)
    seconds, millis = divmod(rest, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


class SubtitleDocument:
    def __init__(self, cues: Iterable[Cue]):
        self.cues: List[Cue] = self._normalize(cues)

    @staticmethod
    def _normalize(cues: Iterable[Cue]) -> List[Cue]:
        """Sắp theo thời gian, bỏ câu rỗng hoặc mốc thời gian sai, đánh số lại từ 1."""
        valid = [c for c in cues if c.source_text.strip() and c.end_ms > c.start_ms >= 0]
        valid.sort(key=lambda c: (c.start_ms, c.end_ms))
        for number, cue in enumerate(valid, 1):
            cue.idx = number
            cue.source_text = " ".join(cue.source_text.split())
        return valid

    def __len__(self) -> int:
        return len(self.cues)

    # ── Đọc ───────────────────────────────────────────────────────────────────
    @classmethod
    def from_file(cls, path: Path) -> "SubtitleDocument":
        """Đọc .srt/.vtt bằng parser sẵn có của LIFE_OS (`sub_handler.load_subtitles`)."""
        from modules.video_dubbing.sub_handler import load_subtitles

        try:
            parsed = load_subtitles(str(path))
        except UnicodeDecodeError as exc:
            raise InvalidRequest("File phụ đề phải được lưu ở bảng mã UTF-8.") from exc
        return cls(
            Cue(idx=0, start_ms=int(item["start"].total_seconds() * 1000),
                end_ms=int(item["end"].total_seconds() * 1000), source_text=item["content"])
            for item in parsed
        )

    @classmethod
    def from_segments(cls, segments: Iterable[dict]) -> "SubtitleDocument":
        """Từ kết quả bóc băng (mỗi đoạn có start, end tính bằng giây và text)."""
        return cls(
            Cue(idx=0, start_ms=int(float(seg["start"]) * 1000), end_ms=int(float(seg["end"]) * 1000),
                source_text=str(seg.get("text") or ""))
            for seg in segments
        )

    # ── Ghi ───────────────────────────────────────────────────────────────────
    @staticmethod
    def write_vtt(cues: Iterable[Cue], path: Path, use_vi: bool = True) -> int:
        """Ghi WebVTT; câu không có nội dung bị bỏ qua. Trả về số câu đã ghi."""
        blocks: List[str] = []
        for cue in cues:
            text: Optional[str] = (cue.vi_text if use_vi else cue.source_text).strip()
            if text:
                blocks.append(f"{len(blocks) + 1}\n{_timestamp(cue.start_ms)} --> {_timestamp(cue.end_ms)}\n{text}\n")
        Path(path).write_text("WEBVTT\n\n" + "\n".join(blocks), encoding="utf-8")
        return len(blocks)
