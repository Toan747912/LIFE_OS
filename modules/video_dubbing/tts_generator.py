import asyncio
import os
import time
import re
import edge_tts
from googletrans import Translator

async def _generate_audio(text, voice, output_path):
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)

def clean_vtt_text(raw_text):
    text = re.sub(r'<[^>]+>', '', raw_text)
    text = re.sub(r'\b(align|position|line|size|region):[^\s]+\b', '', text)
    text = text.replace('\n', ' ')
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def sanitize_vietnamese_text(text):
    text = text.replace('"', '').replace("'", "").replace('„', '').replace('“', '').replace('”', '')
    text = re.sub(r'[<>{}[\]\\]', '', text)
    return text.strip()

def generate_tts_for_subtitles(subs, voice, temp_audio_dir):
    os.makedirs(temp_audio_dir, exist_ok=True)
    audio_map = []
    
    # Ép cứng giọng đọc tiếng Việt chuẩn xác của Edge-TTS
    target_voice = "vi-VN-HoaiMyNeural"
    translator = Translator()

    print("Đang tiến hành dịch phụ đề sang tiếng Việt và tạo giọng đọc...")
    for sub in subs:
        raw_text = sub['content']
        cleaned_text = clean_vtt_text(raw_text)
        
        if not cleaned_text or len(cleaned_text) < 1 or not any(c.isalnum() for c in cleaned_text):
            continue
            
        vietnamese_text = cleaned_text
        try:
            result = translator.translate(cleaned_text, src='en', dest='vi')
            if result and result.text:
                vietnamese_text = result.text
        except Exception:
            pass
            
        safe_text = sanitize_vietnamese_text(vietnamese_text)
        if not safe_text:
            continue
            
        file_name = f"audio_{sub['index']}.mp3"
        output_path = os.path.join(temp_audio_dir, file_name)
        
        try:
            asyncio.run(_generate_audio(safe_text, target_voice, output_path))
            time.sleep(0.15)
            
            audio_map.append({
                "index": sub['index'],
                "start": sub['start'],
                "end": sub['end'],
                "audio_path": output_path
            })
            print(f"Đã dịch & tạo câu {sub['index']}: {safe_text[:35]}...")
        except Exception as e:
            print(f"Lỗi tạo audio câu {sub['index']}: {e}")
            
    return audio_map
