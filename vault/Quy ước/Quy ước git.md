---
tags: [quy-ước]
cập_nhật: 2026-10-06
---
# Quy ước git

> Người dùng đã duyệt ngày 2026-10-06. Áp dụng từ commit kế tiếp; các commit trước đó không cần sửa lại.

## Luật
1. AI **không commit, không push** khi chưa được yêu cầu rõ ràng.
2. Trước mỗi commit: `git status` và `git diff`, đọc hết, đối chiếu với phạm vi nhiệm vụ.
3. Không bao giờ commit: `data/`, cookie, `.env`, file media (`*.mp4`, `*.mp3`, `*.wav`…), `core/output/`, `__pycache__/`, `vault/.obsidian/`.
4. Một commit một mục đích. Không trộn tính năng với dọn dẹp.
5. Thay đổi code và cập nhật vault tương ứng đi **cùng một commit**.
6. Không `--force`, không sửa lịch sử nhánh `main`.

## Thông điệp commit
```text
<loại>(<phạm vi>): <mô tả ngắn, tiếng Việt, không chấm cuối>

<vì sao, nếu không hiển nhiên>
<File ngoài module bị đụng: … | không>
```
| Loại | Dùng khi |
| --- | --- |
| `feat` | thêm tính năng |
| `fix` | sửa lỗi |
| `docs` | chỉ đổi vault hoặc README |
| `test` | chỉ đổi test |
| `refactor` | đổi cấu trúc, không đổi hành vi (phải được yêu cầu) |
| `chore` | dọn dẹp, cấu hình, thư viện |

Phạm vi là tên module: `bilibili`, `dubbing`, `extension`, `backend`, `vault`.

Ví dụ: `feat(bilibili): kiểm tra cookie trực tuyến` · `docs(vault): thêm quy ước code`

## Nhánh
- `main` luôn chạy được.
- Việc lớn làm trên nhánh `feat/<module>-<mô-tả-ngắn>` hoặc `fix/<mô-tả-ngắn>`, gộp về `main` khi đạt [[Định nghĩa xong]].
- Việc nhỏ một commit có thể làm thẳng trên `main`.

## Trước khi gộp
- [ ] Test qua.
- [ ] `git diff main --stat` không có file ngoài phạm vi.
- [ ] Vault đã cập nhật.
