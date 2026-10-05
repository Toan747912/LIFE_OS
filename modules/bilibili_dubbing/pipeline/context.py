"""Dữ liệu của một job đang chạy, truyền qua các stage."""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Optional

from modules.bilibili_dubbing.domain.errors import JobCancelled
from modules.bilibili_dubbing.domain.models import Job, JobSpec
from modules.bilibili_dubbing.storage.repositories import JobRepository


class JobContext:
    _MIN_WRITE_INTERVAL_S = 0.5

    def __init__(self, job: Job, work_dir: Path, jobs: JobRepository, cancel_event: threading.Event):
        self.job = job
        self.work_dir = work_dir
        self._jobs = jobs
        self._cancel_event = cancel_event
        self._last_write = 0.0
        self._last_progress = -1

    @property
    def spec(self) -> JobSpec:
        return self.job.spec

    @property
    def cancelled(self) -> bool:
        return self._cancel_event.is_set()

    def check_cancelled(self) -> None:
        if self.cancelled:
            raise JobCancelled("Job đã bị hủy.")

    def report(self, progress: Optional[int], message: str, force: bool = False) -> None:
        """Lưu tiến độ vào DB, có giới hạn tần suất để không ghi liên tục khi đang tải."""
        self.check_cancelled()
        value = self._last_progress if progress is None else max(0, min(100, int(progress)))
        now = time.monotonic()
        if not force and value == self._last_progress and now - self._last_write < self._MIN_WRITE_INTERVAL_S:
            return
        if not force and now - self._last_write < self._MIN_WRITE_INTERVAL_S and value - self._last_progress < 5:
            return
        self._last_write, self._last_progress = now, value
        self._jobs.update(self.job.id, progress=max(value, 0), message=message)
