"""Trộn giọng lồng tiếng vào video bằng hàm sẵn có của LIFE_OS (`media_mixer.mix_audio_to_video_advanced`).

Lớp này chỉ là adapter: đổi dữ liệu của module sang đúng dạng hàm cũ cần, không sửa hàm cũ.
"""
from __future__ import annotations

import subprocess
from datetime import timedelta
from pathlib import Path
from typing import Callable, List, Optional, Sequence

from modules.bilibili_dubbing.domain.errors import BilibiliError, DependencyMissing
from modules.bilibili_dubbing.dubbing.synthesizer import Clip

# Chữ ký của hàm trộn cũ, để test thay được bằng hàm giả.
MixFn = Callable[..., None]


class MixFailed(BilibiliError):
    code = "mix_failed"
    http_status = 500


def legacy_mix(**kwargs) -> None:
    try:
        from modules.video_dubbing.media_mixer import mix_audio_to_video_advanced
    except ImportError as exc:
        raise DependencyMissing(f"Không nạp được bộ trộn video của LIFE_OS: {exc}") from exc
    mix_audio_to_video_advanced(**kwargs)


class DubMixer:
    def __init__(self, mix: Optional[MixFn] = None):
        self._mix = mix or legacy_mix

    @staticmethod
    def to_audio_map(clips: Sequence[Clip], audio_dir: Path) -> List[dict]:
        """Dạng `audio_map` của pipeline cũ: mốc thời gian là timedelta, đường dẫn tuyệt đối tới file mp3."""
        return [{
            "index": clip.idx,
            "start": timedelta(milliseconds=clip.start_ms),
            "end": timedelta(milliseconds=max(clip.end_ms, clip.start_ms + clip.audio_ms)),
            "duration_ms": clip.end_ms - clip.start_ms,
            "audio_duration_ms": clip.audio_ms,
            "audio_path": str(audio_dir / clip.audio_file),
            "text": clip.text,
        } for clip in clips]

    def mix(self, video_path: Path, clips: Sequence[Clip], audio_dir: Path, subtitle_path: Optional[Path],
            output_path: Path, orig_vol: float, dub_vol: float) -> Path:
        if not clips:
            raise MixFailed("Không có câu lồng tiếng nào để trộn.")
        output_path.unlink(missing_ok=True)
        try:
            self._mix(
                video_path=str(video_path),
                audio_map=self.to_audio_map(clips, audio_dir),
                vtt_path=str(subtitle_path) if subtitle_path and subtitle_path.is_file() else None,
                output_video_path=str(output_path),
                orig_vol=orig_vol,
                dub_vol=dub_vol,
                hard_sub=False,                 # phụ đề mềm: không encode lại hình
                enable_dynamic_sub=False,
            )
        except subprocess.CalledProcessError as exc:
            output_path.unlink(missing_ok=True)
            raise MixFailed(f"FFmpeg báo lỗi khi trộn video (mã {exc.returncode}). "
                            "Chi tiết nằm trong cửa sổ đang chạy server.") from exc
        except FileNotFoundError as exc:
            raise DependencyMissing("Không tìm thấy ffmpeg. Hãy cài ffmpeg và thêm vào PATH.") from exc
        if not output_path.is_file() or output_path.stat().st_size == 0:
            raise MixFailed("Trộn xong nhưng không thấy file video kết quả.")
        return output_path
