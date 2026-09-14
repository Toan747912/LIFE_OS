import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import os
from dataclasses import dataclass
from typing import Callable, Optional

from modules.video_dubbing.sub_handler import load_subtitles
from modules.video_dubbing.tts_generator import generate_tts_for_subtitles
from modules.video_dubbing.media_mixer import mix_audio_to_video_advanced
from modules.dynamic_subtitle import extract_temp_audio, transcribe_audio_word_level, generate_dynamic_ass

@dataclass
class DubbingConfig:
    video_path: str = "core/input/sample.mp4"
    subtitle_path: str = "core/input/sample.vtt"
    output_video_path: str = "core/output/output_final.mp4"
    temp_audio_dir: str = "core/output/temp_audios"
    voice: str = "vi-VN-HoaiMyNeural"
    orig_vol: float = 0.15
    dub_vol: float = 1.0
    hard_sub: bool = False
    enable_dynamic_sub: bool = False
    dynamic_ass_path: str = "core/output/dynamic_fx.ass"

def run_dubbing_pipeline(config: DubbingConfig, progress_callback: Optional[Callable[[int, str], None]] = None):
    """
    Quy trình xử lý lồng tiếng chuẩn hóa (Core Pipeline Service).
    Hoàn toàn độc lập với GUI/CLI, sẵn sàng gọi từ Backend Web (FastAPI/Flask/Celery).
    
    progress_callback(percent: int, message: str)
    """
    def emit_progress(percent: int, message: str):
        print(f"[{percent}%] {message}")
        if progress_callback:
            progress_callback(percent, message)

    emit_progress(5, "Đang tải và kiểm tra file đầu vào...")

    if not os.path.exists(config.video_path):
        raise FileNotFoundError(f"Không tìm thấy file video đầu vào: {config.video_path}")
    if not os.path.exists(config.subtitle_path):
        raise FileNotFoundError(f"Không tìm thấy file phụ đề đầu vào: {config.subtitle_path}")

    # 1. Đọc và phân tích phụ đề
    emit_progress(10, "Đang đọc và phân tích file phụ đề...")
    subs = load_subtitles(config.subtitle_path)
    total_subs = len(subs)
    if total_subs == 0:
        raise ValueError("File phụ đề không chứa câu thoại nào hợp lệ!")
    emit_progress(15, f"Đã nạp {total_subs} câu phụ đề.")

    # 2. Dịch thuật & Sinh âm thanh lồng tiếng (với Auto-speed matching)
    def tts_progress(current, total, msg):
        percent = 15 + int((current / total) * 55)  # Tầm 15% -> 70%
        emit_progress(percent, msg)

    emit_progress(20, "Đang dịch phụ đề và tạo giọng đọc lồng tiếng...")
    audio_map = generate_tts_for_subtitles(
        subs=subs,
        voice=config.voice,
        temp_audio_dir=config.temp_audio_dir,
        progress_callback=tts_progress
    )

    if not audio_map:
        raise RuntimeError("Không tạo được file âm thanh lồng tiếng nào!")

    # 2.5 Nếu bật cờ Phụ Đề Động (Dynamic Subtitle): Chạy nhánh AI bóc băng tiếng Anh & xuất ASS
    if config.enable_dynamic_sub:
        emit_progress(72, "Đang trích xuất audio và chạy AI faster-whisper bóc băng word-level...")
        temp_wav = os.path.join(config.temp_audio_dir, "temp_whisper_input.wav")
        extract_temp_audio(config.video_path, temp_wav)
        
        segments = transcribe_audio_word_level(temp_wav)
        emit_progress(78, "Đang tạo file phụ đề động ASS với hiệu ứng nảy chữ...")
        generate_dynamic_ass(segments, config.dynamic_ass_path)

    # 3. Ghép audio và trộn vào Video
    emit_progress(80, "Đang ghép track lồng tiếng và tiến hành trộn video với FFmpeg...")

    os.makedirs(os.path.dirname(config.output_video_path), exist_ok=True)

    mix_audio_to_video_advanced(
        video_path=config.video_path,
        audio_map=audio_map,
        vtt_path=config.subtitle_path,
        output_video_path=config.output_video_path,
        orig_vol=config.orig_vol,
        dub_vol=config.dub_vol,
        hard_sub=config.hard_sub,
        enable_dynamic_sub=config.enable_dynamic_sub,
        dynamic_ass_path=config.dynamic_ass_path
    )

    emit_progress(100, f"Hoàn tất quy trình lồng tiếng! Video lưu tại: {config.output_video_path}")

    return {
        "status": "success",
        "output_path": config.output_video_path,
        "sub_count": total_subs,
        "audio_count": len(audio_map)
    }

