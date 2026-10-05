---
tags: [vấn-đề]
cập_nhật: 2026-10-06
---
# Vấn đề đã biết

Thêm dòng mới ở cuối, không đánh lại số. Sửa xong thì đổi cột trạng thái, không xóa dòng. Số 11 trở đi phát hiện khi đọc code ngày 2026-10-05, chưa chạy thử để tái hiện.

| # | Vấn đề | Thuộc | Trạng thái |
| --- | --- | --- | --- |
| 1 | Whisper báo `mkl_malloc: failed to allocate memory` khi nạp model | [[Bilibili Dubbing]], [[Dynamic Subtitle]] | Đã có tự lùi model; phát triển tạm dừng |
| 2 | Whisper không báo tiến độ, không hủy giữa chừng được | [[Bilibili Dubbing]] | Giới hạn |
| 3 | Dịch bằng Google chưa thử với dữ liệu thật | [[Bilibili Dubbing]] | Chờ thử |
| 4 | Lỗi FFmpeg khi trộn chỉ hiện ở cửa sổ server (`subprocess.run(check=True)` không thu stderr) | [[Video Dubbing]] | Giới hạn; sửa cần đụng Stable |
| 5 | Job dang dở sau khi khởi động lại chỉ chạy tiếp khi mở `/bilibili` | [[Bilibili Dubbing]] | Giới hạn |
| 6 | Câu dài hơn khung thời gian: đọc nhanh tối đa +50%, vẫn có thể lấn câu sau | [[Bilibili Dubbing]], [[Video Dubbing]] | Rút câu ở bước duyệt |
| 7 | Video HEVC/AV1 nhiều trình duyệt không phát | [[Bilibili Dubbing]] | Bước quét mặc định chọn AVC |
| 8 | `app.py` gọi `TemplateResponse("index.html", {"request": request})` kiểu cũ, sẽ lỗi nếu nâng Starlette | [[Backend FastAPI]] | **Đã sửa 2026-10-06**: tự nhận kiểu gọi theo phiên bản Starlette |
| 9 | Máy chặn `pip.exe`, `uvicorn.exe` | môi trường | Dùng `python -m …` |
| 10 | Hai server cùng cổng 8000, trùng đường dẫn API | [[Backend FastAPI]], [[Backend Flask]] | Roadmap gộp backend |
| 11 | CORS của `app.py` cho mọi nguồn (`allow_origins=["*"]`) với cả `DELETE`: trang web bất kỳ đang mở trong trình duyệt có thể gọi API cục bộ, kể cả xóa file và các endpoint `/api/bilibili/…` | [[Backend FastAPI]] | **Rủi ro đã chấp nhận** (QĐ-12): extension gọi từ trang web bất kỳ nên không siết theo nguồn được |
| 12 | `/api/tts` của `app.py` tạo file mp3 tạm bằng `delete=False` và không xóa (`background=BackgroundTasks()` rỗng) → file tạm tích dần | [[Backend FastAPI]] | **Đã sửa 2026-10-06**: xóa sau khi gửi, và xóa khi sinh giọng lỗi |
| 13 | `/start-dubbing` ghép `video_name`, `subtitle_name` vào `UPLOAD_DIR` mà không lọc `basename` (các hàm của `file_manager` thì có lọc) | [[Backend FastAPI]] | **Đã sửa 2026-10-06** |
| 14 | `status_state` là biến toàn cục: chỉ theo dõi được một lần lồng tiếng; bấm lần hai khi đang chạy sẽ ghi đè tiến độ và cùng ghi vào `output_final.mp4` | [[Backend FastAPI]] | Giới hạn thiết kế cũ |
| 15 | `sites/phim.js`: `SUBTITLE_SELECTOR` đang `null` kèm TODO → adapter cho `phim.nguonc.com` chưa hoàn thiện | [[Chrome Extension]] | Chưa làm |
| 16 | `generate_tts_for_subtitles` nuốt lỗi từng câu (chỉ `print`), để lại file mp3 0 byte; câu lỗi bị bỏ khỏi bản lồng tiếng mà không báo | [[Video Dubbing]] | Giới hạn; Stable |
| 17 | Extension phát giọng bằng `GET /api/tts?text=`; `app.py` chỉ nhận `POST` → chạy với `app.py` thì extension dịch được nhưng không có giọng, và không lùi về Web Speech | [[Chrome Extension]], [[Backend FastAPI]] | **Đã sửa 2026-10-06**: thêm `GET /api/tts` vào `app.py`. Chưa thử với extension thật |
| 18 | `requirements.txt` thiếu nhiều thư viện đang dùng | môi trường | Roadmap; xem [[Môi trường và chạy]] |
