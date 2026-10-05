---
tags: [dự-án]
cập_nhật: 2026-10-06
---
# Việc cần làm

## Chờ bạn làm
AI không làm thay được.
- [x] `git status`, `git diff`, rồi commit phần [[Bilibili Dubbing]] và vault (2026-10-06)
- [ ] Thử thật giai đoạn 6 của [[Bilibili Dubbing]]: kiểm tra cookie trực tuyến, dọn job đã xong
- [ ] Thử dịch bằng Google với video chưa có phụ đề tiếng Việt
- [ ] Thử chuyển thư viện giữa hai ổ đĩa trên Windows
- [ ] Xác nhận để chuyển [[Bilibili Dubbing]] sang Stable ([[Định nghĩa xong#Chuyển sang Stable]])
- [ ] Nếu dùng GitHub Copilot: tự tạo `.github/copilot-instructions.md` (xem [[Quy ước vault]])
- [ ] **Xóa mã chết** (đã duyệt 2026-10-06; AI không có quyền xóa file trên máy nên bạn xóa tay, nên commit trước): `yt-subtitle-extension/content.js`, `content.js.bak`, `content.js.bak2`, `fix_vi_sub.ps1`, `fix_vi_sub_v2.ps1`, `modules/video_dubbing/ui_controller.py`, thư mục `Claude outputs/`. Xóa xong thì gạch mục này và bỏ phần "Mã chết" ở [[Trạng thái]]
- [ ] Thử `app.py` sau khi sửa: mở trang chủ, lồng tiếng một video ngắn, bật extension trên một video có phụ đề và nghe có giọng không (chỉ chạy `app.py`, không chạy `vi_sub_server.py`)

## Roadmap
- [ ] **Hợp nhất backend**: gộp [[Backend Flask]] vào [[Backend FastAPI]], chỉ chạy một server cổng 8000. Đọc [[Phát hiện - liên hệ ẩn#Hai server tranh một cổng, và extension chỉ đọc được với Flask]] trước.
- [ ] **Chuẩn hóa `requirements.txt`**: thiếu `edge-tts`, `pydub`, `faster-whisper`, `flask`, `flask-cors`, `gTTS`, `argostranslate`, `requests`.
- [ ] **Dọn file rác**: các mục mã chết ở [[Trạng thái]].
- [ ] **Cấu hình tập trung (`.env`)**: giọng mặc định, cổng, thư mục upload. Hiện giọng mặc định được khai ở 4 nơi.

## Đề xuất chưa được duyệt
- [ ] Hoàn thiện adapter `sites/phim.js` (selector đang để trống) — [[Vấn đề đã biết]] số 15

## Tạm dừng
- Whisper bóc băng trong [[Bilibili Dubbing]]

## Đã xong
- [x] [[Bilibili Dubbing]] giai đoạn 1 đến 6 (2026-10-05)
- [x] Dựng vault làm nguồn sự thật duy nhất, kèm quy ước và file chỉ đường cho AI (2026-10-05)
- [x] Duyệt toàn bộ quy ước, kể cả [[Quy ước git]] (2026-10-06)
- [x] Sửa `app.py`: file tạm của `/api/tts`, lọc tên file ở `/start-dubbing`, `TemplateResponse`, thêm `GET /api/tts` (2026-10-06)
- [x] CORS: quyết định để nguyên, QĐ-12 (2026-10-06)
