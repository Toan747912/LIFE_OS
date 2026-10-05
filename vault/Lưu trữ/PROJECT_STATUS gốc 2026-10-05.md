# BÁO CÁO TIẾN ĐỘ & PHẠM VI QUẢN LÝ DỰ ÁN LIFE_OS

> **Lưu ý dành cho AI / Developer**: File này chứa danh sách các chức năng đã hoàn thành, khu vực cấm sửa bậy (NO-TOUCH), và các hạng mục cần nâng cấp tiếp theo. **Mọi AI làm việc trên project BẮT BUỘC phải tuân thủ trạng thái trong file này.**

---

## 1. 🟢 Danh Sách Tính Năng Đã Hoàn Thành (STABLE - NO TOUCH)

Các module dưới đây đã được kiểm thử và hoạt động ổn định. **KHÔNG TỰ Ý SỬA ĐỔI LOGIC HOẶC REFACTOR** trừ khi người dùng yêu cầu trực tiếp.

| Module / File | Chức Năng Chính | Trạng Thái | Ghi Chú An Toàn |
| :--- | :--- | :--- | :--- |
| `modules/video_dubbing/service.py` | Pipeline điều phối lồng tiếng video chính | 🟢 Stable | Cấm sửa logic `run_dubbing_pipeline` |
| `modules/video_dubbing/tts_generator.py` | Tạo audio từ phụ đề dùng Edge-TTS (Auto-speed matching) | 🟢 Stable | Cấm đổi tham số khớp tốc độ audio |
| `modules/video_dubbing/media_mixer.py` | Ghép Audio & Video bằng FFmpeg | 🟢 Stable | Cấm sửa các câu lệnh FFmpeg ghép mix âm thanh |
| `modules/video_dubbing/sub_handler.py` | Đọc và xử lý file phụ đề (`.vtt`, `.srt`) | 🟢 Stable | Xử lý tốt encoding UTF-8 |
| `modules/dynamic_subtitle.py` | AI bóc băng tiếng bằng `faster-whisper` tạo phụ đề ASS | 🟢 Stable | Cấm sửa template hiệu ứng ASS |
| `modules/file_manager.py` | Quản lý File upload/rename/delete trong `core/input/` | 🟢 Stable | Cấm đổi đường dẫn `UPLOAD_DIR` |
| `yt-subtitle-extension/` | Chrome Extension dịch & đọc phụ đề YouTube | 🟢 Stable | Giữ nguyên logic inject DOM và giao diện extension |

---

## 2. 🟡 Hạng Mục Đang Phát Triển / Cần Nâng Cấp (IN PROGRESS & ROADMAP)

Các công việc ưu tiên nâng cấp tiếp theo để dự án sạch sẽ và dễ bảo trì hơn:

- [ ] **Hợp nhất Backend**: Gộp Flask server (`vi_sub_server.py`) vào FastAPI (`app.py`) để chỉ chạy 1 port 8000 duy nhất.
- [ ] **Chuẩn hóa `requirements.txt`**: Khai báo đầy đủ các thư viện (`edge-tts`, `flask`, `gtts`, `argostranslate`, `faster-whisper`, v.v.).
- [ ] **Dọn dẹp File Rác**: Xóa các file backup không dùng đến (`content.js.bak`, `content.js.bak2`, các script `.ps1` rải rác).
- [ ] **Cấu hình Tập trung (`.env`)**: Đưa các tham số như Voice mặc định, Port, Upload Directory ra file cấu hình chung.
- [x] **Module Bilibili Dubbing (`modules/bilibili_dubbing/`)** — 🟢 Đã xong 6 giai đoạn (chờ người dùng xác nhận để chuyển sang bảng STABLE). Module độc lập, tự chứa code, dữ liệu ở `data/bilibili_dubbing/`. Thiết kế: 6 giai đoạn.
  - [x] Giai đoạn 1 — Khung module, SQLite, quét link (tập / chất lượng / phụ đề), trang `/bilibili`.
  - [x] Giai đoạn 2 — Tải video, hàng đợi job (1 worker, hủy / chạy lại / tiếp tục sau khi khởi động lại), thư viện tối thiểu (xem, tua, tải xuống, xóa). Cookie đăng nhập ở tab Cài đặt.
  - [x] Giai đoạn 3 — Phụ đề gốc từ 3 nguồn (có sẵn / Whisper / upload), dịch sang tiếng Việt, màn hình duyệt và sửa. Video vào thư viện kèm phụ đề tiếng Việt đã duyệt.
  - [x] Giai đoạn 4 — Sinh giọng đọc tiếng Việt từ phụ đề đã duyệt (khớp tốc độ, thử lại, dùng lại câu đã sinh) và trộn vào video bằng `media_mixer` cũ. Tùy chọn giữ video gốc.
  - [x] Giai đoạn 5 — Quản lý thư viện: đổi tên, ghi chú, series, tag, tìm kiếm không dấu, lọc, sắp xếp; đổi nơi lưu (sao chép, kiểm tra, rồi mới xóa nơi cũ); thống kê dung lượng và dọn dẹp; cài đặt mặc định và model Whisper.
  - [x] Giai đoạn 6 — Hoàn thiện: kiểm tra cookie trực tuyến (bilibili.com), dọn job đã hoàn tất, báo thiếu phụ thuộc ở đầu trang, test lô 3 video, `modules/bilibili_dubbing/README.md`.
  - Tạm dừng: Whisper bóc băng (vẫn chạy, gắn nhãn thử nghiệm; cần nhiều RAM). Chưa thử với dữ liệu thật: dịch bằng Google.

---

## 3. 🔴 Quy Tắc Cấm Đụng Vào (STRICT NO-TOUCH RULES)

1. **Không tự ý refactor code đang chạy tốt**: Đang có ứng dụng đang dùng ổn định, việc refactor không theo yêu cầu sẽ gây hỏng tính năng cũ (Regression).
2. **Không tự xóa/thay đổi hàm API Endpoint**: Giữ nguyên tên endpoint API (`/start-dubbing`, `/api/files`, `/api/translate`, `/api/tts`) vì Chrome Extension và Frontend HTML đang gọi đến.
3. **Không thay đổi cấu trúc dữ liệu trả về (API Contracts)**: Giữ nguyên định dạng JSON response.

---

## 4. 📝 Lịch Sử Thay Đổi (Change Log)

- **2026-10-05**: Khởi tạo file `PROJECT_STATUS.md` & `ARCHITECTURE.md` để khoanh vùng bảo mật code và quản lý tiến độ chuẩn cho AI/Dev.
- **2026-10-05**: Thêm module `modules/bilibili_dubbing/` (giai đoạn 1: quét link Bilibili). Thay đổi ngoài module: 2 dòng code (kèm 1 dòng chú thích) `include_router` trong `app.py`, thêm `yt-dlp` vào `requirements.txt`, thêm `data/bilibili_dubbing/` vào `.gitignore`. Không sửa module Stable nào.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 2: tải video và phụ đề có sẵn, hàng đợi job, thư viện phát trực tiếp trên web. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 3: phụ đề, dịch, duyệt. Dùng lại nguyên trạng `sub_handler.load_subtitles` và hai hàm của `dynamic_subtitle.py` (chỉ gọi, không sửa). Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 4: lồng tiếng. Gọi lại nguyên trạng `media_mixer.mix_audio_to_video_advanced` và `tts_generator.sanitize_vietnamese_text`; không dùng `generate_tts_for_subtitles` vì hàm đó tự dịch lại. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 5: quản lý thư viện, nơi lưu, dung lượng. Thư viện không bao giờ được đặt trong `core/`, `modules/`, `templates/`, `yt-subtitle-extension/`. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
- **2026-10-05**: Module Bilibili Dubbing giai đoạn 6 (hoàn thiện) và README của module. Whisper tự lùi xuống model nhẹ hơn khi thiếu RAM. Không có thay đổi nào ngoài `modules/bilibili_dubbing/` và hai file tài liệu này.
