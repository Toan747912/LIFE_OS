---
tags: [dự-án]
cập_nhật: 2026-10-05
---
# Kiến trúc

## Các khối
```text
 templates/index.html          Chrome Extension             main.py (CLI)
        |                     (yt-subtitle-extension/)            |
        | HTTP                         | HTTP 127.0.0.1:8000      |
        v                              v                          |
 +--------------------------+   +---------------------------+     |
 | app.py (FastAPI)         |   | vi_sub_server.py (Flask)  |     |
 | cổng 8000                |   | cổng 8000 (không chạy     |     |
 |                          |   | cùng lúc với app.py)      |     |
 +----+--------+--------+---+   +---------------------------+     |
      |        |        |                                         |
      v        v        v                                         v
 file_manager  |   bilibili_dubbing  --chỉ gọi-->  video_dubbing  <--+
               +------------------------------->   (service, sub_handler,
                                                    tts_generator, media_mixer)
                                                          |
                                                          v
                                                   dynamic_subtitle
```
Chi tiết từng khối: [[Backend FastAPI]], [[Backend Flask]], [[Video Dubbing]], [[Dynamic Subtitle]], [[File Manager]], [[Chrome Extension]], [[Bilibili Dubbing]].

## Cây thư mục
```text
LIFE_OS/
├── AGENTS.md, CLAUDE.md          # chỉ đường cho AI, trỏ vào vault
├── PROJECT_STATUS.md, ARCHITECTURE.md   # trỏ vào vault
├── vault/                        # nguồn sự thật duy nhất (thư mục này)
├── app.py                        # server FastAPI chính
├── vi_sub_server.py              # server Flask cho extension
├── main.py                       # menu dòng lệnh
├── requirements.txt
├── core/
│   ├── config.py                 # INPUT_DIR, OUTPUT_DIR, DEFAULT_VOICE (chỉ CLI dùng)
│   ├── input/                    # video và phụ đề tải lên
│   └── output/                   # output_final.mp4, dynamic_fx.ass, temp_audios/
├── modules/
│   ├── file_manager.py
│   ├── dynamic_subtitle.py
│   ├── video_dubbing/            # service, sub_handler, tts_generator, media_mixer, main, ui_controller
│   └── bilibili_dubbing/         # config, domain, sources, media, dubbing, subtitles,
│                                 # pipeline, storage, api, web, tests, README.md
├── data/
│   └── bilibili_dubbing/         # bilibili.db, cookies.txt, work/, library/ (gitignore)
├── templates/index.html          # giao diện trang chủ
├── yt-subtitle-extension/        # manifest.json, core.js, sites/, styles.css
├── .agents/rules/                # luật cho Antigravity
├── Claude outputs/               # bản sao cũ, mã chết
└── fix_vi_sub.ps1, fix_vi_sub_v2.ps1   # script vá cũ, mã chết
```

## Luồng lồng tiếng gốc
1. Người dùng tải video và phụ đề lên qua `/api/files/upload` → `core/input/`.
2. `POST /start-dubbing` tạo `DubbingConfig`, chạy `run_dubbing_pipeline` ở nền.
3. `load_subtitles` đọc phụ đề → `generate_tts_for_subtitles` dịch từng câu và sinh mp3 vào `core/output/temp_audios/`.
4. Nếu bật phụ đề động: `extract_temp_audio` → `transcribe_audio_word_level` → `generate_dynamic_ass`.
5. `mix_audio_to_video_advanced` ghép thành một track rồi gọi FFmpeg → `core/output/output_final.mp4`.
6. Giao diện hỏi `/status` định kỳ, xong thì tải qua `/download-video`.

## Luồng extension
`core.js` phát hiện phụ đề trên trang → `POST /api/translate` → hiện phụ đề tiếng Việt → phát giọng bằng `GET /api/tts?text=…`.

## Luồng Bilibili
Xem [[Bilibili Dubbing#Luồng job]].

## Ràng buộc kiến trúc
- Mọi server chạy từ thư mục gốc dự án (code cũ dùng đường dẫn tương đối).
- Module mới gắn vào bằng `include_router`, không sửa module cũ: [[Thêm module mới]].
- Một cổng 8000 cho cả hai server: [[Phát hiện - liên hệ ẩn]].
