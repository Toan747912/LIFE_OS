# AI Assistant Role & Scope Rules (Quy tắc Giới hạn Quyền & Vai trò của AI)

## 1. Nguyên Tắc Cấp Quyền & Phạm Vi Hoạt Động (Strict Permission Scoping)
- **CHỈ SỬA ĐỔI KHI ĐƯỢC CẤP QUYỀN**: AI chỉ được phép tạo, chỉnh sửa hoặc xóa các file và tính năng mà người dùng đã chỉ định hoặc yêu cầu trực tiếp trong phiên làm việc.
- **TẤT CẢ FILE KHÁC LÀ PHẠM VI CẤM (NO-TOUCH)**: Không tự ý chỉnh sửa, tối ưu hóa (refactor), hay "dọn dẹp" các file/module chưa được người dùng cấp phép đụng tới.
- **BÁO CÁO TRƯỚC KHI THAY ĐỔI**: Nếu phát hiện ra lỗi, vấn đề hiệu năng hoặc xung đột ở các file nằm ngoài scope được giao, AI phải giải thích và xin ý kiến người dùng trước khi tiến hành chỉnh sửa.

## 2. Kiểm Soát Thay Đổi (Change Control & Safety)
- **KHÔNG SỬA BẬY (No Unwanted Side Effects)**: Bảo lưu nguyên vẹn logic, comment, và cấu hình hiện có của các tính năng không liên quan.
- **KHÔNG TỰ Ý THÊM/XÓA DEPENDENCIES**: Không tự thêm thư viện ngoài hoặc thay đổi phiên bản dependencies trừ khi người dùng đồng ý.
- **VERIFY KỸ TRƯỚC KHI COMMIT**: Trước khi thực hiện `git commit`, AI phải luôn chạy `git status` và `git diff` để đảm bảo không commit nhầm các file rác hoặc các thay đổi không mong muốn.
