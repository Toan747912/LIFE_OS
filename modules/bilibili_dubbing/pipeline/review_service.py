"""Nghiệp vụ của bước phụ đề và duyệt: upload file, đổi nguồn, đọc/sửa câu, duyệt để chạy tiếp."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from modules.bilibili_dubbing.domain.enums import JobStatus, SubtitleSourceType
from modules.bilibili_dubbing.domain.errors import Conflict, InvalidRequest, NotFound
from modules.bilibili_dubbing.domain.models import Job
from modules.bilibili_dubbing.pipeline.runner import JobRunner
from modules.bilibili_dubbing.pipeline.stages import REVIEW_MARKER, VI_SUBTITLE_FILE, DownloadStage, SubtitleStage
from modules.bilibili_dubbing.pipeline.context import JobContext
from modules.bilibili_dubbing.storage.repositories import CueRepository, JobRepository
from modules.bilibili_dubbing.storage.storage_manager import StorageManager
from modules.bilibili_dubbing.subtitles.document import SubtitleDocument
from modules.bilibili_dubbing.subtitles.providers import UPLOAD_EXTENSIONS, UPLOADED_STEM

MAX_SUBTITLE_BYTES = 5 * 1024 * 1024
MAX_CUE_CHARS = 1000


class ReviewService:
    def __init__(self, jobs: JobRepository, cues: CueRepository, runner: JobRunner, storage: StorageManager):
        self._jobs = jobs
        self._cues = cues
        self._runner = runner
        self._storage = storage

    # ── Tiện ích ──────────────────────────────────────────────────────────────
    def _job_in(self, job_id: str, status: JobStatus, action: str) -> Job:
        job = self._jobs.get(job_id)
        if job.status != status.value:
            raise Conflict(f"Chỉ {action} được khi job đang ở bước tương ứng.")
        return job

    def _requeue(self, job_id: str) -> Job:
        self._jobs.update(job_id, status=JobStatus.QUEUED, error=None, message="Đang chờ tới lượt.")
        self._runner.start()
        self._runner.enqueue(job_id)
        return self._jobs.get(job_id)

    def _work_dir(self, job_id: str) -> Path:
        return self._storage.job_dir(job_id, create=False)

    # ── Khi job chờ phụ đề ────────────────────────────────────────────────────
    def upload_subtitle(self, job_id: str, filename: str, content: bytes) -> Job:
        job = self._job_in(job_id, JobStatus.AWAITING_SUBTITLE, "upload phụ đề")
        extension = Path(filename or "").suffix.lower()
        if extension not in UPLOAD_EXTENSIONS:
            raise InvalidRequest("Chỉ nhận file phụ đề .srt hoặc .vtt.")
        if not content or len(content) > MAX_SUBTITLE_BYTES:
            raise InvalidRequest("File phụ đề rỗng hoặc lớn hơn 5 MB.")
        work_dir = self._work_dir(job_id)
        for old in UPLOAD_EXTENSIONS:
            (work_dir / (UPLOADED_STEM + old)).unlink(missing_ok=True)
        target = work_dir / (UPLOADED_STEM + extension)     # tên file cố định, không dùng tên người dùng gửi lên
        target.write_bytes(content)
        try:
            usable = len(SubtitleDocument.from_file(target))
        except InvalidRequest:
            target.unlink(missing_ok=True)
            raise
        if not usable:
            target.unlink(missing_ok=True)
            raise InvalidRequest("Không đọc được câu thoại nào từ file. Hãy kiểm tra định dạng và bảng mã UTF-8.")
        job.spec.subtitle_source = SubtitleSourceType.UPLOADED.value
        job.spec.subtitle_lang = None
        self._jobs.update_spec(job_id, job.spec)
        return self._requeue(job_id)

    def use_whisper(self, job_id: str) -> Job:
        job = self._job_in(job_id, JobStatus.AWAITING_SUBTITLE, "đổi nguồn phụ đề")
        job.spec.subtitle_source = SubtitleSourceType.WHISPER.value
        job.spec.subtitle_lang = None
        self._jobs.update_spec(job_id, job.spec)
        return self._requeue(job_id)

    # ── Duyệt ─────────────────────────────────────────────────────────────────
    def get_cues(self, job_id: str) -> Dict[str, Any]:
        job = self._jobs.get(job_id)
        cues = self._cues.list(job_id)
        if not cues:
            raise NotFound("Job này chưa có phụ đề.")
        work_dir = self._work_dir(job_id)
        marker = {}
        if work_dir.is_dir():
            marker = SubtitleStage.read_marker(JobContext(job, work_dir, self._jobs, _NEVER)) or {}
        return {
            "job": job.to_dict(),
            "source_lang": marker.get("lang"),
            "editable": job.status == JobStatus.AWAITING_REVIEW.value,
            "untranslated": sum(1 for c in cues if not c.vi_text.strip()),
            "cues": [c.to_dict() for c in cues],
        }

    def save_cues(self, job_id: str, edits: List[Dict[str, Any]]) -> Dict[str, Any]:
        self._job_in(job_id, JobStatus.AWAITING_REVIEW, "sửa phụ đề")
        known = {c.idx for c in self._cues.list(job_id)}
        texts: Dict[int, str] = {}
        for edit in edits:
            idx, text = edit["idx"], " ".join(str(edit.get("vi_text") or "").split())
            if idx not in known:
                raise InvalidRequest(f"Không có câu số {idx}.")
            if len(text) > MAX_CUE_CHARS:
                raise InvalidRequest(f"Câu số {idx} dài quá {MAX_CUE_CHARS} ký tự.")
            texts[idx] = text
        changed = self._cues.save_edits(job_id, texts)
        cues = self._cues.list(job_id)
        return {"changed": changed, "untranslated": sum(1 for c in cues if not c.vi_text.strip())}

    def approve(self, job_id: str) -> Job:
        self._job_in(job_id, JobStatus.AWAITING_REVIEW, "duyệt")
        work_dir = self._work_dir(job_id)
        written = SubtitleDocument.write_vtt(self._cues.list(job_id), work_dir / VI_SUBTITLE_FILE, use_vi=True)
        if written == 0:
            (work_dir / VI_SUBTITLE_FILE).unlink(missing_ok=True)
            raise InvalidRequest("Chưa có câu tiếng Việt nào. Hãy điền bản dịch trước khi duyệt.")
        (work_dir / REVIEW_MARKER).write_text("ok", encoding="utf-8")
        return self._requeue(job_id)

    def preview_path(self, job_id: str) -> Path:
        """Video gốc trong thư mục làm việc, để xem lại cảnh khi duyệt phụ đề."""
        job = self._jobs.get(job_id)
        work_dir = self._work_dir(job_id)
        marker = DownloadStage.read_marker(JobContext(job, work_dir, self._jobs, _NEVER)) if work_dir.is_dir() else None
        if marker is None:
            raise NotFound("Video của job này không còn trong thư mục làm việc.")
        return work_dir / marker["video"]


class _NeverCancelled:
    @staticmethod
    def is_set() -> bool:
        return False


_NEVER = _NeverCancelled()
