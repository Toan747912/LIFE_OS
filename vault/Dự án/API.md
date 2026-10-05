---
tags: [dự-án]
cập_nhật: 2026-10-06
---
# API

Tên đường dẫn, phương thức, tên tham số và hình dạng JSON dưới đây là **hợp đồng cấm đổi**. Thêm endpoint mới thì thêm vào trang này.

## `app.py` — FastAPI
Tham số gửi dạng form (`multipart/form-data`), không phải JSON.

| Phương thức, đường dẫn | Tham số | Trả về |
| --- | --- | --- |
| `GET /` | | HTML `templates/index.html` |
| `POST /start-dubbing` | `video_name`, `subtitle_name`, `orig_vol`=0.15, `dub_vol`=1.0, `hard_sub`=false, `enable_dynamic_sub`=false | `{"status": "started"}`; 400 nếu thiếu file |
| `GET /status` | | `{"progress": int, "message": str, "is_done": bool}` |
| `GET /download-video` | | file `output_final.mp4`, hoặc `{"error": "Video chưa được tạo"}` |
| `GET /api/files` | | `{"files": [{"name": str, "size_mb": float}]}` |
| `POST /api/files/upload` | `file` | `{"success": true, "filename": str, "message": str}` |
| `PUT /api/files/rename` | `old_name`, `new_name` | `{"success": bool, "message": str}`; 400 khi lỗi |
| `DELETE /api/files/{filename}` | | `{"success": bool, "message": str}`; 404 khi không có |
| `POST /api/translate` | `text` | `{"translation": str}`, lỗi thì thêm `"error"` |
| `POST /api/tts` | `text` | `audio/mpeg`; 503 nếu thiếu `edge-tts`; 400 nếu rỗng; 500 nếu sinh giọng lỗi |
| `GET /api/tts` | query `text` | giống `POST /api/tts` (thêm 2026-10-06 cho extension) |

Khi lồng tiếng lỗi, `/status` trả `message` bắt đầu bằng `"Lỗi: "` và `is_done` vẫn là `false`.

## `vi_sub_server.py` — Flask
| Phương thức, đường dẫn | Tham số | Trả về |
| --- | --- | --- |
| `POST /api/translate` | form `text` | `{"translation": str}` |
| `GET` hoặc `POST /api/tts` | `text` (query hoặc form) | `audio/mpeg`; lỗi `{"error": str}` kèm 400 hoặc 500 |
| `GET /health` | | `{"status": "ok", "gtts": bool, "argos": bool, "trans_cached": int, "tts_cached": int}` |

Hai server trùng đường dẫn `/api/translate` và `/api/tts` nhưng khác engine: [[Phát hiện - liên hệ ẩn]].

## Bilibili Dubbing — `/api/bilibili/…`
Nguồn: `modules/bilibili_dubbing/api/router.py`. Lỗi trả theo cây `BilibiliError` (mỗi lỗi có `code` và mã HTTP).

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

Thư viện còn nhận `?kind=source` ở `/stream` và `/download` để trả video gốc khi người dùng chọn giữ lại.

## Ai gọi endpoint nào
| Bên gọi | Endpoint |
| --- | --- |
| `templates/index.html` | `/api/files`, `/api/files/upload`, `/api/files/rename`, `/api/files/{filename}`, `/start-dubbing`, `/status`, `/download-video` |
| `yt-subtitle-extension/core.js` | `POST /api/translate`, `GET /api/tts?text=` |
| `modules/bilibili_dubbing/web/` | `/api/bilibili/…` |
