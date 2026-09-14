import os
import re
from datetime import timedelta

def parse_time(time_str):
    """Chuyển đổi chuỗi thời gian SRT/VTT thành timedelta"""
    time_str = time_str.strip().replace(',', '.')
    parts = time_str.split(':')
    if len(parts) == 3:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds_parts = parts[2].split('.')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
    elif len(parts) == 2:
        hours = 0
        minutes = int(parts[0])
        seconds_parts = parts[1].split('.')
        seconds = int(seconds_parts[0])
        milliseconds = int(seconds_parts[1]) if len(seconds_parts) > 1 else 0
    else:
        raise ValueError(f"Định dạng thời gian không hợp lệ: {time_str}")

    return timedelta(
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        milliseconds=milliseconds
    )

def clean_subtitle_text(raw_text):
    """Làm sạch các thẻ định dạng HTML/VTT và khoảng trắng thừa"""
    # Xóa thẻ HTML dạng <v Speaker>, <b>, <i>, <font>, ...
    text = re.sub(r'<[^>]+>', '', raw_text)
    # Xóa tham số vị trí VTT (align, position, line, ...)
    text = re.sub(r'\b(align|position|line|size|region):[^\s]+\b', '', text)
    # Thay ngắt dòng thành khoảng trắng
    text = text.replace('\n', ' ')
    # Xóa khoảng trắng thừa
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def load_subtitles(file_path):
    """Đọc file phụ đề (.vtt hoặc .srt) và trả về danh sách câu thoại chuẩn hóa"""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Không tìm thấy file phụ đề tại: {file_path}")

    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    # Regex khớp với thời gian trong cả VTT và SRT
    pattern = r'(?:(\d{2}:\d{2}:\d{2}[\.,]\d{3}) --> (\d{2}:\d{2}:\d{2}[\.,]\d{3})|(\d{2}:\d{2}[\.,]\d{3}) --> (\d{2}:\d{2}[\.,]\d{3}))\s*\n(.*?)(?=\n\s*\n|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)

    parsed_subs = []
    for i, match in enumerate(matches, 1):
        start_str = match[0] if match[0] else match[2]
        end_str = match[1] if match[1] else match[3]
        raw_text = match[4]

        cleaned_text = clean_subtitle_text(raw_text)
        if not cleaned_text:
            continue

        start_time = parse_time(start_str)
        end_time = parse_time(end_str)
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        parsed_subs.append({
            "index": i,
            "start": start_time,
            "end": end_time,
            "duration_ms": duration_ms,
            "content": cleaned_text
        })

    return parsed_subs
