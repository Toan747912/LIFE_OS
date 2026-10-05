"""Nghiệp vụ job: tạo từ lựa chọn của người dùng, hủy, chạy lại, xóa."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List

from modules.bilibili_dubbing.domain.enums import ACTIVE_STATUSES, RETRYABLE_STATUSES, JobStatus, SubtitleSourceType
from modules.bilibili_dubbing.domain.errors import Conflict, InvalidRequest
from modules.bilibili_dubbing.domain.models import Job, JobSpec
from modules.bilibili_dubbing.pipeline.runner import JobRunner
from modules.bilibili_dubbing.storage.repositories import JobRepository, ScanRepository
from modules.bilibili_dubbing.storage.storage_manager import StorageManager

ALLOWED_VOICES = ("vi-VN-HoaiMyNeural", "vi-VN-NamMinhNeural")


class JobService:
    def __init__(self, jobs: JobRepository, scans: ScanRepository, runner: JobRunner,
                 storage: StorageManager, max_jobs_per_request: int):
        self._jobs = jobs
        self._scans = scans
        self._runner = runner
        self._storage = storage
        self._max_jobs = max_jobs_per_request

    def create_from_selection(self, scan_id: str, items: List[Dict[str, Any]], voice: str,
                              orig_vol: float, dub_vol: float, keep_source: bool) -> List[Job]:
        """Mọi thông tin tải (URL, chuỗi chọn định dạng) lấy từ kết quả quét đã lưu, không lấy từ trình duyệt."""
        if not items:
            raise InvalidRequest("Chưa chọn tập nào.")
        if len(items) > self._max_jobs:
            raise InvalidRequest(f"Mỗi lần tạo tối đa {self._max_jobs} job.")
        if voice not in ALLOWED_VOICES:
            raise InvalidRequest("Giọng đọc không hợp lệ.")
        if not (0 <= orig_vol <= 1 and 0.5 <= dub_vol <= 2):
            raise InvalidRequest("Âm lượng không hợp lệ.")

        scan = self._scans.get(scan_id)
        specs = [self._build_spec(scan, item, voice, orig_vol, dub_vol, keep_source) for item in items]
        keys = [(s.result_index, s.episode_id) for s in specs]
        if len(set(keys)) != len(keys):
            raise InvalidRequest("Có tập bị chọn trùng.")

        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        jobs = []
        for spec in specs:
            job = Job(id="job_" + uuid.uuid4().hex[:12], title=spec.title, spec=spec,
                      status=JobStatus.QUEUED.value, created_at=now, updated_at=now, message="Đang chờ tới lượt.")
            self._jobs.create(job)
            jobs.append(job)
        self._runner.start()
        for job in jobs:
            self._runner.enqueue(job.id)
        return jobs

    @staticmethod
    def _build_spec(scan, item: Dict[str, Any], voice: str, orig_vol: float, dub_vol: float,
                    keep_source: bool) -> JobSpec:
        result_index, episode_id = item["result_index"], item["episode_id"]
        episode = scan.find_episode(result_index, episode_id)
        result = scan.results[result_index]
        if not (episode.probed and episode.accessible):
            raise InvalidRequest(f"Tập '{episode.title}' chưa quét chi tiết hoặc không truy cập được.")
        chosen = next((f for f in episode.formats if f.format_id == item["format_id"]), None)
        if chosen is None:
            raise InvalidRequest(f"Chất lượng đã chọn không có trong kết quả quét của '{episode.title}'.")

        raw_subtitle = item.get("subtitle") or SubtitleSourceType.WHISPER.value
        kind, _, lang = raw_subtitle.partition(":")
        if kind == SubtitleSourceType.PLATFORM.value:
            if lang not in {track.lang for track in episode.subtitles}:
                raise InvalidRequest(f"Phụ đề '{lang}' không có trong kết quả quét của '{episode.title}'.")
        elif kind in (SubtitleSourceType.WHISPER.value, SubtitleSourceType.UPLOADED.value):
            lang = ""
        else:
            raise InvalidRequest("Nguồn phụ đề không hợp lệ.")

        is_series = result.kind == "playlist"
        return JobSpec(
            scan_id=scan.scan_id, result_index=result_index, episode_id=episode_id,
            source=result.source or "", url=episode.url, title=episode.title,
            format_id=chosen.format_id, selector=chosen.selector, quality_label=chosen.label,
            codec=chosen.codec, browser_playable=chosen.browser_playable,
            series_title=result.title if is_series else None,
            episode_label=f"Tập {episode.index}" if is_series else None,
            expected_bytes=chosen.size_bytes, subtitle_source=kind, subtitle_lang=lang or None,
            voice=voice, orig_vol=orig_vol, dub_vol=dub_vol, keep_source=keep_source,
        )

    def list(self) -> List[Job]:
        self._runner.start()   # mở tab Hàng đợi sau khi khởi động lại server sẽ tiếp tục job dang dở
        return self._jobs.list()

    def get(self, job_id: str) -> Job:
        return self._jobs.get(job_id)

    def cancel(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job.status not in {s.value for s in ACTIVE_STATUSES}:
            raise Conflict("Job đã kết thúc nên không hủy được.")
        self._runner.cancel(job_id)
        return self._jobs.get(job_id)

    def retry(self, job_id: str) -> Job:
        job = self._jobs.get(job_id)
        if job.status not in {s.value for s in RETRYABLE_STATUSES}:
            raise Conflict("Chỉ chạy lại được job đã thất bại hoặc đã hủy.")
        self._jobs.update(job_id, status=JobStatus.QUEUED, error=None, message="Đang chờ tới lượt.")
        self._runner.start()
        self._runner.enqueue(job_id)
        return self._jobs.get(job_id)

    def clear_finished(self) -> int:
        """Xóa khỏi danh sách mọi job đã hoàn tất. Video trong thư viện không bị ảnh hưởng."""
        finished = self._jobs.ids_with_status([JobStatus.DONE])
        for job_id in finished:
            self._storage.remove_job_dir(job_id)
            self._jobs.delete(job_id)
        return len(finished)

    def delete(self, job_id: str) -> None:
        job = self._jobs.get(job_id)
        if job.status in {s.value for s in ACTIVE_STATUSES} or self._runner.is_running(job_id):
            raise Conflict("Hãy hủy job trước khi xóa.")
        self._storage.remove_job_dir(job_id)
        self._jobs.delete(job_id)
