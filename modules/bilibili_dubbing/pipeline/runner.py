"""Hàng đợi một worker: mỗi lúc chỉ xử lý một job vì tải, Whisper và FFmpeg đều nặng."""
from __future__ import annotations

import logging
import queue
import threading
from typing import Dict, Optional

from modules.bilibili_dubbing.domain.enums import ACTIVE_STATUSES, RUNNING_STATUSES, JobStatus
from modules.bilibili_dubbing.domain.errors import NotFound
from modules.bilibili_dubbing.pipeline.pipeline import DubbingPipeline
from modules.bilibili_dubbing.storage.repositories import JobRepository

logger = logging.getLogger(__name__)


class JobRunner:
    def __init__(self, pipeline: DubbingPipeline, jobs: JobRepository):
        self._pipeline = pipeline
        self._jobs = jobs
        self._queue: "queue.Queue[Optional[str]]" = queue.Queue()
        self._cancel_events: Dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._current: Optional[str] = None
        self._gate = threading.Event()     # bật = worker được phép bắt đầu job mới
        self._gate.set()

    # ── Vòng đời ──────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Khôi phục job dang dở rồi bật worker. Gọi nhiều lần cũng chỉ bật một worker."""
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._jobs.reset_running(RUNNING_STATUSES, JobStatus.QUEUED)
            for job_id in self._jobs.ids_with_status([JobStatus.QUEUED]):
                self._queue.put(job_id)
            self._thread = threading.Thread(target=self._loop, name="bilibili-job-runner", daemon=True)
            self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        thread = self._thread
        if thread is None:
            return
        self._queue.put(None)
        thread.join(timeout)

    # ── Thao tác ──────────────────────────────────────────────────────────────
    def enqueue(self, job_id: str) -> None:
        with self._lock:
            self._cancel_events.pop(job_id, None)
        self._queue.put(job_id)

    def cancel(self, job_id: str) -> None:
        """Job đang chạy sẽ dừng ở lần báo tiến độ kế tiếp; job đang chờ bị đánh dấu hủy ngay."""
        with self._lock:
            self._cancel_events.setdefault(job_id, threading.Event()).set()
            running = self._current == job_id
        if not running:
            self._jobs.update(job_id, status=JobStatus.CANCELLED, message="Đã hủy.")

    def pause(self) -> bool:
        """Ngừng bắt đầu job mới (job vẫn được xếp hàng). Trả về False nếu đang có job chạy dở."""
        with self._lock:
            if self._current is not None:
                return False
            self._gate.clear()
            return True

    def resume(self) -> None:
        self._gate.set()

    @property
    def paused(self) -> bool:
        return not self._gate.is_set()

    def is_running(self, job_id: str) -> bool:
        with self._lock:
            return self._current == job_id

    # ── Worker ────────────────────────────────────────────────────────────────
    def _loop(self) -> None:
        while True:
            job_id = self._queue.get()
            if job_id is None:
                return
            self._gate.wait()
            try:
                self._run_one(job_id)
            except Exception:  # noqa: BLE001 - worker không được chết vì một job
                logger.exception("Lỗi khi xử lý job %s", job_id)
            finally:
                with self._lock:
                    self._current = None
                    self._cancel_events.pop(job_id, None)

    def _run_one(self, job_id: str) -> None:
        try:
            job = self._jobs.get(job_id)
        except NotFound:
            return
        if job.status != JobStatus.QUEUED.value:
            return   # đã bị hủy hoặc xóa trong lúc chờ
        with self._lock:
            if not self._gate.is_set():
                self._queue.put(job_id)      # vừa bị tạm dừng: trả job về hàng đợi, chờ mở lại
                return
            event = self._cancel_events.setdefault(job_id, threading.Event())
            if event.is_set():
                return
            self._current = job_id
        self._pipeline.run(job, event)
        # Lệnh hủy có thể tới đúng lúc pipeline vừa dừng ở trạng thái chờ (duyệt, phụ đề): khi đó pipeline
        # không còn kiểm tra cờ hủy nữa, nên phải tự đánh dấu ở đây kẻo job kẹt mãi ở trạng thái chờ.
        with self._lock:
            cancelled_late = event.is_set()
            self._current = None
        if cancelled_late:
            try:
                status = self._jobs.get(job_id).status
            except NotFound:
                return
            if status in {s.value for s in ACTIVE_STATUSES}:
                self._jobs.update(job_id, status=JobStatus.CANCELLED, message="Đã hủy.")
