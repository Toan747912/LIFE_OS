---
tags: [quy-ước, meta]
cập_nhật: 2026-10-05
---
# Quy ước vault (tài liệu)

## Vai trò
Vault là nguồn sự thật duy nhất. Mỗi thông tin chỉ nằm ở **một** trang; nơi khác cần thì liên kết tới, không chép lại.

| Thông tin | Nằm ở |
| --- | --- |
| Luật cho AI | [[Bắt đầu ở đây]], [[Phạm vi và quyền]] |
| Cái gì Stable, cái gì đang làm | [[Trạng thái]] |
| Việc phải làm | [[Việc cần làm]] |
| Endpoint | [[API]] |
| Cấu trúc, luồng | [[Kiến trúc]] |
| Lịch sử thay đổi | [[Change log]] |
| Lý do | [[Nhật ký quyết định]] |
| Lỗi, giới hạn | [[Vấn đề đã biết]] |
| Chi tiết một module | `Modules/<tên>.md` |
| Diễn biến một phiên | `Nhật ký/YYYY-MM-DD.md` |

## File chỉ đường ở thư mục gốc
Các file này tồn tại vì mỗi công cụ AI tự đọc một tên file khác nhau. Chúng chỉ chứa luật cứng rút gọn và đường dẫn tới vault.

| File | Công cụ đọc |
| --- | --- |
| `AGENTS.md` | Codex, Cursor, Copilot, Antigravity và phần lớn công cụ khác |
| `CLAUDE.md` | Claude (nạp `AGENTS.md`) |
| `.agents/rules/strict_permissions.md` | Antigravity / Gemini |
| `.cursor/rules/life-os.mdc` | Cursor |
| `.github/copilot-instructions.md` | GitHub Copilot. **Chưa tạo**: AI không ghi được vào `.github/`. Cần thì tự tạo với một dòng: "Làm theo `AGENTS.md` ở thư mục gốc" |
| `PROJECT_STATUS.md`, `ARCHITECTURE.md` | trỏ tới [[Trạng thái]] và [[Kiến trúc]] cho ai còn tìm theo tên cũ |

**Khi sửa "Luật cứng" trong [[Bắt đầu ở đây]] thì sửa luôn `AGENTS.md`, `.agents/rules/strict_permissions.md` và [[Tóm tắt dán tay]]** — ba nơi này chép lại luật cứng vì AI có thể không mở được liên kết.

## Cách viết
- Một ý một ghi chú, nối bằng `[[liên kết]]`. Tên ghi chú là duy nhất trong vault.
- Viết điều đã kiểm chứng. Điều suy đoán phải ghi rõ là chưa kiểm chứng.
- Ghi ngày tuyệt đối (`2026-10-05`), không ghi "hôm qua", "tuần trước".
- Trích tên file, hàm, endpoint đúng như trong code, đặt trong dấu `` ` ``.
- Đầu mỗi trang có `cập_nhật:`; sửa trang thì sửa ngày.
- [[Nhật ký quyết định]] và [[Change log]] chỉ thêm, không sửa mục cũ.

## Ai được sửa trang nào
| Trang | AI tự cập nhật | Cần người dùng duyệt |
| --- | --- | --- |
| Trạng thái, Change log, Việc cần làm, Vấn đề đã biết, Nhật ký, Modules, API, Kiến trúc, Phát hiện | có, sau mỗi nhiệm vụ | |
| Nhật ký quyết định | thêm mục mới | sửa mục cũ |
| Bắt đầu ở đây, Phạm vi và quyền, Quy trình làm việc, Quy ước code, Quy ước git, Định nghĩa xong, trang này | | mọi thay đổi |
| Chuyển một module sang Stable | | luôn luôn |

## Câu lệnh mẫu cho Claude
| Lúc | Câu lệnh |
| --- | --- |
| Mở phiên | "Đọc `vault/AI/Bắt đầu ở đây.md` rồi tóm tắt dự án đang ở đâu và việc gì đang treo." |
| Giao việc | "Làm <việc>. Phạm vi: <file hoặc module>. Theo Quy trình làm việc." |
| Chốt phiên | "Cập nhật vault theo bước 4 của Quy trình làm việc." |
| Rà soát định kỳ | "Đọc toàn bộ vault và code, tìm chỗ vault lệch code, việc treo quá lâu, ghi chú không ai liên kết tới. Cập nhật Phát hiện - liên hệ ẩn." |

## Thẻ
`#moc` · `#ai` · `#quy-ước` · `#module` · `#dự-án` · `#quyết-định` · `#vấn-đề` · `#nhật-ký` · `#meta`

## Mẫu
[[Mẫu module]] · [[Mẫu quyết định]] · [[Mẫu nhật ký]]

## Mở bằng Obsidian
"Open folder as vault" → chọn thư mục `vault`. Thư mục `.obsidian/` (cấu hình cá nhân) đã được bỏ qua bằng `vault/.gitignore`.
