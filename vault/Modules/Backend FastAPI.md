---
tags: [module]
file: app.py
trạng_thái: đang dùng
cập_nhật: 2026-10-06
---
# Backend FastAPI

`app.py` (CRLF). Chạy: `python -m uvicorn app:app --reload --port 8000` từ thư mục gốc.

## Làm gì
- Phục vụ trang chủ `templates/index.html`.
- Điều khiển [[Video Dubbing]]: `/start-dubbing` chạy `run_dubbing_pipeline` bằng `BackgroundTasks`, tiến độ lưu trong biến toàn cục `status_state`.
- CRUD file qua [[File Manager]]: `/api/files…`.
- `/api/translate` (deep-translator) và `/api/tts` (edge-tts, nhận cả `POST` và `GET`) cho [[Chrome Extension]]. Phần sinh giọng nằm ở `_synthesize_tts`; file mp3 tạm được xóa sau khi gửi.
- Gắn [[Bilibili Dubbing]]: `from modules.bilibili_dubbing import router as bilibili_router` và `app.include_router(bilibili_router)`.
- CORS mở cho mọi nguồn.

Hợp đồng endpoint: [[API]].

## Quan hệ
- Được gọi bởi: `templates/index.html`, [[Chrome Extension]], trang `/bilibili`.
- Gọi tới: [[Video Dubbing]], [[File Manager]], [[Bilibili Dubbing]].

## Cấm đụng
- Tên endpoint, tên tham số form, hình dạng JSON.
- Kiểu xuống dòng CRLF.
- Thêm module mới chỉ bằng 2 dòng `import` + `include_router`.

## Cần biết trước khi sửa
- [[Vấn đề đã biết]] số 10, 11 (rủi ro đã chấp nhận), 14 còn mở; số 8, 12, 13, 17 đã sửa 2026-10-06.
- `index()` chọn kiểu gọi `TemplateResponse` theo `_TEMPLATE_REQUEST_FIRST` để chạy được với cả Starlette cũ và mới. Đừng gộp lại thành một kiểu.
- Trùng cổng và đường dẫn với [[Backend Flask]]: [[Phát hiện - liên hệ ẩn]].
