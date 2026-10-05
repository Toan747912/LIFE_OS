---
tags: [module]
file: modules/file_manager.py
trạng_thái: Stable
cập_nhật: 2026-10-05
---
# File Manager

Quản lý file trong `core/input/` (`UPLOAD_DIR = "core/input"`, tương đối theo thư mục chạy).

## Hàm công khai
| Hàm | Trả về |
| --- | --- |
| `ensure_upload_dir()` | |
| `get_unique_filename(filename)` | tên không trùng (thêm `_1`, `_2`…) |
| `list_files()` | `[{"name", "size_mb"}]` |
| `rename_file(old_name, new_name)` | `{"success", "message"}` |
| `delete_file_from_disk(filename)` | `{"success", "message"}`; xóa hẳn, không vào Thùng rác |

Mọi hàm lọc tên qua `os.path.basename`.

## Quan hệ
- Được gọi bởi: [[Backend FastAPI]] (`/api/files…`, `/start-dubbing`).
- Không liên quan tới thư viện của [[Bilibili Dubbing]].

## Cấm đụng
`UPLOAD_DIR` và hình dạng dict trả về (giao diện web đọc trực tiếp).
