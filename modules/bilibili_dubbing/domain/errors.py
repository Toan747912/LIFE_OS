"""Cây exception của module. Router đổi chúng thành mã HTTP + thông báo tiếng Việt."""
from __future__ import annotations


class BilibiliError(Exception):
    code = "bilibili_error"
    http_status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class UnsupportedUrl(BilibiliError):
    code = "unsupported_url"
    http_status = 400


class InvalidRequest(BilibiliError):
    code = "invalid_request"
    http_status = 400


class NotFound(BilibiliError):
    code = "not_found"
    http_status = 404


class DependencyMissing(BilibiliError):
    code = "dependency_missing"
    http_status = 503


class AccessDenied(BilibiliError):
    """Nội dung khóa vùng / cần đăng nhập / cần VIP. Module không tìm cách vượt qua."""

    code = "access_denied"
    http_status = 403


class ContentUnavailable(BilibiliError):
    code = "content_unavailable"
    http_status = 404


class ScanFailed(BilibiliError):
    code = "scan_failed"
    http_status = 502


class Conflict(BilibiliError):
    code = "conflict"
    http_status = 409


class InsufficientSpace(BilibiliError):
    code = "insufficient_space"
    http_status = 507


class UnsafePath(BilibiliError):
    """Đường dẫn nằm ngoài thư mục module được phép ghi/xóa."""

    code = "unsafe_path"
    http_status = 400


class JobCancelled(BilibiliError):
    code = "job_cancelled"
    http_status = 409


class FileBusy(BilibiliError):
    """File đang bị tiến trình khác giữ (thường gặp trên Windows khi video đang được phát)."""

    code = "file_busy"
    http_status = 409
