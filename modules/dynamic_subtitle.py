import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import os
import subprocess
from typing import List, Dict, Any

def extract_temp_audio(video_path: str, output_wav: str) -> str:
    """
    Trích xuất riêng luồng audio tiếng Anh từ video gốc ra file .wav (16kHz, mono)
    để đẩy vào mô hình AI faster-whisper.
    """
    os.makedirs(os.path.dirname(output_wav), exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-vn",
        "-acodec", "pcm_s16le",
        "-ar", "16000",
        "-ac", "1",
        output_wav
    ]
    print(f"[DynamicSub] Trích xuất audio từ '{video_path}' -> '{output_wav}'...")
    subprocess.run(cmd, check=True)
    return output_wav

def transcribe_audio_word_level(audio_path: str, model_size: str = "base") -> List[Dict[str, Any]]:
    """
    Dùng faster-whisper nhận diện âm thanh với word-level timestamps.
    Trả về danh sách các segments, mỗi segment chứa danh sách từ (words) có timestamp (start, end, word).
    """
    from faster_whisper import WhisperModel

    print(f"[DynamicSub] Load model faster-whisper ('{model_size}', device='cpu', compute_type='int8')...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    
    print(f"[DynamicSub] Đang bóc băng âm thanh file '{audio_path}'...")
    segments, info = model.transcribe(audio_path, word_timestamps=True)
    
    result_segments = []
    for segment in segments:
        words_list = []
        if hasattr(segment, "words") and segment.words:
            for w in segment.words:
                words_list.append({
                    "start": w.start,
                    "end": w.end,
                    "word": w.word
                })
        
        result_segments.append({
            "start": segment.start,
            "end": segment.end,
            "text": segment.text,
            "words": words_list
        })
        
    print(f"[DynamicSub] Hoàn tất bóc băng. Tìm thấy {len(result_segments)} câu/phân đoạn.")
    return result_segments

def format_ass_timestamp(seconds: float) -> str:
    """
    Chuyển đổi số giây (float) sang định dạng mốc thời gian ASS: H:MM:SS.cs (centiseconds)
    Ví dụ: 65.25 -> 0:01:05.25
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centiseconds = int(round((seconds - int(seconds)) * 100))
    if centiseconds >= 100:
        centiseconds = 99
    return f"{hours}:{minutes:02d}:{secs:02d}.{centiseconds:02d}"

def generate_dynamic_ass(segments: List[Dict[str, Any]], output_ass: str) -> str:
    """
    Tạo file format ASS (Advanced SubStation Alpha).
    Thiết lập Style mặc định: Font to, in đậm, viền đen (Outline) rõ nét, canh giữa màn hình.
    Xử lý mã hiệu ứng nảy/đổi màu từng từ (Karaoke/Transform tags).
    """
    os.makedirs(os.path.dirname(output_ass), exist_ok=True)
    
    ass_header = """[Script Info]
Title: Dynamic Word Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: None
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Dynamic,Arial,48,&H00FFFFFF,&H0000FFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,3,1,2,20,20,60,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    
    for seg in segments:
        words = seg.get("words", [])
        if not words:
            # Fallback nếu câu không chia được word-level
            start_str = format_ass_timestamp(seg["start"])
            end_str = format_ass_timestamp(seg["end"])
            text = seg.get("text", "").strip()
            if text:
                events.append(f"Dialogue: 0,{start_str},{end_str},Dynamic,,0,0,0,,{text}")
            continue
            
        # Với mỗi từ cất lên, tạo một dòng Dialogue hiển thị cả câu/cụm câu, 
        # nhưng từ đang đọc sẽ nảy to (130%) và đổi sang màu vàng (\c&H00FFFF&)
        for i, current_word_info in enumerate(words):
            w_start = current_word_info["start"]
            w_end = current_word_info["end"]
            
            # Tránh trường hợp w_end <= w_start
            if w_end <= w_start:
                w_end = w_start + 0.1
                
            start_str = format_ass_timestamp(w_start)
            end_str = format_ass_timestamp(w_end)
            
            formatted_words = []
            for j, word_info in enumerate(words):
                w_text = word_info["word"].strip()
                if not w_text:
                    continue
                if j == i:
                    # Từ đang cất lên: Phóng to 130%, màu vàng
                    formatted_words.append(f"{{\\fscx130\\fscy130\\c&H00FFFF&}}{w_text}{{\\fscx100\\fscy100\\c&HFFFFFF&}}")
                else:
                    # Các từ khác trong cùng câu: Kích thước bình thường 100%, màu trắng
                    formatted_words.append(w_text)
            
            line_text = " ".join(formatted_words)
            events.append(f"Dialogue: 0,{start_str},{end_str},Dynamic,,0,0,0,,{line_text}")
            
    with open(output_ass, "w", encoding="utf-8") as f:
        f.write(ass_header)
        for ev in events:
            f.write(ev + "\n")
            
    print(f"[DynamicSub] Đã sinh file phụ đề động ASS tại: '{output_ass}'")
    return output_ass
