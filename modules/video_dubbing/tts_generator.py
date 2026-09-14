import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass
import asyncio
import os
import time
import re
import edge_tts
from pydub import AudioSegment

def is_valid_translation(text: str) -> bool:
    """Kiểm tra câu dịch có hợp lệ không (loại bỏ thông báo lỗi Google 500 / Rate Limit / HTML)"""
    if not text or not isinstance(text, str):
        return False
    lower = text.lower()
    invalid_keywords = [
        'error 500', 'server error', 'too many requests', 
        '429 ', '500 ', '<html', '<doctype', 'googletranslateerror',
        'http 500', 'http 429'
    ]
    return not any(kw in lower for kw in invalid_keywords)

_argos_translator = None

def get_argos_translator():
    """Tải translator Offline 100% bằng ArgosTranslate (Không tốn băng thông mạng, 0% lỗi Server Error)"""
    global _argos_translator
    if _argos_translator is not None:
        return _argos_translator
    try:
        import argostranslate.translate
        langs = argostranslate.translate.get_installed_languages()
        from_lang = next((l for l in langs if l.code == 'en'), None)
        to_lang = next((l for l in langs if l.code == 'vi'), None)
        if from_lang and to_lang:
            _argos_translator = from_lang.get_translation(to_lang)
            print("[TTS] Đã nạp thành công mô hình dịch thuật Offline Local (ArgosTranslate EN->VI).")
            return _argos_translator
    except Exception as e:
        print(f"[TTS Warning] Chưa khởi tạo được ArgosTranslate Offline: {e}")
    return None

try:
    from deep_translator import GoogleTranslator
    _has_deep_translator = True
except Exception:
    _has_deep_translator = False

def translate_text(text: str) -> str:
    """
    Dịch câu tiếng Anh sang tiếng Việt.
    Ưu tiên 1: Dịch Local Offline 100% bằng argostranslate (không tốn mạng, không bị nghẽn API).
    Ưu tiên 2: DeepTranslator / GoogleTranslator (Online fallback với validation & retry).
    """
    # 1. Thử dịch Local Offline 100% trước
    argos_trans = get_argos_translator()
    if argos_trans:
        try:
            res = argos_trans.translate(text)
            if res and is_valid_translation(res):
                return res
        except Exception:
            pass

    # 2. Online Fallback nếu chưa dùng được Argos
    if _has_deep_translator:
        for attempt in range(3):
            try:
                res = GoogleTranslator(source='auto', target='vi').translate(text)
                if res and is_valid_translation(res):
                    return res
            except Exception:
                pass
            time.sleep(0.5)
            
    return text

async def _generate_audio(text, voice, output_path, rate="+0%"):
    """Tạo audio với giọng đọc và tốc độ chỉ định qua Edge-TTS"""
    communicate = edge_tts.Communicate(text, voice, rate=rate)
    await communicate.save(output_path)

def sanitize_vietnamese_text(text):
    """Làm sạch ký tự đặc biệt nguy hại cho TTS"""
    text = text.replace('"', '').replace("'", "").replace('„', '').replace('“', '').replace('”', '')
    text = re.sub(r'[<>{}[\]\\]', '', text)
    return text.strip()

def generate_tts_for_subtitles(subs, voice="vi-VN-HoaiMyNeural", temp_audio_dir="core/output/temp_audios", progress_callback=None):
    """
    Tạo file audio cho từng câu phụ đề, tự động điều chỉnh tốc độ đọc (auto-speed matching)
    nếu âm thanh đọc dài hơn khung thời gian phụ đề.
    """
    os.makedirs(temp_audio_dir, exist_ok=True)
    audio_map = []
    total_subs = len(subs)

    print(f"Đang dịch {total_subs} câu phụ đề & tạo giọng đọc (Giọng: {voice})...")

    for idx, sub in enumerate(subs, 1):
        raw_text = sub['content']
        if not raw_text or not any(c.isalnum() for c in raw_text):
            continue

        # 1. Dịch sang tiếng Việt (Có validation & retry chống lỗi Server Error 500)
        vietnamese_text = raw_text
        try:
            translated = translate_text(raw_text)
            if translated and is_valid_translation(translated):
                vietnamese_text = translated
        except Exception:
            pass

        safe_text = sanitize_vietnamese_text(vietnamese_text)
        if not safe_text:
            continue

        file_name = f"audio_{sub['index']}.mp3"
        output_path = os.path.join(temp_audio_dir, file_name)

        # 2. Tạo audio mặc định (tốc độ bình thường)
        try:
            asyncio.run(_generate_audio(safe_text, voice, output_path, rate="+0%"))
            time.sleep(0.1)

            # 3. Đo độ dài thực tế của file Audio thu được (bằng pydub)
            audio_segment = AudioSegment.from_file(output_path)
            actual_duration_ms = len(audio_segment)
            target_duration_ms = sub.get('duration_ms', 0)

            # 4. Auto-Speed Matching: Nếu audio dài hơn khoảng thời gian câu thoại (> 5%)
            if target_duration_ms > 400 and actual_duration_ms > target_duration_ms * 1.05:
                speed_ratio = actual_duration_ms / target_duration_ms
                # Giới hạn tăng tốc tối đa +50% để giọng nói tự nhiên, không bị méo
                speed_increase = min(int((speed_ratio - 1) * 100), 50)
                rate_str = f"+{speed_increase}%"

                # Tạo lại audio với tốc độ được tăng lên
                asyncio.run(_generate_audio(safe_text, voice, output_path, rate=rate_str))
                time.sleep(0.1)
                audio_segment = AudioSegment.from_file(output_path)
                actual_duration_ms = len(audio_segment)

            audio_map.append({
                "index": sub['index'],
                "start": sub['start'],
                "end": sub['end'],
                "duration_ms": target_duration_ms,
                "audio_duration_ms": actual_duration_ms,
                "audio_path": output_path,
                "text": safe_text
            })

            msg = f"[{idx}/{total_subs}] Đã tạo câu {sub['index']}: {safe_text[:30]}..."
            print(msg)
            if progress_callback:
                progress_callback(idx, total_subs, msg)

        except Exception as e:
            print(f"[Lỗi TTS] Câu {sub['index']}: {e}")

    return audio_map
