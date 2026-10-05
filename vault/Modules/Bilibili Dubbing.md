---
tags: [module]
file: modules/bilibili_dubbing/
trạng_thái: chờ xác nhận
cập_nhật: 2026-10-05
---
# Bilibili Dubbing

Dán link Bilibili → quét → tải → dịch và duyệt phụ đề → lồng tiếng Việt → xem, tải, quản lý trong thư viện. Trang riêng `/bilibili`, API `/api/bilibili/…` ([[API]]). Hướng dẫn sử dụng: `modules/bilibili_dubbing/README.md`.

Đây là **module mẫu** của dự án: [[Quy ước code]], [[Thêm module mới]].

## Cấu trúc
| Thư mục | Lớp chính | Vai trò |
| --- | --- | --- |
| `config.py` | `BilibiliSettings` | Đường dẫn, giới hạn, mặc định (cố định khi khởi động) |
| `domain/` | `Job`, `JobSpec`, `LibraryItem`, `ScanResult`, `Episode`, `JobStatus`, `BilibiliError` và 12 lớp con | Dữ liệu thuần, enum, cây exception |
| `sources/` | `BaseVideoSource` (ABC), `BilibiliSource` (yt-dlp), `SourceRegistry`, `ScanService` | Quét và tải |
| `subtitles/` | `SubtitleDocument`, `SubtitleProvider` (ABC) + `Platform`/`Whisper`/`Uploaded`, `Translator` (ABC) + `GoogleTranslatorAdapter` | Phụ đề và dịch |
| `dubbing/` | `TtsSynthesizer`, `DubMixer` | Giọng đọc; adapter gọi bộ trộn cũ |
| `media/` | `FfmpegTools` | ffprobe, đổi phụ đề sang WebVTT |
| `pipeline/` | `PipelineStage` (ABC) + 7 stage, `DubbingPipeline`, `JobRunner`, `JobService`, `ReviewService`, `JobContext` | Luồng job |
| `storage/` | `Database`, 6 repository, `StorageManager`, `LibraryService`, `StorageService`, `LibraryMover`, `CookieStore`, `CookieChecker`, `AppSettingsService` | SQLite, file, cookie |
| `api/` | `router`, `schemas`, `ServiceContainer`, `range_response` | HTTP và nối đối tượng |
| `web/` | `bilibili.html`, `static/bilibili.js`, `static/bilibili.css` | Giao diện một trang |
| `tests/` | `fakes.py`, `support.FlowTestCase`, các `test_*.py` | 132 test |

## Luồng job
`QUEUED` → `DOWNLOADING` → `PREPARING_SUBS` → `TRANSLATING` → `AWAITING_REVIEW` (dừng chờ người dùng duyệt) → `SYNTHESIZING` → `MIXING` → `PUBLISHING` → `DONE`.
- Thiếu phụ đề thì job dừng ở `AWAITING_SUBTITLE` chờ upload file hoặc chuyển sang Whisper.
- Job đang chờ không chiếm worker; worker xử lý job kế tiếp.
- Lỗi: `FAILED` (chạy lại được, stage đã xong được bỏ qua nhờ file đánh dấu trong `work/<job_id>/`).
- Phụ đề gốc đã là tiếng Việt thì bỏ qua bước dịch.
- Một worker thread xử lý lần lượt; job dang dở được tiếp tục khi module được dùng lần đầu sau khi khởi động lại server.

Stage dừng chờ bằng `PipelinePause`. File đánh dấu trong `work/<job_id>/`: `download.json`, `subtitle.json`, `translate.done`, `review.approved`, `subs.vi.vtt`, `tts/` (mp3 + `tts.partial.json`), `tts.json`, `dubbed.mp4`, `mix.json`.

## Lồng tiếng
- Đầu vào là cột `vi_text` của bảng `cues` (bản đã duyệt); câu để trống không được đọc.
- Mỗi câu được đọc ở tốc độ thường; nếu dài hơn khung thời gian quá 5% thì đọc lại nhanh hơn, tối đa +50%. Khung thời gian tính tới lúc câu kế tiếp bắt đầu.
- Mỗi câu thử tối đa 3 lần; câu đã đọc xong được ghi vào `work/<job_id>/tts/tts.partial.json` để chạy lại không phải đọc lại.
- Thư viện: `GET /api/bilibili/library/{id}/stream?kind=source` và `/download?kind=source` trả video gốc khi người dùng chọn giữ lại.
- 3 câu đọc song song, mỗi lô 12 câu.

## Đổi nơi lưu thư viện
- Đích phải là đường dẫn tuyệt đối, trống (hoặc là thư viện cũ của module), không nằm trong thư viện hiện tại, thư mục làm việc tạm, hay thư mục của chức năng khác (`core/`, `modules/`, `templates/`, `yt-subtitle-extension/`).
- Thứ tự: tạm dừng worker, sao chép từng video, so khớp danh sách file và kích thước, đổi cấu hình `library_root`, rồi mới xóa nơi cũ. Lỗi giữa chừng thì xóa phần đã sao chép và thư viện vẫn ở nơi cũ.
- Bị từ chối khi đang có job chạy dở. Job tạo trong lúc chuyển được xếp hàng và chạy sau khi chuyển xong.

## Bốn điểm mở rộng
Thêm lớp con, không sửa code đang chạy: `BaseVideoSource` (nền tảng video mới) · `SubtitleProvider` (nguồn phụ đề) · `Translator` (dịch vụ dịch) · `PipelineStage` (bước xử lý).

## Quan hệ
- Được gắn vào [[Backend FastAPI]] bằng `include_router`.
- Gọi lại, không sửa: [[Video Dubbing]] (`load_subtitles`, `mix_audio_to_video_advanced`, `sanitize_vietnamese_text`), [[Dynamic Subtitle]] (`extract_temp_audio`, `transcribe_audio_word_level`).
- Thư viện: `yt-dlp`, `edge-tts`, `deep-translator`, `faster-whisper` (không bắt buộc), SQLite.

## Dữ liệu
```text
data/bilibili_dubbing/
├── bilibili.db      # SQLite, schema v2: job, câu phụ đề, thư viện, series, tag, cài đặt
├── cookies.txt      # chỉ có khi đã nhập cookie
├── work/<job_id>/   # file tạm của job
└── library/<id>/    # thư viện (đổi được nơi lưu)
```
Module chỉ ghi và xóa trong `work/` và thư mục thư viện, mọi đường dẫn qua `StorageManager`. Xóa video là xóa hẳn.

## Cấm đụng (khi vào Stable)
- Schema: chỉ thêm migration mới.
- Tên và hình dạng JSON của `/api/bilibili/…`.
- Tên file đánh dấu trong `work/` (job dang dở dựa vào đó để chạy tiếp).
- Giới hạn ghi/xóa của `StorageManager` và danh sách `protected_dirs`.

## Khi test trong sandbox
Cần chép từ máy người dùng: `modules/video_dubbing/{sub_handler,tts_generator,media_mixer}.py`, `modules/dynamic_subtitle.py`; cài `pydub`, `edge-tts` (và `audioop-lts` nếu Python 3.13). Không ghi ngược các file đó về máy. Chromium trong sandbox không giải mã H.264/AAC: thử trình phát bằng VP9+Opus.

## Xem thêm
[[Nhật ký quyết định]] QĐ-01 đến QĐ-08 · [[Vấn đề đã biết]] số 1, 2, 3, 5, 6, 7 · [[Việc cần làm]]
