---
tags: [dự-án]
cập_nhật: 2026-10-06
---
# Change log

Chỉ thêm, không sửa dòng cũ. Mỗi dòng: ngày, việc, và **file nào ngoài module bị đụng**. Mục mới thêm ở cuối.

- **2026-10-05**: Khởi tạo file `PROJECT_STATUS.md` & `ARCHITECTURE.md` để khoanh vùng bảo mật code và quản lý tiến độ chuẩn cho AI/Dev.
- **2026-10-05**: Thêm module `modules/bilibili_dubbing/` (giai đoạn 1: quét link Bilibili). Thay đổi ngoài module: 2 dòng code (kèm 1 dòng chú thích) `include_router` trong `app.py`, thêm `yt-dlp` vào `requirements.txt`, thêm `data/bilibili_dubbing/` vào `.gitignore`. Không sửa module Stable nào.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 2: tải video và phụ đề có sẵn, hàng đợi job, thư viện phát trực tiếp trên web. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 3: phụ đề, dịch, duyệt. Dùng lại nguyên trạng `sub_handler.load_subtitles` và hai hàm của `dynamic_subtitle.py` (chỉ gọi, không sửa). Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 4: lồng tiếng. Gọi lại nguyên trạng `media_mixer.mix_audio_to_video_advanced` và `tts_generator.sanitize_vietnamese_text`; không dùng `generate_tts_for_subtitles` vì hàm đó tự dịch lại. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 5: quản lý thư viện, nơi lưu, dung lượng. Thư viện không bao giờ được đặt trong `core/`, `modules/`, `templates/`, `yt-subtitle-extension/`. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 6 (hoàn thiện) và README của module. Whisper tự lùi xuống model nhẹ hơn khi thiếu RAM. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Dựng `vault/` làm nguồn sự thật duy nhất. Nội dung của `PROJECT_STATUS.md` và `ARCHITECTURE.md` chuyển vào vault; hai file đó cùng `AGENTS.md` và `.agents/rules/strict_permissions.md` được viết lại thành trang chỉ đường. Thêm `CLAUDE.md`, `.cursor/rules/life-os.mdc`. Không đụng file code nào. Bản gốc nguyên văn của 4 file được lưu trong `vault/Lưu trữ/`.
- **2026-10-06**: Sửa `app.py` theo yêu cầu trực tiếp của người dùng: xóa file mp3 tạm của `/api/tts` sau khi gửi; lọc `basename` cho `video_name`, `subtitle_name` ở `/start-dubbing`; `TemplateResponse` tự nhận kiểu gọi theo phiên bản Starlette; thêm `GET /api/tts?text=` (giữ nguyên `POST`). Không đổi tên endpoint hay JSON nào có sẵn. Giữ CRLF. Chỉ đụng `app.py` và vault.
- **2026-10-06**: Người dùng duyệt bộ quy ước (QĐ-14), giữ CORS mở (QĐ-12), cho xóa mã chết (chờ xóa tay).
