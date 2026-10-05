# KIẾN TRÚC VÀ BẢN ĐỒ DỰ ÁN LIFE_OS

File này mô tả tổng quan kiến trúc phần mềm, cấu trúc thư mục, danh sách API và luồng dữ liệu của hệ thống **LIFE_OS**.

---

## 1. 🏗️ Tổng Quan Kiến Trúc (Architecture Overview)

Dự án gồm **3 khối thành phần chính**:

```text
+-----------------------------------------------------------------------+
|                         CHROME EXTENSION                              |
|                   (yt-subtitle-extension/)                            |
|    - Inject phụ đề tiếng Việt trên YouTube/Web                        |
|    - Gọi API dịch /api/translate & TTS /api/tts                       |
+-----------------------------------+-----------------------------------+
                                    |
                                    v (HTTP Requests)
+-----------------------------------+-----------------------------------+
|                        FASTAPI / FLASK BACKEND                        |
|              (app.py / vi_sub_server.py / port 8000)                  |
|    - Quản lý file Upload (core/input/)                                |
|    - Cung cấp API Dịch (deep-translator / argostranslate)             |
|    - Cung cấp API TTS (edge-tts / gTTS)                               |
+-----------------------------------+-----------------------------------+
                                    |
                                    v (Python Internal Calls)
+-----------------------------------+-----------------------------------+
|                     CORE VIDEO DUBBING PIPELINE                       |
|                     (modules/video_dubbing/)                          |
|    - sub_handler.py: Parse VTT/SRT                                    |
|    - tts_generator.py: Sinh âm thanh lồng tiếng                       |
|    - dynamic_subtitle.py: AI faster-whisper bóc băng                  |
|    - media_mixer.py: FFmpeg Trộn Audio + Video                        |
+-----------------------------------------------------------------------+
```

---

## 2. 📁 Cấu Trúc Thư Mục & Vai Trò Các File

```text
LIFE_OS/
├── AGENTS.md                 # Quy tắc an toàn & phạm vi hoạt động của AI
├── PROJECT_STATUS.md         # Báo cáo tiến độ, các module Stable & Roadmap
├── ARCHITECTURE.md           # File này - Bản đồ kiến trúc hệ thống
├── app.py                    # Server FastAPI chính (Quản lý File & Video Dubbing API)
├── vi_sub_server.py          # Server Flask phụ (Phục vụ Chrome Extension Dịch & TTS)
├── main.py                   # Giao diện dòng lệnh (CLI Menu)
├── requirements.txt          # Danh sách thư viện Python cần thiết
├── core/
│   ├── config.py             # Cấu hình đường dẫn đầu vào/đầu ra
│   ├── input/                # Thư mục chứa file Video & Subtitle tải lên
│   └── output/               # Thư mục xuất Video lồng tiếng kết quả
├── modules/
│   ├── file_manager.py       # Xử lý CRUD file vật lý trên đĩa
│   ├── dynamic_subtitle.py   # AI Whisper trích xuất phụ đề động ASS
│   └── video_dubbing/        # Pipeline lồng tiếng video chính
│       ├── service.py        # Controller chính điều phối quy trình lồng tiếng
│       ├── sub_handler.py    # Xử lý đọc file phụ đề
│       ├── tts_generator.py  # Sinh giọng đọc Edge-TTS
│       └── media_mixer.py    # Trộn âm thanh và video bằng FFmpeg
├── templates/
│   └── index.html            # Giao diện Web Frontend
└── yt-subtitle-extension/    # Extension Chrome dịch phụ đề trực tiếp
```

---

## 3. 🌐 Danh Sách API Endpoints Hiện Có

### Backend Web (`app.py` - FastAPI)
- `GET /`: Mở giao diện trang chủ Web.
- `POST /start-dubbing`: Nhận cấu hình và chạy quy trình lồng tiếng video trong background.
- `GET /status`: Lấy phần trăm tiến độ xử lý video.
- `GET /download-video`: Tải về file video kết quả (`output_final.mp4`).
- `GET /api/files`: Liệt kê các file video/sub trong `core/input/`.
- `POST /api/files/upload`: Tải file mới lên `core/input/`.
- `PUT /api/files/rename`: Đổi tên file.
- `DELETE /api/files/{filename}`: Xóa file khỏi đĩa.
- `POST /api/translate`: Dịch văn bản tiếng Anh sang tiếng Việt (`deep-translator`).
- `POST /api/tts`: Sinh giọng đọc MP3 từ văn bản tiếng Việt (`edge-tts`).

### Extension Server (`vi_sub_server.py` - Flask)
- `POST /api/translate`: Dịch offline (`argostranslate`) hoặc online fallback.
- `POST /api/tts`: Sinh giọng đọc MP3 bằng `gTTS`.
- `GET /health`: Kiểm tra sức khỏe của server.

---

## 4. 🎬 Module Bilibili Dubbing (`modules/bilibili_dubbing/`)

Module độc lập, gắn vào `app.py` bằng `include_router`. Không sửa và không ghi vào thư mục của các module khác; dữ liệu nằm ở `data/bilibili_dubbing/` (SQLite `bilibili.db`, `cookies.txt`, `work/`, `library/`).

```text
modules/bilibili_dubbing/
├── config.py        # BilibiliSettings: đường dẫn và giới hạn
├── domain/          # models (dataclass), enums, errors (BilibiliError)
├── sources/         # BaseVideoSource (ABC), BilibiliSource (yt-dlp), SourceRegistry, ScanService
├── media/           # FfmpegTools: đọc thông tin video, đổi phụ đề sang WebVTT
├── dubbing/         # TtsSynthesizer (edge-tts, khớp tốc độ), DubMixer (adapter gọi media_mixer cũ)
├── subtitles/       # SubtitleDocument, SubtitleProvider (ABC) + Platform/Whisper/Uploaded, Translator (ABC) + Google
├── pipeline/        # PipelineStage (ABC) + Download/Subtitle/Translate/Review/Synthesize/Mix/Publish, DubbingPipeline, JobRunner,
│                    # JobService, ReviewService
├── storage/         # Database, repositories, CookieStore, StorageManager (giới hạn ghi/xóa), LibraryService,
│                    # StorageService (dung lượng, dọn dẹp), LibraryMover (đổi nơi lưu), AppSettingsService
├── api/             # router (APIRouter), schemas, container (dependency injection)
├── web/             # bilibili.html + static/ (giao diện riêng tại /bilibili)
└── tests/           # unittest: python -m unittest discover -s modules/bilibili_dubbing/tests -t .
```

### Endpoints
- `GET /bilibili`: Giao diện của module.
- `GET /api/bilibili/health`: Tình trạng yt-dlp, ffmpeg, cookie, phiên bản schema.
- `POST /api/bilibili/scan`: Quét danh sách link, trả về tập, chất lượng, phụ đề (không tải video).
- `GET /api/bilibili/scan/{scan_id}`: Lấy lại kết quả quét đã lưu.
- `POST /api/bilibili/scan/{scan_id}/probe`: Quét chi tiết một tập chưa quét (series dài).
- `GET /api/bilibili/settings/cookie`: Trạng thái cookie đăng nhập (không trả giá trị cookie).
- `PUT /api/bilibili/settings/cookie`: Lưu cookie từ nội dung dán vào (cookies.txt, JSON, chuỗi header hoặc SESSDATA).
- `DELETE /api/bilibili/settings/cookie`: Xóa cookie đã lưu.
- `POST /api/bilibili/jobs`: Tạo job từ các tập đã chọn (thông tin tải lấy từ kết quả quét đã lưu).
- `GET /api/bilibili/jobs`, `GET /api/bilibili/jobs/{id}`: Danh sách và chi tiết job (trạng thái, tiến độ, lỗi).
- `POST /api/bilibili/jobs/{id}/cancel`, `POST /api/bilibili/jobs/{id}/retry`, `DELETE /api/bilibili/jobs/{id}`: Hủy, chạy lại, xóa job.
- `GET /api/bilibili/library`, `GET /api/bilibili/library/{id}`, `DELETE /api/bilibili/library/{id}`: Thư viện video.
- `GET /api/bilibili/library/{id}/stream`: Phát video, hỗ trợ tua (HTTP Range).
- `GET /api/bilibili/library/{id}/subtitle`, `/thumbnail`, `/download`: Phụ đề WebVTT, ảnh thu nhỏ, tải video về máy.

- `POST /api/bilibili/jobs/{id}/subtitle`: Upload file `.srt`/`.vtt` cho job đang chờ phụ đề.
- `POST /api/bilibili/jobs/{id}/use-whisper`: Job đang chờ phụ đề chuyển sang Whisper bóc băng.
- `GET`, `PUT /api/bilibili/jobs/{id}/cues`: Đọc và lưu các câu phụ đề (gốc + tiếng Việt) khi duyệt.
- `POST /api/bilibili/jobs/{id}/approve`: Duyệt bản dịch, job chạy tiếp.
- `GET /api/bilibili/jobs/{id}/preview`: Video gốc của job để xem lại cảnh khi duyệt (HTTP Range).

- `GET /api/bilibili/library?q=&series=&tag=&status=&sort=`: Tìm kiếm không dấu và lọc.
- `PATCH /api/bilibili/library/{id}`: Đổi tên, ghi chú, series, tag (chỉ đổi thông tin, không đổi file).
- `GET /api/bilibili/series`, `PATCH`, `DELETE /api/bilibili/series/{id}`; `GET /api/bilibili/tags`, `DELETE /api/bilibili/tags/{id}`: Quản lý series và tag. Xóa series hay tag không xóa video.
- `GET /api/bilibili/storage`: Thư mục thư viện, dung lượng, ổ đĩa còn trống, các mục dọn được, tiến độ chuyển thư viện.
- `PUT /api/bilibili/storage/root`: Chuyển thư viện sang thư mục khác (chạy nền).
- `POST /api/bilibili/storage/cleanup`: Dọn các mục đã chọn (`stopped_jobs`, `orphan_work`, `kept_sources`, `orphan_library`).
- `GET`, `PUT /api/bilibili/settings`: Giọng, âm lượng, giữ video gốc mặc định và model Whisper.
- `POST /api/bilibili/settings/cookie/check`: Hỏi máy chủ bilibili.com xem cookie còn đăng nhập được không.
- `POST /api/bilibili/jobs/clear-finished`: Dọn các job đã hoàn tất khỏi hàng đợi (video được giữ nguyên).

Hướng dẫn sử dụng, cấu trúc và giới hạn đã biết: xem `modules/bilibili_dubbing/README.md`.

### Đổi nơi lưu thư viện
- Đích phải là đường dẫn tuyệt đối, trống (hoặc là thư viện cũ của module), không nằm trong thư viện hiện tại, thư mục làm việc tạm, hay thư mục của chức năng khác (`core/`, `modules/`, `templates/`, `yt-subtitle-extension/`).
- Thứ tự: tạm dừng worker, sao chép từng video, so khớp danh sách file và kích thước, đổi cấu hình `library_root`, rồi mới xóa nơi cũ. Lỗi giữa chừng thì xóa phần đã sao chép và thư viện vẫn ở nơi cũ.
- Bị từ chối khi đang có job chạy dở. Job tạo trong lúc chuyển được xếp hàng và chạy sau khi chuyển xong.

### Luồng job
`QUEUED` → `DOWNLOADING` → `PREPARING_SUBS` → `TRANSLATING` → `AWAITING_REVIEW` (dừng chờ người dùng duyệt) → `SYNTHESIZING` → `MIXING` → `PUBLISHING` → `DONE`.
- Thiếu phụ đề thì job dừng ở `AWAITING_SUBTITLE` chờ upload file hoặc chuyển sang Whisper.
- Job đang chờ không chiếm worker; worker xử lý job kế tiếp.
- Lỗi: `FAILED` (chạy lại được, stage đã xong được bỏ qua nhờ file đánh dấu trong `work/<job_id>/`).
- Phụ đề gốc đã là tiếng Việt thì bỏ qua bước dịch.
- Một worker thread xử lý lần lượt; job dang dở được tiếp tục khi module được dùng lần đầu sau khi khởi động lại server.

### Code cũ được gọi lại (không sửa)
- `modules/video_dubbing/sub_handler.load_subtitles`: đọc SRT/VTT.
- `modules/dynamic_subtitle.extract_temp_audio`, `transcribe_audio_word_level`: tách audio và bóc băng bằng faster-whisper.
- `modules/video_dubbing/media_mixer.mix_audio_to_video_advanced`: trộn giọng lồng tiếng, giữ tiếng gốc làm nền, nhúng phụ đề mềm (`hard_sub=False`).
- `modules/video_dubbing/tts_generator.sanitize_vietnamese_text`: làm sạch câu trước khi đọc.

### Lồng tiếng
- Đầu vào là cột `vi_text` của bảng `cues` (bản đã duyệt); câu để trống không được đọc.
- Mỗi câu được đọc ở tốc độ thường; nếu dài hơn khung thời gian quá 5% thì đọc lại nhanh hơn, tối đa +50%. Khung thời gian tính tới lúc câu kế tiếp bắt đầu.
- Mỗi câu thử tối đa 3 lần; câu đã đọc xong được ghi vào `work/<job_id>/tts/tts.partial.json` để chạy lại không phải đọc lại.
- Thư viện: `GET /api/bilibili/library/{id}/stream?kind=source` và `/download?kind=source` trả video gốc khi người dùng chọn giữ lại.
