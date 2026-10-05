---
tags: [quy-ước]
cập_nhật: 2026-10-05
---
# Thêm module mới

Mục tiêu: dự án lớn thêm mà phần cũ không lung lay. Mỗi tính năng mới là một module tự chứa. Mẫu để nhìn theo: [[Bilibili Dubbing]].

## Nguyên tắc
1. Toàn bộ code nằm trong `modules/<tên_module>/`.
2. Ngoài module chỉ được đụng đúng các file sau, và chỉ thêm, không sửa cái có sẵn:
   - `app.py`: 2 dòng `import` và `include_router` (giữ CRLF)
   - `requirements.txt`: thư viện đã được duyệt
   - `.gitignore`: thư mục dữ liệu của module
3. Dữ liệu ở `data/<tên_module>/`.
4. Không import ngược: module cũ không được biết module mới tồn tại.
5. Dùng lại code cũ bằng cách gọi qua adapter, không sửa, không chép.
6. Xóa thư mục module và 2 dòng trong `app.py` thì dự án phải chạy lại như trước khi có module.

## Các bước
1. **Làm rõ yêu cầu**: người dùng làm gì, đầu vào, đầu ra, ngoài phạm vi là gì. Hỏi cho tới khi hết mơ hồ.
2. **Bản thiết kế** trình người dùng duyệt trước khi viết code: các lớp, luồng dữ liệu, endpoint, schema, thư viện cần thêm, code cũ sẽ gọi lại, chia giai đoạn.
3. **Chia giai đoạn**: mỗi giai đoạn chạy được và người dùng thử được trên máy thật trước khi sang giai đoạn sau.
4. **Dựng khung** theo cây thư mục trong [[Quy ước code#Tách tầng trong một module]].
5. **Viết kèm test** từng giai đoạn.
6. **Viết `README.md` của module**: cách chạy, luồng sử dụng, cấu trúc, code cũ được gọi, dữ liệu, giới hạn đã biết.
7. **Cập nhật vault**: tạo ghi chú trong `Modules/` theo [[Mẫu module]]; thêm vào [[Trạng thái]], [[API]], [[Kiến trúc]], [[Change log]], bảng module ở [[00 - Trang chủ]].
8. Module vào bảng Stable theo [[Định nghĩa xong#Chuyển sang Stable]].

## Kiểm tra độc lập trước khi báo xong
- [ ] `git diff --stat` chỉ có file trong `modules/<tên_module>/`, các file được phép ở trên, và `vault/`.
- [ ] Không file nào của module Stable bị đổi.
- [ ] Endpoint mới không trùng đường dẫn nào trong [[API]].
- [ ] Tạm bỏ 2 dòng `include_router`: các chức năng cũ vẫn chạy.
- [ ] Module nạp lỗi (thiếu thư viện) thì trang của module báo lỗi rõ ràng, các chức năng khác vẫn chạy.
