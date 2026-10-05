"""Lời gọi ffmpeg/ffprobe dùng chung của module (chỉ đọc thông tin và chuyển định dạng phụ đề)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional


class FfmpegTools:
    def __init__(self, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe", timeout_s: int = 120):
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._timeout_s = timeout_s

    def available(self) -> bool:
        return shutil.which(self._ffmpeg) is not None

    def probe(self, path: Path) -> Dict[str, Any]:
        """Thời lượng, kích thước và codec thật của file. Trả dict rỗng nếu không đọc được."""
        try:
            done = subprocess.run(
                [self._ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
                capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=self._timeout_s,
            )
            data = json.loads(done.stdout or "{}")
        except (OSError, subprocess.SubprocessError, ValueError):
            return {}
        info: Dict[str, Any] = {}
        try:
            info["duration_s"] = int(round(float(data["format"]["duration"])))
        except (KeyError, TypeError, ValueError):
            pass
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                info.update(width=stream.get("width"), height=stream.get("height"), vcodec=stream.get("codec_name"))
                break
        return info

    def duration_ms(self, path: Path) -> Optional[int]:
        """Độ dài chính xác tới mili giây của một file âm thanh/video; None nếu không đọc được."""
        try:
            done = subprocess.run(
                [self._ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                capture_output=True, text=True, timeout=self._timeout_s,
            )
            return int(round(float(done.stdout.strip()) * 1000))
        except (OSError, subprocess.SubprocessError, ValueError):
            return None

    def to_vtt(self, source: Path, target: Path) -> bool:
        """Đổi phụ đề (srt, ass...) sang WebVTT để trình duyệt phát được. False nếu thất bại."""
        try:
            done = subprocess.run(
                [self._ffmpeg, "-y", "-v", "error", "-i", str(source), "-f", "webvtt", str(target)],
                capture_output=True, timeout=self._timeout_s,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return done.returncode == 0 and target.is_file() and target.stat().st_size > 0
