"""Thống kê dung lượng và dọn dẹp. Mọi thao tác xóa đều đi qua StorageManager nên chỉ chạm thư mục của module."""
from __future__ import annotations

import shutil
from typing import Any, Dict, List

from modules.bilibili_dubbing.domain.enums import ACTIVE_STATUSES, RETRYABLE_STATUSES
from modules.bilibili_dubbing.domain.errors import InvalidRequest
from modules.bilibili_dubbing.storage.library_mover import ITEM_PREFIX
from modules.bilibili_dubbing.storage.repositories import JobRepository, LibraryRepository
from modules.bilibili_dubbing.storage.storage_manager import StorageManager

# Tên mục dọn dẹp -> mô tả hiển thị
CLEANUP_TARGETS = {
    "stopped_jobs": "File tạm của job đã thất bại hoặc đã hủy (chạy lại sẽ phải tải lại từ đầu)",
    "orphan_work": "File tạm không thuộc job nào",
    "kept_sources": "Video gốc đang giữ kèm bản lồng tiếng",
    "orphan_library": "Thư mục trong thư viện không có trong danh sách video",
}


class StorageService:
    def __init__(self, storage: StorageManager, library: LibraryRepository, jobs: JobRepository):
        self._storage = storage
        self._library = library
        self._jobs = jobs

    # ── Phân loại thư mục ─────────────────────────────────────────────────────
    def _work_dirs(self) -> Dict[str, List[str]]:
        jobs = {job.id: job.status for job in self._jobs.list()}
        retryable = {s.value for s in RETRYABLE_STATUSES}
        active = {s.value for s in ACTIVE_STATUSES}
        groups: Dict[str, List[str]] = {"stopped_jobs": [], "orphan_work": [], "active": []}
        root = self._storage.work_root
        for folder in (root.iterdir() if root.is_dir() else []):
            if not folder.is_dir():
                continue
            status = jobs.get(folder.name)
            if status in active:
                groups["active"].append(folder.name)
            elif status in retryable:
                groups["stopped_jobs"].append(folder.name)
            else:
                groups["orphan_work"].append(folder.name)       # job đã xóa hoặc đã xong
        return groups

    def _orphan_library_dirs(self) -> List[str]:
        known = {item.id for item in self._library.list()}
        root = self._storage.library_root
        return sorted(p.name for p in (root.iterdir() if root.is_dir() else [])
                      if p.is_dir() and p.name.startswith(ITEM_PREFIX) and p.name not in known)

    def _source_size(self, item) -> int:
        try:
            return self._storage.item_file(item.id, item.source_rel).stat().st_size
        except Exception:  # noqa: BLE001 - file không còn thì coi như 0
            return 0

    # ── Thống kê ──────────────────────────────────────────────────────────────
    def usage(self) -> Dict[str, Any]:
        items = self._library.list()
        library_root, work_root = self._storage.library_root, self._storage.work_root
        work = self._work_dirs()
        size_of = lambda root, names: sum(self._storage.dir_size(root / name) for name in names)  # noqa: E731
        orphan_library = self._orphan_library_dirs()
        library_root.mkdir(parents=True, exist_ok=True)
        disk = shutil.disk_usage(library_root)
        cleanable = {
            "stopped_jobs": {"count": len(work["stopped_jobs"]), "bytes": size_of(work_root, work["stopped_jobs"])},
            "orphan_work": {"count": len(work["orphan_work"]), "bytes": size_of(work_root, work["orphan_work"])},
            "kept_sources": {"count": sum(1 for i in items if i.source_rel),
                             "bytes": sum(self._source_size(i) for i in items if i.source_rel)},
            "orphan_library": {"count": len(orphan_library), "bytes": size_of(library_root, orphan_library)},
        }
        for name, info in cleanable.items():
            info["label"] = CLEANUP_TARGETS[name]
        return {
            "library_root": str(library_root),
            "is_default_root": not self._storage.has_custom_root,
            "item_count": len(items),
            "library_bytes": sum(self._storage.dir_size(library_root / item.id) for item in items),
            "work_bytes": self._storage.dir_size(work_root),
            "active_work_bytes": size_of(work_root, work["active"]),
            "disk_free_bytes": disk.free,
            "disk_total_bytes": disk.total,
            "cleanable": cleanable,
        }

    # ── Dọn dẹp ───────────────────────────────────────────────────────────────
    def cleanup(self, targets: List[str]) -> Dict[str, Any]:
        unknown = [t for t in targets if t not in CLEANUP_TARGETS]
        if unknown or not targets:
            raise InvalidRequest("Chưa chọn mục cần dọn hoặc mục không hợp lệ.")
        freed: Dict[str, int] = {}
        skipped = 0
        work = self._work_dirs()
        for name in ("stopped_jobs", "orphan_work"):
            if name not in targets:
                continue
            freed[name] = 0
            for job_id in work[name]:
                before = self._storage.dir_size(self._storage.work_root / job_id)
                self._storage.remove_job_dir(job_id)
                after = self._storage.dir_size(self._storage.work_root / job_id)
                freed[name] += before - after
                skipped += 1 if after else 0
        if "orphan_library" in targets:
            freed["orphan_library"] = 0
            for item_id in self._orphan_library_dirs():
                before = self._storage.dir_size(self._storage.library_root / item_id)
                self._storage.remove_item_dir(item_id)
                after = self._storage.dir_size(self._storage.library_root / item_id)
                freed["orphan_library"] += before - after
                skipped += 1 if after else 0
        if "kept_sources" in targets:
            freed["kept_sources"] = 0
            for item in self._library.list():
                if not item.source_rel:
                    continue
                size = self._source_size(item)
                try:
                    self._storage.remove_item_file(item.id, item.source_rel)
                except Exception:  # noqa: BLE001 - file đang được phát: bỏ qua, lần sau dọn tiếp
                    skipped += 1
                    continue
                self._library.update(item.id, source_rel=None,
                                     size_bytes=self._storage.dir_size(self._storage.item_dir(item.id, create=False)))
                freed["kept_sources"] += size
        return {"freed": freed, "freed_bytes": sum(freed.values()), "skipped_busy": skipped}
