---
description: Rule ngăn chặn AI tự ý sửa đổi code/file ngoài phạm vi cấp phép của người dùng
---

# Scope & Permission Guardrails

1. **Permission Boundary**:
   - Only edit files and features explicitly requested by the user.
   - Do NOT refactor, clean up, or rewrite unrelated files without user authorization.

2. **Reporting & Approval**:
   - If a bug or improvement is identified in an unauthorized file, propose it to the user and wait for approval before making changes.

3. **No Unintended Side Effects**:
   - Preserve existing structure, logic, and configurations outside the active task scope.
