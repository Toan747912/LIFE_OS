from __future__ import annotations

from enum import Enum


class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    DOWNLOADING = "DOWNLOADING"
    PREPARING_SUBS = "PREPARING_SUBS"
    AWAITING_SUBTITLE = "AWAITING_SUBTITLE"
    TRANSLATING = "TRANSLATING"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    SYNTHESIZING = "SYNTHESIZING"
    MIXING = "MIXING"
    PUBLISHING = "PUBLISHING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


# Job đang được worker xử lý (khi server khởi động lại sẽ được đưa về hàng đợi).
RUNNING_STATUSES = frozenset({
    JobStatus.DOWNLOADING, JobStatus.PREPARING_SUBS, JobStatus.TRANSLATING,
    JobStatus.SYNTHESIZING, JobStatus.MIXING, JobStatus.PUBLISHING,
})
# Job chưa kết thúc: không được xóa, có thể hủy.
# Job đang dừng chờ người dùng (không chiếm worker).
WAITING_STATUSES = frozenset({JobStatus.AWAITING_SUBTITLE, JobStatus.AWAITING_REVIEW})
ACTIVE_STATUSES = RUNNING_STATUSES | WAITING_STATUSES | {JobStatus.QUEUED}
# Job đã dừng nhưng chạy lại được.
RETRYABLE_STATUSES = frozenset({JobStatus.FAILED, JobStatus.CANCELLED})


class SubtitleSourceType(str, Enum):
    PLATFORM = "platform"   # phụ đề có sẵn trên Bilibili
    WHISPER = "whisper"     # bóc băng bằng faster-whisper
    UPLOADED = "uploaded"   # người dùng tự upload


class SubtitleKind(str, Enum):
    UPLOADED = "uploaded"   # do người đăng video cung cấp
    AUTO = "auto"           # phụ đề AI của nền tảng
