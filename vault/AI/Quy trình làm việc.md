---
tags: [ai]
cập_nhật: 2026-10-05
---
# Quy trình làm việc

Mỗi nhiệm vụ đi qua 4 bước. Bỏ bước nào cũng coi là chưa xong.

## 1. Trước khi làm
- [ ] Đọc [[Bắt đầu ở đây]], [[Trạng thái]], nhật ký phiên gần nhất.
- [ ] Đọc ghi chú module liên quan và [[Vấn đề đã biết]].
- [ ] Viết ra **phạm vi**: sẽ tạo và sửa những file nào. Mọi file ngoài danh sách là cấm đụng.
- [ ] Yêu cầu còn mơ hồ thì hỏi lại trước. Việc lớn (module mới, đổi kiến trúc) thì trình bản thiết kế và chờ duyệt, chia giai đoạn, mỗi giai đoạn người dùng thử được.
- [ ] Cần thư viện mới hoặc cần đụng file ngoài phạm vi thì xin phép trước.

## 2. Trong lúc làm
- Đọc code thật trước khi gọi hoặc sửa. Không đoán chữ ký hàm, không đoán tên endpoint.
- Thay đổi nhỏ nhất đủ để đạt yêu cầu. Không tiện tay sửa thứ khác.
- Theo [[Quy ước code]]. Module mới theo [[Thêm module mới]].
- Mỗi quyết định có phương án bị loại thì ghi vào [[Nhật ký quyết định]] ngay.
- Thấy lỗi ngoài phạm vi: ghi vào [[Vấn đề đã biết]], báo người dùng, không sửa.

## 3. Trước khi báo xong
- [ ] Chạy test của module (lệnh ở [[Môi trường và chạy]]). Ghi rõ số test qua.
- [ ] Tự đối chiếu danh sách file đã đổi với phạm vi ở bước 1. Lệch thì hoàn lại hoặc xin phép.
- [ ] Kiểm tra không làm hỏng endpoint cũ (xem [[API]]).
- [ ] Đạt mọi mục trong [[Định nghĩa xong]].
- [ ] Phân biệt rõ trong báo cáo: **đã kiểm chứng** (chạy thật, test qua) với **chưa kiểm chứng** (cần người dùng thử trên máy, cần mạng thật).

## 4. Sau khi xong (cập nhật vault)
- [ ] [[Trạng thái]]: đổi trạng thái hạng mục.
- [ ] [[Change log]]: thêm một dòng, ghi rõ file nào ngoài module bị đụng.
- [ ] [[Việc cần làm]]: gạch việc xong, thêm việc treo mới.
- [ ] Ghi chú module trong `Modules/`: cập nhật nếu đổi hàm công khai, quan hệ gọi, dữ liệu.
- [ ] [[API]]: cập nhật nếu thêm endpoint.
- [ ] `Nhật ký/YYYY-MM-DD.md`: thêm mục theo [[Mẫu nhật ký]].

## Mẫu báo cáo cuối nhiệm vụ
```text
Kết quả: <một câu>
File đã đổi: <danh sách>   Ngoài module: <danh sách hoặc "không">
Đã kiểm chứng: <test nào, số lượng, chạy thật cái gì>
Chưa kiểm chứng: <cái gì, vì sao, người dùng cần thử gì>
Vấn đề phát hiện ngoài phạm vi: <danh sách hoặc "không">
Vault đã cập nhật: <trang nào>
```

## Đặc thù khi AI chạy trên cloud hoặc sandbox
- Sandbox không truy cập được bilibili, Google Translate, edge-tts. Mọi đường gọi mạng thật chỉ kiểm chứng được qua người dùng: phải nói rõ điều này, không báo "đã chạy".
- Ghi file về máy theo lô nhỏ, file lá trước, file nối (`container.py`, `router.py`) sau.
- AI không có shell trên máy người dùng thì việc `git status`, `git diff`, commit là của người dùng: ghi vào [[Việc cần làm]].
