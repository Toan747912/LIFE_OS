"""Nghiệp vụ thư viện: xem, tìm, lọc, sửa thông tin, phân loại theo series/tag, xóa."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.bilibili_dubbing.domain.errors import InvalidRequest
from modules.bilibili_dubbing.domain.models import LibraryItem
from modules.bilibili_dubbing.storage.repositories import LibraryRepository, TaxonomyRepository
from modules.bilibili_dubbing.storage.storage_manager import StorageManager
from modules.bilibili_dubbing.storage.text_utils import clean_name, fold

MAX_TITLE = 200
MAX_NOTE = 2000
MAX_NAME = 80
MAX_TAG = 30
MAX_TAGS_PER_ITEM = 12
SORTS = {
    "newest": (lambda v: v["created_at"], True),
    "oldest": (lambda v: v["created_at"], False),
    "title": (lambda v: fold(v["title"]), False),
    "size": (lambda v: v["size_bytes"], True),
    "duration": (lambda v: v["duration_s"] or 0, True),
}


class LibraryService:
    def __init__(self, library: LibraryRepository, storage: StorageManager, taxonomy: TaxonomyRepository):
        self._library = library
        self._storage = storage
        self._taxonomy = taxonomy

    # ── Xem ───────────────────────────────────────────────────────────────────
    def _view(self, item: LibraryItem, series_names: dict, tags: dict) -> Dict[str, Any]:
        data = item.to_dict()
        data["series"] = series_names.get(item.series_id)
        data["tags"] = tags.get(item.id, [])
        return data

    def get(self, item_id: str) -> Dict[str, Any]:
        return self._view(self._library.get(item_id), self._taxonomy.series_names(), self._taxonomy.tags_by_item())

    def list(self, q: str = "", series_id: Optional[int] = None, tag: str = "", status: str = "",
             sort: str = "newest") -> List[Dict[str, Any]]:
        if sort not in SORTS:
            raise InvalidRequest("Cách sắp xếp không hợp lệ.")
        if status not in ("", "dubbed", "undubbed"):
            raise InvalidRequest("Bộ lọc trạng thái không hợp lệ.")
        series_names, tags = self._taxonomy.series_names(), self._taxonomy.tags_by_item()
        views = [self._view(item, series_names, tags) for item in self._library.list()]
        words = fold(q).split()
        wanted_tag = fold(tag)

        def matches(view: Dict[str, Any]) -> bool:
            if series_id is not None and view["series_id"] != series_id:
                return False
            if wanted_tag and wanted_tag not in {fold(t) for t in view["tags"]}:
                return False
            if status and view["dubbed"] != (status == "dubbed"):
                return False
            haystack = fold(" ".join([view["title"], view["note"], view["series"] or "",
                                      view["episode_label"] or "", " ".join(view["tags"])]))
            return all(word in haystack for word in words)

        key, reverse = SORTS[sort]
        return sorted((v for v in views if matches(v)), key=key, reverse=reverse)

    # ── File ──────────────────────────────────────────────────────────────────
    def video_path(self, item_id: str, kind: str = "main") -> Path:
        """kind: "main" (sản phẩm, đã lồng tiếng nếu có) hoặc "source" (video gốc, chỉ có khi chọn giữ lại)."""
        item = self._library.get(item_id)
        return self._storage.item_file(item_id, item.source_rel if kind == "source" else item.video_rel)

    def subtitle_path(self, item_id: str, kind: str = "auto") -> Path:
        """kind: "vi" (bản đã duyệt), "orig" (phụ đề gốc) hoặc "auto" (ưu tiên tiếng Việt)."""
        item = self._library.get(item_id)
        relative = {"vi": item.sub_vi_rel, "orig": item.sub_orig_rel}.get(kind, item.sub_vi_rel or item.sub_orig_rel)
        return self._storage.item_file(item_id, relative)

    def thumbnail_path(self, item_id: str) -> Path:
        return self._storage.item_file(item_id, self._library.get(item_id).thumb_rel)

    def download_name(self, item_id: str, kind: str = "main") -> str:
        """Tên file khi tải về: lấy từ tiêu đề, bỏ ký tự Windows không cho phép."""
        title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", self._library.get(item_id).title)
        title = re.sub(r"\s+", " ", title).strip(" .")[:120]
        return (title or item_id) + (" (gốc)" if kind == "source" else "") + ".mp4"

    # ── Sửa ───────────────────────────────────────────────────────────────────
    def update(self, item_id: str, title: Optional[str] = None, note: Optional[str] = None,
               series: Optional[str] = None, tags: Optional[List[str]] = None) -> Dict[str, Any]:
        """Chỉ đổi những trường được gửi lên. `series` rỗng = bỏ khỏi series. Chỉ đổi thông tin, không đổi file."""
        self._library.get(item_id)
        fields: Dict[str, Any] = {}
        if title is not None:
            cleaned = clean_name(title, MAX_TITLE)
            if not cleaned:
                raise InvalidRequest("Tên video không được để trống.")
            fields["title"] = cleaned
        if note is not None:
            if len(note) > MAX_NOTE:
                raise InvalidRequest(f"Ghi chú dài quá {MAX_NOTE} ký tự.")
            fields["note"] = note.strip()
        if series is not None:
            name = clean_name(series, MAX_NAME)
            fields["series_id"] = self._taxonomy.get_or_create_series(name) if name else None
        self._library.update(item_id, **fields)
        if tags is not None:
            self._taxonomy.set_item_tags(item_id, self._clean_tags(tags))
        return self.get(item_id)

    @staticmethod
    def _clean_tags(tags: List[str]) -> List[str]:
        unique: Dict[str, str] = {}
        for raw in tags:
            name = clean_name(str(raw).lstrip("#"), MAX_TAG)
            if name:
                unique.setdefault(name.casefold(), name)
        if len(unique) > MAX_TAGS_PER_ITEM:
            raise InvalidRequest(f"Mỗi video tối đa {MAX_TAGS_PER_ITEM} tag.")
        return list(unique.values())

    def delete(self, item_id: str) -> None:
        self._library.get(item_id)             # báo 404 nếu không tồn tại
        self._storage.remove_item_dir(item_id, strict=True)   # file đang bị giữ thì báo lỗi, giữ nguyên bản ghi
        self._library.delete(item_id)
        self._taxonomy.set_item_tags(item_id, [])              # dọn tag không còn ai dùng

    # ── Series và tag ─────────────────────────────────────────────────────────
    def list_series(self) -> list:
        return self._taxonomy.list_series()

    def rename_series(self, series_id: int, name: str) -> None:
        cleaned = clean_name(name, MAX_NAME)
        if not cleaned:
            raise InvalidRequest("Tên series không được để trống.")
        self._taxonomy.rename_series(series_id, cleaned)

    def delete_series(self, series_id: int) -> None:
        self._taxonomy.delete_series(series_id)

    def list_tags(self) -> list:
        return self._taxonomy.list_tags()

    def delete_tag(self, tag_id: int) -> None:
        self._taxonomy.delete_tag(tag_id)
