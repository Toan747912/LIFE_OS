---
tags: [ai]
cập_nhật: 2026-10-05
---
# Phạm vi và quyền

## Ba vùng
| Vùng | Gồm | AI được làm |
| --- | --- | --- |
| **Được giao** | File, module người dùng nêu tên trong phiên này | Tạo, sửa, xóa trong đúng phạm vi đó |
| **Cấm sửa (Stable)** | Các module trong bảng Stable của [[Trạng thái]] | Chỉ đọc và gọi lại nguyên trạng |
| **Chưa được giao** | Mọi thứ còn lại | Chỉ đọc. Muốn sửa phải hỏi trước |

Vault (`vault/`) là ngoại lệ có điều kiện: AI **phải** cập nhật các trang trạng thái và nhật ký sau mỗi nhiệm vụ (xem [[Quy trình làm việc]]), nhưng **không tự sửa** các trang luật: [[Bắt đầu ở đây]], trang này, [[Quy ước code]], [[Quy ước git]], [[Định nghĩa xong]]. Muốn đổi luật thì đề xuất với người dùng.

## Luật cấm đụng
1. Không tự refactor code đang chạy tốt. Refactor không được yêu cầu gây hỏng tính năng cũ.
2. Không tự xóa hay đổi tên endpoint: `/start-dubbing`, `/status`, `/download-video`, `/api/files…`, `/api/translate`, `/api/tts`, và toàn bộ `/api/bilibili/…`.
3. Không đổi cấu trúc JSON trả về.
4. Giữ nguyên logic, comment và cấu hình của các phần không liên quan tới nhiệm vụ.
5. Không tự thêm, xóa thư viện hay đổi phiên bản.
6. Không đổi kiểu xuống dòng của file có sẵn (xem [[Quy ước code#Định dạng file]]).

## Điểm cấm cụ thể trong module Stable
| File | Cấm |
| --- | --- |
| `modules/video_dubbing/service.py` | sửa logic `run_dubbing_pipeline` |
| `modules/video_dubbing/tts_generator.py` | đổi tham số khớp tốc độ (ngưỡng 5%, tối đa +50%) |
| `modules/video_dubbing/media_mixer.py` | sửa các lệnh FFmpeg |
| `modules/dynamic_subtitle.py` | sửa template hiệu ứng ASS |
| `modules/file_manager.py` | đổi `UPLOAD_DIR` |
| `yt-subtitle-extension/` | đổi logic inject DOM và giao diện |
| `templates/index.html` | thêm link hay sửa giao diện khi chưa được giao |

## Khi nào phải dừng lại hỏi
- Nhiệm vụ không làm được nếu không sửa một file ngoài phạm vi.
- Cần thêm thư viện.
- Có hai cách hiểu yêu cầu dẫn tới hai kết quả khác nhau.
- Thao tác không hoàn tác được: xóa file, xóa dữ liệu, đổi schema, ghi đè file người dùng.
- Phát hiện lỗi ở vùng cấm hoặc vùng chưa được giao.

Cách hỏi: nêu vấn đề, nêu các phương án kèm hệ quả, đề xuất một phương án. Không hỏi câu mà đọc vault là trả lời được.

## Những thứ không bao giờ làm
- Vượt khóa vùng, VIP, DRM của nền tảng video.
- Đưa cookie, khóa, dữ liệu trong `data/` vào git, log hay câu trả lời.
- Ghi hoặc xóa ngoài thư mục dữ liệu của chính module đang làm.
