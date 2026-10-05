# Bilibili Dubbing

Module của LIFE_OS: dán link Bilibili, quét để chọn chất lượng và phụ đề, tải video, dịch và duyệt phụ đề,
lồng tiếng Việt, rồi xem, tải xuống và quản lý trong thư viện trên web.

Module độc lập với các chức năng khác. Toàn bộ code nằm trong thư mục này; `app.py` chỉ có 2 dòng
`include_router`. Dữ liệu nằm ở `data/bilibili_dubbing/` (đã gitignore).

## Chạy

```powershell
cd <thư mục LIFE_OS>
python -m pip install -r requirements.txt
python -m uvicorn app:app --reload --port 8000
```

Mở `http://localhost:8000/bilibili`. Dùng `python -m pip` và `python -m uvicorn` vì trên một số máy Windows
file `pip.exe` và `uvicorn.exe` bị chính sách Application Control chặn.

Cần có `ffmpeg` và `ffprobe` trong PATH. Trang web báo ngay ở đầu trang nếu thiếu `yt-dlp`, `ffmpeg`,
`edge-tts` hoặc `deep-translator`.

## Luồng sử dụng

1. **Tạo mới:** dán một hoặc nhiều link (mỗi dòng một link), bấm Quét. Module chỉ đọc thông tin, chưa tải gì.
2. Chọn tập, chất lượng, nguồn phụ đề, giọng đọc, rồi bấm Bắt đầu. Mỗi tập là một job.
3. **Hàng đợi:** job tải video, lấy phụ đề gốc, dịch sang tiếng Việt, rồi dừng ở "Chờ bạn duyệt".
4. **Duyệt phụ đề:** xem lại và sửa bản tiếng Việt (bấm mốc thời gian để nhảy tới cảnh đó), rồi Duyệt.
5. Job sinh giọng đọc, trộn vào video (tiếng gốc giữ nhỏ làm nền, phụ đề mềm) và đưa vào **Thư viện**.

Trạng thái của job:
`QUEUED` → `DOWNLOADING` → `PREPARING_SUBS` → `TRANSLATING` → `AWAITING_REVIEW` → `SYNTHESIZING` → `MIXING`
→ `PUBLISHING` → `DONE`. Thiếu phụ đề thì dừng ở `AWAITING_SUBTITLE` chờ upload file `.srt`/`.vtt`.

Job lỗi (`FAILED`) bấm Chạy lại được: bước nào đã xong thì không làm lại (không tải lại, không dịch lại,
không đọc lại câu đã đọc).

## Cookie đăng nhập

Tab Cài đặt. Cần cho nội dung yêu cầu đăng nhập, chất lượng trên 480p và phụ đề AI. Cookie chỉ lưu ở
`data/bilibili_dubbing/cookies.txt`, không bao giờ được trả ngược ra trình duyệt, và module chỉ giữ cookie
của Bilibili. Nút "Kiểm tra đăng nhập" hỏi trực tiếp máy chủ bilibili.com; với bilibili.tv thì quét thử
một link cần đăng nhập để biết.

Module không vượt khóa vùng, VIP hay DRM: nội dung tài khoản không xem được sẽ báo rõ ở bước quét.

## Cấu trúc

| Thư mục | Vai trò |
| --- | --- |
| `domain/` | Mô hình dữ liệu, enum trạng thái, cây exception `BilibiliError` |
| `sources/` | `BaseVideoSource` (ABC), `BilibiliSource` (yt-dlp), `ScanService` |
| `subtitles/` | `SubtitleDocument`, `SubtitleProvider` (ABC) + 3 nguồn, `Translator` (ABC) + Google |
| `dubbing/` | `TtsSynthesizer` (edge-tts), `DubMixer` (adapter của `media_mixer` cũ) |
| `pipeline/` | `PipelineStage` (ABC) + 7 stage, `DubbingPipeline`, `JobRunner`, `JobService`, `ReviewService` |
| `storage/` | SQLite, repository, `StorageManager`, `LibraryService`, `StorageService`, `LibraryMover`, cookie |
| `media/` | `FfmpegTools` (ffprobe, đổi phụ đề sang WebVTT) |
| `api/` | `router.py` (mọi endpoint), `schemas.py`, `container.py` (nối các đối tượng), `streaming.py` |
| `web/` | Giao diện một trang (HTML + JavaScript thuần) |
| `tests/` | Unit test và test trọn luồng |

Bốn lớp trừu tượng là điểm mở rộng: thêm nền tảng video, nguồn phụ đề, dịch vụ dịch hoặc một bước xử lý
mới bằng cách thêm lớp con, không sửa code đang chạy. Danh sách endpoint đầy đủ nằm ở `ARCHITECTURE.md`.

## Code cũ được gọi lại, không sửa

- `modules/video_dubbing/sub_handler.load_subtitles`: đọc SRT/VTT.
- `modules/video_dubbing/media_mixer.mix_audio_to_video_advanced`: trộn giọng lồng tiếng và nhúng phụ đề.
- `modules/video_dubbing/tts_generator.sanitize_vietnamese_text`: làm sạch câu trước khi đọc.
- `modules/dynamic_subtitle.extract_temp_audio`, `transcribe_audio_word_level`: bóc băng bằng faster-whisper.

Không dùng `tts_generator.generate_tts_for_subtitles` vì hàm đó tự dịch lại từng câu, sẽ làm hỏng bản dịch
đã duyệt.

## Dữ liệu và an toàn

```text
data/bilibili_dubbing/
├── bilibili.db      # SQLite: job, câu phụ đề, thư viện, series, tag, cài đặt
├── cookies.txt      # chỉ có khi đã nhập cookie
├── work/<job_id>/   # file tạm của job, tự dọn khi job xong
└── library/<id>/    # thư viện (đổi được sang thư mục khác ở tab Cài đặt)
```

- Module chỉ ghi và xóa trong `work/` và thư mục thư viện; mọi đường dẫn đều được kiểm tra lại.
- Thư viện không bao giờ được đặt trong `core/`, `modules/`, `templates/`, `yt-subtitle-extension/`.
- Xóa video là xóa hẳn khỏi đĩa, không vào Thùng rác.
- Lỗi khi nạp module không làm sập app: `/bilibili` trả 503 kèm lý do, các chức năng khác vẫn chạy.

## Test

```powershell
python -m unittest discover -s modules/bilibili_dubbing/tests -t .
```

Test không cần mạng: nguồn video, dịch, bóc băng và giọng đọc được thay bằng bản giả trong
`tests/fakes.py`. Bộ trộn cũ thì chạy thật, nên cần `ffmpeg`. Thiếu `httpx` hoặc `ffmpeg` thì các test
trọn luồng tự bỏ qua.

## Giới hạn đã biết

- **Whisper bóc băng đang tạm dừng phát triển.** Chức năng vẫn chạy và được gắn nhãn thử nghiệm. Nó cần
  nhiều RAM, không báo tiến độ và không hủy giữa chừng được. Thiếu RAM thì module tự lùi xuống model nhẹ
  hơn. Nên ưu tiên phụ đề có sẵn hoặc file tự upload.
- **Dịch bằng Google chưa được thử với dữ liệu thật** trong quá trình phát triển (video đã thử có sẵn phụ
  đề tiếng Việt nên bước dịch bị bỏ qua).
- **Lỗi của FFmpeg khi trộn** chỉ hiện chi tiết trong cửa sổ chạy server, vì hàm trộn cũ không thu lại.
- **Job dang dở sau khi khởi động lại server** chỉ chạy tiếp khi trang `/bilibili` được mở lần đầu.
- **Câu dài hơn khung thời gian** được đọc nhanh hơn, tối đa +50%; vẫn không kịp thì giọng lấn sang câu
  sau. Cách xử lý là rút ngắn câu ở bước duyệt.
- **Video HEVC/AV1** tải được nhưng nhiều trình duyệt không phát; bước quét mặc định chọn AVC.
- Chỉ nên dùng cho video bạn có quyền tải và xem cá nhân.
