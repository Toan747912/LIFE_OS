"""Chạy các stage theo thứ tự cho một job và ghi trạng thái kết thúc."""
from __future__ import annotations

import logging
import threading
from typing import List

from modules.bilibili_dubbing.domain.enums import JobStatus
from modules.bilibili_dubbing.domain.errors import BilibiliError, JobCancelled
from modules.bilibili_dubbing.domain.models import Job
from modules.bilibili_dubbing.pipeline.context import JobContext
from modules.bilibili_dubbing.pipeline.stages import PipelinePause, PipelineStage
from modules.bilibili_dubbing.storage.repositories import JobRepository
from modules.bilibili_dubbing.storage.storage_manager import StorageManager

logger = logging.getLogger(__name__)


class DubbingPipeline:
    def __init__(self, stages: List[PipelineStage], jobs: JobRepository, storage: StorageManager):
        self._stages = list(stages)
        self._jobs = jobs
        self._storage = storage

    def run(self, job: Job, cancel_event: threading.Event) -> None:
        ctx = JobContext(job, self._storage.job_dir(job.id), self._jobs, cancel_event)
        current = None
        try:
            for stage in self._stages:
                ctx.check_cancelled()
                if stage.is_done(ctx):
                    continue
                current = stage
                if stage.announce:
                    self._jobs.update(job.id, status=stage.status, stage=stage.name, progress=0, error=None)
                stage.run(ctx)
            self._jobs.update(job.id, status=JobStatus.DONE, stage=None, progress=100, message="Hoàn tất.")
        except PipelinePause as pause:
            if ctx.cancelled:
                self._jobs.update(job.id, status=JobStatus.CANCELLED, message="Đã hủy.")
                return
            self._jobs.update(job.id, status=pause.status, stage=getattr(current, "name", None),
                              progress=0, message=pause.message)
        except Exception as exc:  # noqa: BLE001 - mọi lỗi của một job phải được ghi lại, không làm chết worker
            if ctx.cancelled or isinstance(exc, JobCancelled):
                self._jobs.update(job.id, status=JobStatus.CANCELLED, message="Đã hủy.")
                return
            if isinstance(exc, BilibiliError):
                message = exc.message
            else:
                logger.exception("Job %s lỗi ở stage %s", job.id, getattr(current, "name", "?"))
                message = f"Lỗi không mong đợi: {type(exc).__name__}: {exc}"
            self._jobs.update(job.id, status=JobStatus.FAILED, error=message[:1000], message="Thất bại.")
