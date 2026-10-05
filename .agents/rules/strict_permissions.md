---
description: Luật cứng của LIFE_OS. Đọc vault/AI/Bắt đầu ở đây.md trước khi sửa bất cứ thứ gì.
---

# LIFE_OS — Luật cứng

Trước khi tạo, sửa hay xóa file: đọc `vault/AI/Bắt đầu ở đây.md` và `vault/Dự án/Trạng thái.md`.

1. **Chỉ sửa file người dùng đã giao trong phiên này.** Mọi file khác là cấm đụng: không refactor, không "dọn dẹp", không sửa giúp.
2. **Không sửa module Stable**: `modules/video_dubbing/`, `modules/dynamic_subtitle.py`, `modules/file_manager.py`, `yt-subtitle-extension/`, `templates/index.html`. Được gọi lại nguyên trạng, không được đổi.
3. **Không đổi tên endpoint, không đổi hình dạng JSON trả về.**
4. **Không thêm, bớt, đổi phiên bản thư viện** khi chưa được đồng ý.
5. **Thấy lỗi ngoài phạm vi thì báo, không sửa.**
6. **Không báo "xong" khi chưa kiểm chứng.** Nói rõ cái gì đã chạy thử, cái gì chưa.
7. **Không commit, không push khi chưa được yêu cầu.** Trước khi commit phải `git status` và `git diff`.
8. **Kết thúc nhiệm vụ phải cập nhật vault**: Trạng thái, Change log, Việc cần làm, nhật ký phiên.

Chi tiết: `AGENTS.md` ở thư mục gốc và thư mục `vault/`.

<!-- Chép từ vault/AI/Bắt đầu ở đây.md. Sửa ở đó trước rồi đồng bộ sang đây. -->
