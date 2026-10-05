---
tags: [dự-án]
cập_nhật: 2026-10-06
---
# Phát hiện — liên hệ ẩn

Những chỗ các phần của dự án chạm nhau mà nhìn từng file không thấy. Rút từ lần đọc toàn bộ code ngày 2026-10-05: đọc từng dòng các module cũ, `app.py`, `vi_sub_server.py`; đọc cấu trúc và các đoạn gọi API của extension và `index.html`; trích danh mục lớp và hàm của [[Bilibili Dubbing]]. Chưa chạy code để tái hiện.

## Hai server tranh một cổng, và extension chỉ đọc được với Flask
> Cập nhật 2026-10-06: `app.py` đã có `GET /api/tts` (QĐ-13), nên extension có giọng với cả hai server. Phần dưới mô tả tình trạng trước đó và những khác biệt còn lại.

[[Backend FastAPI]] và [[Backend Flask]] đều chạy cổng 8000, cùng có `/api/translate` và `/api/tts`, nhưng khác nhau:

| | `app.py` (FastAPI) | `vi_sub_server.py` (Flask) |
| --- | --- | --- |
| `/api/translate` | `POST`, `deep-translator` (Google) | `POST`, Argos offline, không có thì gọi Google |
| `/api/tts` | `POST`, và `GET` từ 2026-10-06; `edge-tts`, giọng `vi-VN-HoaiMyNeural` | **`GET` và `POST`**, `gTTS` |
| Cache | không | có (2000 câu dịch, 300 đoạn giọng) |
| `/health` | không có | có |

[[Chrome Extension]] phát giọng bằng `new Audio(API_TTS + '?text=…')`, tức là `GET`. Vì vậy:
- Chạy `vi_sub_server.py`: extension dịch và đọc được.
- Chạy `app.py` (trước 2026-10-06): extension dịch được, **không có giọng** (`GET /api/tts` không tồn tại), và code không lùi về Web Speech khi lỗi.

**Khi gộp backend** phải: giữ `GET /api/tts?text=` (đã thêm), giữ nguyên `{"translation": …}`, quyết định engine nào (edge-tts hay gTTS, Google hay Argos), và giữ `/health` nếu còn thứ gì gọi.

## Bốn bản cài đặt dịch, ba bản sinh giọng
| Việc | Nơi cài đặt |
| --- | --- |
| Dịch | `app.py` (`/api/translate`), `vi_sub_server.py`, `tts_generator.translate_text` (Argos rồi Google), `bilibili_dubbing/subtitles/translator.py` |
| Sinh giọng | `app.py` (`/api/tts`), `vi_sub_server.py` (gTTS), `tts_generator` (edge-tts), `bilibili_dubbing/dubbing/synthesizer.py` (edge-tts) |

Sửa hành vi dịch hay giọng ở một nơi không ảnh hưởng nơi khác. Đừng giả định chúng giống nhau.

## Giọng mặc định khai ở 4 nơi
`core/config.py` (`DEFAULT_VOICE`, chỉ CLI dùng) · `DubbingConfig.voice` trong `service.py` · `EDGE_TTS_VOICE` trong `app.py` · cài đặt của [[Bilibili Dubbing]]. Đều là `vi-VN-HoaiMyNeural`. Đây là lý do mục ".env" trong roadmap.

## Đường dẫn tương đối
`file_manager.UPLOAD_DIR = "core/input"`, `Jinja2Templates(directory="templates")`, các mặc định trong `DubbingConfig`, `"core/output/output_final.mp4"` trong `app.py` đều tương đối theo thư mục chạy. Chạy server từ thư mục khác thì hỏng. [[Bilibili Dubbing]] không bị vì tính đường dẫn từ `__file__`.

## Phụ thuộc ngầm của Bilibili vào code Stable
[[Bilibili Dubbing]] gọi thẳng 5 hàm (QĐ-02 trong [[Nhật ký quyết định]]). Nó phụ thuộc vào cả **hình dạng dữ liệu**, không chỉ tên hàm:
- `load_subtitles` trả danh sách dict có `index`, `start`, `end` (kiểu `timedelta`), `duration_ms`, `content`.
- `mix_audio_to_video_advanced` nhận `audio_map` là danh sách dict có `start`, `end` (kiểu `timedelta`), `audio_path`; ghi file tạm `combined_dubbing.wav` vào cùng thư mục với đoạn audio đầu tiên.
- `transcribe_audio_word_level` trả danh sách dict có `start`, `end`, `text`, `words`.

Đổi bất kỳ điều nào ở trên (ví dụ khi gộp backend hay "dọn" code cũ) sẽ làm hỏng Bilibili mà test của module cũ không báo, vì module cũ không có test.

## Một file đầu ra dùng chung
Lồng tiếng gốc luôn ghi `core/output/output_final.mp4` và `core/output/temp_audios/`. Lần chạy sau ghi đè lần trước; file `audio_*.mp3` cũ không được dọn nên lẫn với lần chạy mới.

## Mã chết và file thừa
| Mục | Bằng chứng |
| --- | --- |
| `yt-subtitle-extension/content.js` (43 KB) | `manifest.json` chỉ nạp `core.js` + `sites/*.js`. `content.js` là bản một file cũ, chứa lại gần hết `core.js` và `generic.js` |
| `content.js.bak`, `content.js.bak2` | bản sao lưu của file trên |
| `fix_vi_sub.ps1`, `fix_vi_sub_v2.ps1` | script vá chuỗi trong `content.js`, tức là vá một file không còn được nạp |
| `modules/video_dubbing/ui_controller.py` | cửa sổ tkinter chỉnh âm lượng; không file nào import |
| `yt-subtitle-extension/app_cors_snippet.py` | đoạn mẫu CORS; `app.py` đã có sẵn CORS |
| `Claude outputs/` | bản sao cũ của file extension và `vi_sub_server.py` |
| `mix_audio_to_video` trong `media_mixer.py` | hàm "tương thích ngược", không ai gọi |
| `core/output/temp_audios/` | 139 file `audio_*.mp3` cũ, nhiều file 0 byte |

Chưa xóa gì. Xóa là việc không hoàn tác được và một số nằm trong vùng Stable: cần người dùng quyết định ([[Việc cần làm]]).

## Tên dự án không thống nhất
`main.py`, `modules/video_dubbing/main.py` và `ui_controller.py` in "LIVE OS"; thư mục và `app.py` là "LIFE_OS".

## Kiểu xuống dòng lẫn lộn
Một số file CRLF, số còn lại LF (danh sách ở [[Quy ước code#Định dạng file]]). Công cụ tự đổi kiểu xuống dòng sẽ tạo diff toàn file ở module Stable.

## Luật cứng chép ở 4 nơi
[[Bắt đầu ở đây]], `AGENTS.md`, `.agents/rules/strict_permissions.md`, [[Tóm tắt dán tay]]. Sửa một nơi phải sửa cả bốn (QĐ-10).
