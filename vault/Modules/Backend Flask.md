---
tags: [module]
file: vi_sub_server.py
trạng_thái: đang dùng, dự kiến gộp
cập_nhật: 2026-10-06
---
# Backend Flask

`vi_sub_server.py` ("VI-Sub server v3"). Chạy: `python vi_sub_server.py` → `127.0.0.1:8000`.

## Làm gì
- `POST /api/translate`: Argos Translate offline (tự tải gói EN→VI lần đầu); Argos chưa sẵn sàng thì gọi Google qua `requests`, thử lại khi bị 429. Cache 2000 câu trong bộ nhớ.
- `GET`/`POST /api/tts`: `gTTS`, cache 300 đoạn trong bộ nhớ.
- `GET /health`.

## Quan hệ
- Được gọi bởi: [[Chrome Extension]]. Từ 2026-10-06 [[Backend FastAPI]] cũng có `GET /api/tts`, nên server này không còn là nơi duy nhất cho extension có giọng.
- Không gọi module nào của dự án.

## Tương lai
Gộp vào [[Backend FastAPI]]: [[Việc cần làm#Roadmap]]. Trước khi gộp đọc [[Phát hiện - liên hệ ẩn]].
