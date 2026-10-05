---
tags: [dự-án]
cập_nhật: 2026-10-06
---
# Trạng thái

Nghĩa của từng mức: [[Định nghĩa xong#Các mức trạng thái]]. Chỉ người dùng chuyển một hạng mục sang Stable.

## Stable — cấm sửa
Đã kiểm thử và chạy ổn định. Không sửa logic, không refactor, trừ khi người dùng yêu cầu trực tiếp.

| Module / File | Chức năng | Điểm cấm | Ghi chú |
| --- | --- | --- | --- |
| `modules/video_dubbing/service.py` | Điều phối pipeline lồng tiếng | logic `run_dubbing_pipeline` | [[Video Dubbing]] |
| `modules/video_dubbing/tts_generator.py` | Dịch và sinh giọng Edge-TTS, khớp tốc độ | tham số khớp tốc độ | [[Video Dubbing]] |
| `modules/video_dubbing/media_mixer.py` | Ghép audio và video bằng FFmpeg | các lệnh FFmpeg | [[Video Dubbing]] |
| `modules/video_dubbing/sub_handler.py` | Đọc `.vtt`, `.srt` | | [[Video Dubbing]] |
| `modules/dynamic_subtitle.py` | Whisper bóc băng, phụ đề ASS | template hiệu ứng ASS | [[Dynamic Subtitle]] |
| `modules/file_manager.py` | CRUD file trong `core/input/` | `UPLOAD_DIR` | [[File Manager]] |
| `yt-subtitle-extension/` | Extension dịch và đọc phụ đề | logic inject DOM, giao diện | [[Chrome Extension]] |

Ngoài ra, mọi endpoint hiện có và JSON trả về của chúng là cấm đổi: [[API]].

## Chờ xác nhận
| Hạng mục | Tình trạng | Còn thiếu để vào Stable |
| --- | --- | --- |
| [[Bilibili Dubbing]] | Xong 6 giai đoạn. Giai đoạn 1 đến 5 người dùng đã xác nhận trên máy thật. Giai đoạn 6 chưa được thử thật | Xem [[Việc cần làm#Chờ bạn làm]] |

## Đang dùng, chưa xếp loại
| Hạng mục | Ghi chú |
| --- | --- |
| [[Backend FastAPI]] (`app.py`) | Chứa endpoint cấm đổi; chưa được ghi là Stable. Sửa phải được giao rõ |
| [[Backend Flask]] (`vi_sub_server.py`) | Dự kiến gộp vào FastAPI |
| `templates/index.html` | Giao diện trang chủ; coi như Stable (QĐ-04) |
| `main.py`, `modules/video_dubbing/main.py` | Menu dòng lệnh |

## Tạm dừng
| Hạng mục | Lý do |
| --- | --- |
| Whisper bóc băng trong [[Bilibili Dubbing]] | Người dùng yêu cầu dừng phát triển sau lỗi thiếu RAM. Chức năng vẫn chạy, gắn nhãn thử nghiệm |

## Dự kiến
Xem [[Việc cần làm#Roadmap]].

## Mã chết (chờ quyết định xóa)
Người dùng đã cho xóa ngày 2026-10-06 (QĐ-14); chờ xóa tay, xem [[Việc cần làm]]. Chi tiết và bằng chứng ở [[Phát hiện - liên hệ ẩn#Mã chết và file thừa]].
- `yt-subtitle-extension/content.js`, `content.js.bak`, `content.js.bak2`
- `fix_vi_sub.ps1`, `fix_vi_sub_v2.ps1`
- `modules/video_dubbing/ui_controller.py`
- Thư mục `Claude outputs/`
