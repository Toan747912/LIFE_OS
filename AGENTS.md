# LIFE_OS — Hướng dẫn cho AI

Mọi luật, trạng thái, kiến trúc và quy ước của dự án nằm trong thư mục `vault/`. File này chỉ là cửa vào.

## Việc đầu tiên, bắt buộc
Đọc `vault/AI/Bắt đầu ở đây.md` trước khi tạo, sửa hay xóa bất cứ thứ gì. Trang đó cho biết phải đọc tiếp gì cho từng loại việc.

## Luật cứng
1. **Chỉ sửa file người dùng đã giao trong phiên này.** Mọi file khác là cấm đụng: không refactor, không "dọn dẹp", không sửa giúp.
2. **Không sửa module Stable**: `modules/video_dubbing/`, `modules/dynamic_subtitle.py`, `modules/file_manager.py`, `yt-subtitle-extension/`, `templates/index.html`. Được gọi lại nguyên trạng, không được đổi.
3. **Không đổi tên endpoint, không đổi hình dạng JSON trả về.**
4. **Không thêm, bớt, đổi phiên bản thư viện** khi chưa được đồng ý.
5. **Thấy lỗi ngoài phạm vi thì báo, không sửa.**
6. **Không báo "xong" khi chưa kiểm chứng.** Nói rõ cái gì đã chạy thử, cái gì chưa.
7. **Không commit, không push khi chưa được yêu cầu.** Trước khi commit phải `git status` và `git diff`.
8. **Kết thúc nhiệm vụ phải cập nhật vault**: Trạng thái, Change log, Việc cần làm, nhật ký phiên.

Không chắc một việc có nằm trong phạm vi không thì hỏi người dùng.

## Bản đồ vault
| Cần biết | Đọc |
| --- | --- |
| Được sửa gì, cấm sửa gì | `vault/AI/Phạm vi và quyền.md` |
| Trước, trong, sau nhiệm vụ làm gì | `vault/AI/Quy trình làm việc.md` |
| Module nào Stable, cái gì đang làm | `vault/Dự án/Trạng thái.md` |
| Endpoint và hợp đồng JSON | `vault/Dự án/API.md` |
| Cấu trúc, luồng dữ liệu | `vault/Dự án/Kiến trúc.md` |
| Cài đặt, chạy, test | `vault/Dự án/Môi trường và chạy.md` |
| Cách viết code | `vault/Quy ước/Quy ước code.md` |
| Thêm module mới | `vault/Quy ước/Thêm module mới.md` |
| Commit | `vault/Quy ước/Quy ước git.md` |
| Thế nào là xong | `vault/Quy ước/Định nghĩa xong.md` |
| Chi tiết từng module | `vault/Modules/` |
| Lỗi và giới hạn đã biết | `vault/Vấn đề đã biết.md` |
| Vì sao làm thế này | `vault/Nhật ký quyết định.md` |

## Lệnh hay dùng
```powershell
python -m uvicorn app:app --reload --port 8000
python -m unittest discover -s modules/bilibili_dubbing/tests -t .
```
Luôn chạy từ thư mục gốc dự án. Dùng `python -m pip`, không dùng `pip.exe`.

<!-- Phần "Luật cứng" chép từ vault/AI/Bắt đầu ở đây.md. Sửa ở đó trước rồi đồng bộ sang đây. -->
