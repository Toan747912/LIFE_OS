---
tags: [ai, meta]
cập_nhật: 2026-10-05
---
# Bắt đầu ở đây

Trang này dành cho mọi AI (và người) trước khi đụng vào LIFE_OS. Đọc hết trang này, rồi đọc theo bảng "Đọc gì cho việc gì".

## Luật cứng
Vi phạm bất kỳ điều nào là sai, kể cả khi kết quả chạy được.

1. **Chỉ sửa file người dùng đã giao trong phiên này.** Mọi file khác là cấm đụng: không refactor, không "dọn dẹp", không sửa giúp.
2. **Không sửa module Stable.** Danh sách ở [[Trạng thái]]. Được gọi lại nguyên trạng, không được đổi.
3. **Không đổi tên endpoint, không đổi hình dạng JSON trả về.** Extension và giao diện web đang gọi chúng. Hợp đồng ở [[API]].
4. **Không thêm, bớt, đổi phiên bản thư viện** khi chưa được đồng ý.
5. **Thấy lỗi ngoài phạm vi thì báo, không sửa.** Ghi vào [[Vấn đề đã biết]] và hỏi người dùng.
6. **Không báo "xong" khi chưa kiểm chứng.** Nói rõ cái gì đã chạy thử, cái gì chưa. Tiêu chí ở [[Định nghĩa xong]].
7. **Không commit, không push khi chưa được yêu cầu.** Trước khi commit phải `git status` và `git diff`.
8. **Kết thúc phiên phải cập nhật vault**: [[Trạng thái]], [[Change log]], [[Việc cần làm]], nhật ký phiên. Xem [[Quy trình làm việc]].

Không chắc một việc có nằm trong phạm vi không thì hỏi. Hỏi luôn rẻ hơn sửa nhầm.

## Đọc gì cho việc gì
| Việc được giao | Đọc bắt buộc |
| --- | --- |
| Bất kỳ việc gì | Trang này, [[Trạng thái]], [[Phạm vi và quyền]], nhật ký phiên gần nhất trong `Nhật ký/` |
| Sửa hoặc thêm trong một module | Ghi chú module đó trong `Modules/`, [[Quy ước code]], [[Vấn đề đã biết]] |
| Thêm module mới | [[Thêm module mới]], [[Kiến trúc]], [[Bilibili Dubbing]] (module mẫu) |
| Đụng tới endpoint | [[API]], [[Phát hiện - liên hệ ẩn]] |
| Gộp backend, dọn file, đổi cấu hình | [[Phát hiện - liên hệ ẩn]], [[Nhật ký quyết định]] |
| Commit | [[Quy ước git]] |
| Cài đặt, chạy, test | [[Môi trường và chạy]] |

## Dự án trong 6 dòng
- Ứng dụng cá nhân chạy trên Windows, Python 3.11, một người dùng, chạy cục bộ ở cổng 8000.
- [[Backend FastAPI]] (`app.py`) là server chính; [[Backend Flask]] (`vi_sub_server.py`) là server cũ cho extension, cùng cổng.
- [[Video Dubbing]], [[Dynamic Subtitle]], [[File Manager]], [[Chrome Extension]] là Stable, cấm sửa.
- [[Bilibili Dubbing]] là module mới nhất và là **mẫu chuẩn** cho mọi module sau này.
- Server phải chạy từ thư mục gốc dự án, vì code cũ dùng đường dẫn tương đối.
- Trang chủ vault: [[00 - Trang chủ]].
