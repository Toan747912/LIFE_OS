---
tags: [module]
file: modules/video_dubbing/
trạng_thái: Stable
cập_nhật: 2026-10-05
---
# Video Dubbing

Pipeline lồng tiếng gốc: phụ đề → dịch → giọng đọc → trộn vào video.

## File và hàm công khai
| File | Hàm | Làm gì |
| --- | --- | --- |
| `service.py` | `DubbingConfig`, `run_dubbing_pipeline(config, progress_callback)` | Điều phối toàn bộ; báo tiến độ 5 → 100; trả `{"status", "output_path", "sub_count", "audio_count"}` |
| `sub_handler.py` | `load_subtitles(file_path)` | Đọc `.vtt`/`.srt` (UTF-8, có BOM cũng được), trả danh sách dict `index`, `start`, `end` (`timedelta`), `duration_ms`, `content` |
| | `parse_time`, `clean_subtitle_text` | Phụ trợ |
| `tts_generator.py` | `generate_tts_for_subtitles(subs, voice, temp_audio_dir, progress_callback)` | **Tự dịch** từng câu rồi sinh mp3 bằng edge-tts; khớp tốc độ; trả `audio_map` |
| | `translate_text(text)` | Argos offline trước, rồi Google (3 lần thử) |
| | `sanitize_vietnamese_text(text)` | Bỏ ký tự gây lỗi TTS |
| `media_mixer.py` | `mix_audio_to_video_advanced(video_path, audio_map, vtt_path, output_video_path, orig_vol, dub_vol, hard_sub, enable_dynamic_sub, dynamic_ass_path)` | Ghép các câu thành `combined_dubbing.wav` rồi gọi FFmpeg |
| | `build_combined_dub_track` | Ghép các câu theo mốc thời gian |
| `main.py` | `main()` | Bản dòng lệnh, dùng `core/input/sample.mp4` và `sample.vtt` |
| `ui_controller.py` | `open_volume_controller` | Mã chết (tkinter), không ai import |

## Tham số cấm đổi
- Khớp tốc độ: chỉ khi khung thời gian > 400 ms và audio dài hơn khung quá 5%; tăng tối đa +50%.
- FFmpeg: `amix=inputs=2:duration=first:normalize=0`; phụ đề mềm thì `-c:v copy`, phụ đề cứng hoặc phụ đề động thì `libx264 -crf 23`; audio `aac 192k`; phụ đề mềm gắn `language=vie`.
- Mặc định: `orig_vol=0.15`, `dub_vol=1.0`, giọng `vi-VN-HoaiMyNeural`.

## Quan hệ
- Được gọi bởi: [[Backend FastAPI]] (`/start-dubbing`), `main.py`, [[Bilibili Dubbing]] (3 hàm).
- Gọi tới: [[Dynamic Subtitle]] khi `enable_dynamic_sub=True`.
- Thư viện: `edge-tts`, `pydub`, `deep-translator`, `argostranslate` (không bắt buộc), FFmpeg.
- Đọc `core/input/`, ghi `core/output/output_final.mp4` và `core/output/temp_audios/`.

## Ai phụ thuộc vào đây
[[Bilibili Dubbing]] gọi `load_subtitles`, `mix_audio_to_video_advanced`, `sanitize_vietnamese_text` và phụ thuộc cả hình dạng dữ liệu của chúng: [[Phát hiện - liên hệ ẩn#Phụ thuộc ngầm của Bilibili vào code Stable]].

## Cấm đụng
Toàn bộ module. Điểm cấm cụ thể ở [[Phạm vi và quyền]].

## Giới hạn
[[Vấn đề đã biết]] số 4, 6, 16. Không có test.
