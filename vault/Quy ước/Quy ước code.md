---
tags: [quy-ước]
cập_nhật: 2026-10-05
---
# Quy ước code

Rút từ code thật của dự án. [[Bilibili Dubbing]] là mẫu chuẩn; code cũ ([[Video Dubbing]], [[Backend FastAPI]]) có nhiều chỗ không theo quy ước này nhưng là Stable nên **giữ nguyên, không sửa cho hợp chuẩn**. Quy ước áp dụng cho code mới.

## Định dạng file
- UTF-8, không BOM.
- File mới: xuống dòng LF.
- File có sẵn: **giữ đúng kiểu xuống dòng đang có.** Đang là CRLF: `app.py`, `core/config.py`, `modules/video_dubbing/ui_controller.py`, `AGENTS.md`, `yt-subtitle-extension/core.js`, `sites/*.js`. Phần còn lại là LF.
- Định danh (biến, hàm, lớp, file) bằng tiếng Anh. Docstring, comment, thông báo cho người dùng bằng tiếng Việt có dấu.

## Python
- Dòng đầu mỗi file: docstring một câu nói file này chịu trách nhiệm gì, rồi `from __future__ import annotations`.
- `snake_case` cho hàm, biến, file; `PascalCase` cho lớp; `UPPER_CASE` cho hằng.
- Có type hint cho tham số và giá trị trả về của hàm công khai.
- Dữ liệu thuần dùng `@dataclass`; cấu hình cố định dùng `@dataclass(frozen=True)`.
- Trạng thái dùng `class X(str, Enum)`, giá trị trùng tên (`QUEUED = "QUEUED"`). Không so sánh chuỗi trần.
- Không có số ma thuật rải rác: giới hạn và mặc định nằm trong lớp cấu hình của module (mẫu: `BilibiliSettings`).

## Tách tầng trong một module
```text
domain/    dataclass, enum, exception. Không import HTTP, không import SQLite.
storage/   repository chỉ đọc và ghi dữ liệu, không chứa nghiệp vụ.
<nghiệp vụ>/  service và pipeline: chứa logic, gọi repository.
api/       router chỉ nhận request, gọi service, trả response. Không chứa logic.
api/container.py  nơi duy nhất tạo và nối các đối tượng (dependency injection thủ công).
web/       HTML, CSS, JavaScript của module.
tests/     unittest.
```
Phụ thuộc chỉ đi một chiều: `api` → nghiệp vụ → `storage` → `domain`.

## Mở rộng bằng lớp con, không sửa code đang chạy
Chỗ nào sẽ có nhiều biến thể thì đặt một lớp trừu tượng (`ABC`) và thêm biến thể bằng lớp con. Mẫu hiện có: `BaseVideoSource`, `SubtitleProvider`, `Translator`, `PipelineStage`.

## Lỗi
- Mỗi module có **một cây exception** gốc riêng, mỗi lớp mang `code`, `http_status`, `message` (mẫu: `BilibiliError`).
- Router đổi exception thành mã HTTP và thông báo tiếng Việt. Service không trả mã HTTP.
- **Không nuốt lỗi im lặng.** `except Exception: pass` hoặc chỉ `print` rồi đi tiếp là cấm trong code mới. (Code cũ `tts_generator.generate_tts_for_subtitles` làm vậy, hệ quả là file mp3 0 byte mà không ai biết.)
- Thông báo lỗi phải nói người dùng làm gì tiếp, không chỉ nói cái gì hỏng.

## Đường dẫn và file
- Dùng `pathlib.Path`. Tính đường dẫn từ `__file__` (mẫu: `PROJECT_ROOT = Path(__file__).resolve().parents[2]`).
- **Không dùng đường dẫn tương đối theo thư mục chạy** như `"core/input"`. (Code cũ dùng, nên server buộc phải chạy từ thư mục gốc.)
- Mọi thao tác ghi và xóa của module đi qua **một lớp gác cổng** kiểm tra đường dẫn nằm trong thư mục được phép (mẫu: `StorageManager`, lỗi `UnsafePath`).
- Dữ liệu của module nằm ở `data/<tên_module>/` và phải có trong `.gitignore`.
- Trên Windows: không giữ handle file giữa các lần đọc; thao tác chuyển, xóa phải thử lại khi file đang bận.

## Dữ liệu
- SQLite, schema có số phiên bản. **Chỉ thêm migration mới, không sửa migration cũ.**
- Database lưu đường dẫn tương đối so với thư mục gốc dữ liệu, không lưu đường dẫn tuyệt đối.

## Trạng thái và xử lý nặng
- Không dùng biến toàn cục để giữ trạng thái xử lý. (Code cũ `status_state` trong `app.py` là biến toàn cục, nên chỉ theo dõi được một lần lồng tiếng tại một thời điểm.)
- Việc nặng (tải, Whisper, FFmpeg) chạy qua hàng đợi có worker, có hủy, có chạy lại, có tiếp tục sau khi khởi động lại (mẫu: `JobRunner`).
- Bước đã xong để lại file đánh dấu để chạy lại không làm lại.

## HTTP
- Trang của module ở `/<module>`, API ở `/api/<module>/…`.
- Body của request khai báo bằng schema pydantic trong `api/schemas.py`.
- Module gắn vào `app.py` bằng đúng `include_router`. Lỗi khi nạp module không được làm sập app.
- Không thêm endpoint trùng đường dẫn với endpoint có sẵn. Tra [[API]] trước.

## Thư viện
- Không thêm thư viện khi chưa được duyệt. Ưu tiên thư viện chuẩn của Python.
- Thư viện nặng hoặc không bắt buộc thì import trong hàm dùng nó, và báo thiếu qua endpoint `health` thay vì làm sập lúc khởi động.
- Thêm thư viện thì thêm vào `requirements.txt` trong cùng thay đổi.

## Gọi lại code cũ
- Gọi qua một lớp adapter trong module mới (mẫu: `DubMixer` bọc `media_mixer.mix_audio_to_video_advanced`).
- Chỉ gọi, không sửa. Ghi tên hàm được gọi vào ghi chú module và [[Phát hiện - liên hệ ẩn]].
- Đọc kỹ hàm cũ trước khi gọi: nó có thể làm nhiều hơn tên gọi (xem QĐ-02 trong [[Nhật ký quyết định]]).

## Ghi log
Code mới dùng `logging`. Không `print` trong service và pipeline.

## Giao diện web
HTML, CSS, JavaScript thuần, không framework, không bước build. File tĩnh nằm trong `web/static/` của module.

## Chrome extension
- Logic dùng chung ở `core.js`, mỗi phần là một khối `const Tên = (() => { … })()`.
- Mỗi trang web cần xử lý riêng là một lớp con của `SubtitleAdapter` trong `sites/`, khai báo trong `manifest.json`.
- Hằng cấu hình nằm trong `CONFIG` ở đầu `core.js`.

## Test
- `unittest`, đặt trong `modules/<module>/tests/`, tên file `test_<chủ đề>.py`.
- Test không cần mạng: nguồn ngoài (tải video, dịch, giọng đọc, bóc băng) thay bằng bản giả trong `tests/fakes.py`.
- Mỗi luồng người dùng chính có ít nhất một test trọn luồng.
- Sửa lỗi thì thêm test tái hiện lỗi trước.
