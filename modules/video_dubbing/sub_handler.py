import os
from datetime import timedelta

def parse_time_vtt(time_str):
    """Chuyển đổi chuỗi thời gian VTT (hh:mm:ss.mmm hoặc mm:ss.mmm) thành timedelta"""
    parts = time_str.strip().split(':')
    if len(parts) == 3:
        hours, minutes, seconds_ms = parts
    elif len(parts) == 2:
        hours = 0
        minutes, seconds_ms = parts
    else:
        raise ValueError(f"Định dạng thời gian không hợp lệ: {time_str}")
    
    seconds, milliseconds = seconds_ms.split('.')
    return timedelta(
        hours=int(hours),
        minutes=int(minutes),
        seconds=int(seconds),
        milliseconds=int(milliseconds)
    )

def load_subtitles(vtt_path):
    """Đọc file .vtt thủ công, nhẹ nhàng, không tốn tài nguyên máy"""
    if not os.path.exists(vtt_path):
        raise FileNotFoundError(f"Không tìm thấy file vtt tại: {vtt_path}")
    
    with open(vtt_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    parsed_subs = []
    i = 0
    index = 1
    
    while i < len(lines):
        line = lines[i].strip()
        
        # Bỏ qua dòng WEBVTT header hoặc dòng trống
        if not line or line.startswith("WEBVTT") or "-->" not in line and not line.isdigit():
            i += 1
            continue
            
        # Nếu dòng hiện tại là số thứ tự hoặc nhảy thẳng vào dòng thời gian có dấu "-->"
        if "-->" in line:
            time_line = line
            i += 1
        elif i + 1 < len(lines) and "-->" in lines[i + 1]:
            # Dòng hiện tại là index, dòng sau là thời gian
            i += 1
            time_line = lines[i].strip()
            i += 1
        else:
            i += 1
            continue
            
        # Tách thời gian bắt đầu và kết thúc
        start_str, end_str = time_line.split("-->")
        start_time = parse_time_vtt(start_str.strip().split(" ")[0])
        end_time = parse_time_vtt(end_str.strip().split(" ")[0])
        
        # Gom các dòng nội dung tiếp theo cho đến khi gặp dòng trống
        content_lines = []
        while i < len(lines) and lines[i].strip() != "":
            content_lines.append(lines[i].strip())
            i += 1
            
        content = " ".join(content_lines)
        
        if content:
            parsed_subs.append({
                "index": index,
                "start": start_time,
                "end": end_time,
                "content": content
            })
            index += 1
            
    return parsed_subs
