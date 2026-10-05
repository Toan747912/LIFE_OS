---
tags: [module]
file: modules/dynamic_subtitle.py
trạng_thái: Stable
cập_nhật: 2026-10-05
---
# Dynamic Subtitle

Bóc băng tiếng bằng `faster-whisper` và tạo phụ đề ASS có hiệu ứng từng từ.

## Hàm công khai
| Hàm | Làm gì |
| --- | --- |
| `extract_temp_audio(video_path, output_wav)` | FFmpeg tách audio ra WAV 16 kHz mono |
| `transcribe_audio_word_level(audio_path, model_size="base")` | Whisper trên CPU, `int8`, mốc thời gian từng từ; trả danh sách dict `start`, `end`, `text`, `words` |
| `generate_dynamic_ass(segments, output_ass)` | Ghi file ASS: từ đang đọc phóng 130% và đổi màu vàng |
| `format_ass_timestamp(seconds)` | Phụ trợ |

## Quan hệ
- Được gọi bởi: [[Video Dubbing]] (`service.py`, khi bật phụ đề động), [[Bilibili Dubbing]] (`extract_temp_audio`, `transcribe_audio_word_level`).
- Thư viện: `faster-whisper` (import bên trong hàm), FFmpeg.

## Cấm đụng
Template ASS (phần đầu file, style `Dynamic`, thẻ hiệu ứng). Chữ ký và dữ liệu trả về của hai hàm mà Bilibili gọi.

## Giới hạn
Model nạp lại mỗi lần gọi. Cần nhiều RAM: [[Vấn đề đã biết]] số 1.
