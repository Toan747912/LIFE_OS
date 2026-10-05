---
tags: [quy-ước]
cập_nhật: 2026-10-05
---
# Định nghĩa "xong"

## Các mức trạng thái
| Trạng thái | Nghĩa |
| --- | --- |
| Dự kiến | có trong roadmap, chưa bắt đầu |
| Đang làm | đang viết, chưa đủ để thử |
| Chờ xác nhận | AI đã xong phần mình, chờ người dùng thử thật |
| Stable | người dùng đã xác nhận, từ giờ cấm sửa |
| Tạm dừng | dừng theo yêu cầu, ghi rõ lý do |
| Mã chết | còn trong repo nhưng không được dùng, chờ quyết định xóa |

## Một nhiệm vụ là "xong" (AI được báo xong) khi
- [ ] Làm đúng và đủ yêu cầu, không làm thêm thứ không được yêu cầu.
- [ ] Chỉ đụng file trong phạm vi đã nêu.
- [ ] Test của module qua hết, có test cho phần mới.
- [ ] Các endpoint cũ còn nguyên tên và hình dạng JSON.
- [ ] Không thêm thư viện chưa được duyệt.
- [ ] Theo [[Quy ước code]].
- [ ] Lỗi được báo bằng thông báo tiếng Việt, người dùng biết làm gì tiếp.
- [ ] Vault đã cập nhật theo bước 4 của [[Quy trình làm việc]].
- [ ] Báo cáo nêu rõ phần **chưa kiểm chứng** và người dùng cần thử gì.

Thiếu một mục thì trạng thái là "Đang làm", không phải "xong".

## Chuyển sang "Chờ xác nhận"
Mọi mục ở trên đạt, và phần chưa kiểm chứng đã được ghi thành việc cụ thể trong [[Việc cần làm]].

## Chuyển sang Stable
Chỉ **người dùng** quyết định. AI không tự chuyển. Điều kiện:
- [ ] Người dùng đã chạy thật trên máy mình các luồng chính và xác nhận.
- [ ] Mọi mục "chưa kiểm chứng" đã được thử, hoặc được ghi thành giới hạn trong [[Vấn đề đã biết]].
- [ ] Có `README.md` của module và ghi chú trong `Modules/`.
- [ ] Đã commit.
- [ ] Ghi chú module có mục "Cấm đụng" nêu rõ điểm nào không được sửa.

Sau khi vào Stable: thêm vào bảng ở [[Trạng thái]] và [[Phạm vi và quyền]], ghi một dòng vào [[Change log]].

## Sửa một module Stable
Chỉ khi người dùng yêu cầu trực tiếp. Khi đó: nêu phạm vi sửa, thêm test tái hiện trước, sửa tối thiểu, ghi vào [[Change log]] và [[Nhật ký quyết định]].
