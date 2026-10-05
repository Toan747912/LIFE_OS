---
tags: [quyết-định]
cập_nhật: 2026-10-06
---
# Nhật ký quyết định

Mỗi quyết định: bối cảnh, lựa chọn, lý do. Thêm mục mới ở cuối theo [[Mẫu quyết định]]. Không sửa mục cũ; đổi ý thì viết mục mới và ghi "thay thế QĐ-xx".

## QĐ-01 · Module mới phải tách riêng, không đụng module Stable
- **Ngày:** 2026-10-05
- **Bối cảnh:** thêm [[Bilibili Dubbing]] vào dự án đang chạy ổn.
- **Chọn:** toàn bộ code trong `modules/bilibili_dubbing/`; ngoài module chỉ đụng `app.py` (2 dòng `include_router`), `requirements.txt`, `.gitignore` và tài liệu.
- **Lý do:** tránh hỏng [[Video Dubbing]], [[Dynamic Subtitle]], [[File Manager]], [[Chrome Extension]].
- **Thành quy ước chung:** [[Thêm module mới]].

## QĐ-02 · Gọi lại code cũ nguyên trạng thay vì viết lại
- **Chọn:** dùng `sub_handler.load_subtitles`, `media_mixer.mix_audio_to_video_advanced`, `tts_generator.sanitize_vietnamese_text`, `dynamic_subtitle.extract_temp_audio`, `dynamic_subtitle.transcribe_audio_word_level`.
- **Không dùng:** `tts_generator.generate_tts_for_subtitles`, vì hàm này tự dịch lại từng câu và sẽ ghi đè bản dịch người dùng đã duyệt.
- **Hệ quả:** [[Bilibili Dubbing]] có `TtsSynthesizer` riêng.

## QĐ-03 · Cookie lưu ở `data/bilibili_dubbing/cookies.txt`
- Không trả cookie ngược ra trình duyệt; chỉ giữ cookie của Bilibili; thư mục `data/bilibili_dubbing/` nằm trong `.gitignore`.

## QĐ-04 · Không thêm link Bilibili vào `templates/index.html`
- **Lý do:** `index.html` thuộc phần ổn định. Module có trang riêng tại `/bilibili`.

## QĐ-05 · Whisper của Bilibili mặc định model `small`
- Code cũ mặc định `base`; `small` nhận dạng tiếng Trung tốt hơn, chậm hơn trên CPU.
- Sau đó gặp lỗi thiếu RAM, đã thêm cơ chế tự lùi xuống model nhẹ hơn. Xem [[Vấn đề đã biết]] số 1.

## QĐ-06 · Thư viện được duyệt: `yt-dlp` và SQLite; test bằng `unittest`
- **Lý do:** luật cấm tự thêm thư viện; SQLite và `unittest` có sẵn trong Python.

## QĐ-07 · Không vượt khóa vùng, VIP, DRM
- Nội dung tài khoản không xem được thì báo rõ ở bước quét.

## QĐ-08 · Thư viện video không được đặt trong thư mục của chức năng khác
- Cấm `core/`, `modules/`, `templates/`, `yt-subtitle-extension/`, `.git`. Đổi nơi lưu theo thứ tự: sao chép, kiểm tra, đổi cấu hình, rồi mới xóa nơi cũ.

## QĐ-09 · Vault là nguồn sự thật duy nhất
- **Ngày:** 2026-10-05
- **Bối cảnh:** luật và trạng thái nằm ở `AGENTS.md`, `PROJECT_STATUS.md`, `ARCHITECTURE.md`, `.agents/rules/`, cộng thêm vault → dễ lệch nhau.
- **Chọn:** chuyển toàn bộ nội dung vào `vault/`; các file ở thư mục gốc chỉ còn là trang chỉ đường.
- **Phương án đã loại:** giữ 3 file gốc làm chính (thông tin ở hai nơi); để vault đầy đủ nhưng không đụng file gốc (hai bản sẽ lệch).
- **Hệ quả:** quy tắc "cập nhật `PROJECT_STATUS.md` sau mỗi nhiệm vụ" đổi thành cập nhật [[Trạng thái]] và [[Change log]].

## QĐ-10 · Mỗi công cụ AI có một file chỉ đường, luật cứng chép ở 3 nơi
- **Ngày:** 2026-10-05
- **Bối cảnh:** dự án dùng Claude, Antigravity/Gemini, Cursor/Copilot/Codex và ChatGPT dán tay; mỗi công cụ tự đọc một tên file khác nhau, có công cụ không mở được liên kết.
- **Chọn:** `AGENTS.md` là cửa vào chung; `CLAUDE.md`, `.cursor/rules/` trỏ về nó (file cho Copilot ở `.github/` chưa tạo được, Copilot dùng `AGENTS.md`); luật cứng được chép ở `AGENTS.md`, `.agents/rules/strict_permissions.md` và [[Tóm tắt dán tay]].
- **Cái giá:** sửa luật cứng phải sửa 4 nơi (kể cả [[Bắt đầu ở đây]]). Ghi trong [[Quy ước vault]].

## QĐ-11 · [[Bilibili Dubbing]] là mẫu chuẩn cho code mới
- **Ngày:** 2026-10-05
- **Chọn:** [[Quy ước code]] rút từ module này. Code cũ không theo chuẩn được giữ nguyên vì là Stable.

## QĐ-12 · Giữ CORS mở cho mọi nguồn
- **Ngày:** 2026-10-06
- **Bối cảnh:** `app.py` đặt `allow_origins=["*"]` kèm `DELETE`, nên trang web bất kỳ có thể gọi API cục bộ ([[Vấn đề đã biết]] số 11).
- **Chọn:** để nguyên, coi là rủi ro đã chấp nhận.
- **Phương án đã loại:** bỏ `DELETE` và `PUT` khỏi CORS.
- **Lý do:** [[Chrome Extension]] gọi API từ chính trang web đang xem (YouTube, Coursera…), siết theo nguồn sẽ làm hỏng extension; ứng dụng chỉ chạy cục bộ cho một người dùng.
- **Xem lại khi:** ứng dụng được mở ra mạng ngoài máy.

## QĐ-13 · Thêm `GET /api/tts` vào FastAPI, giữ nguyên `POST`
- **Ngày:** 2026-10-06
- **Bối cảnh:** extension phát giọng bằng `GET /api/tts?text=`, `app.py` chỉ có `POST` ([[Vấn đề đã biết]] số 17).
- **Chọn:** thêm phương thức `GET` dùng chung phần xử lý với `POST`; không đổi gì ở `POST`, không sửa extension.
- **Hệ quả:** chạy `app.py` thì extension đọc bằng edge-tts; chạy `vi_sub_server.py` thì đọc bằng gTTS. Bước mở đường cho việc gộp backend.

## QĐ-14 · Duyệt bộ quy ước và cho xóa mã chết
- **Ngày:** 2026-10-06
- Người dùng duyệt toàn bộ trang luật và quy ước trong vault, kể cả [[Quy ước git]].
- Người dùng cho xóa mã chết liệt kê ở [[Trạng thái]]. AI không xóa được file trên máy nên việc xóa nằm ở [[Việc cần làm]].
