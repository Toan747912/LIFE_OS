"""Tầng HTTP của module. Chỉ gọi service, không chứa logic xử lý video."""
from __future__ import annotations

from dataclasses import asdict
from typing import Callable, Optional

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.routing import APIRoute

from modules.bilibili_dubbing.api.container import ServiceContainer, get_container
from modules.bilibili_dubbing.api.schemas import (
    CleanupRequest,
    CookieRequest,
    CreateJobsRequest,
    ProbeRequest,
    RenameRequest,
    SaveCuesRequest,
    ScanRequest,
    SettingsRequest,
    StorageRootRequest,
    UpdateItemRequest,
)
from modules.bilibili_dubbing.api.streaming import range_response
from modules.bilibili_dubbing.domain.errors import BilibiliError

_STATIC_FILES = {
    "bilibili.js": "application/javascript",
    "bilibili.css": "text/css",
}


class BilibiliRoute(APIRoute):
    """Đổi BilibiliError thành JSON lỗi, chỉ áp dụng cho route của module này."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def handler(request: Request) -> Response:
            try:
                return await original(request)
            except BilibiliError as exc:
                return JSONResponse(
                    status_code=exc.http_status,
                    content={"error": exc.message, "code": exc.code},
                )

        return handler


router = APIRouter(route_class=BilibiliRoute, tags=["bilibili"])


# ── Trang giao diện ───────────────────────────────────────────────────────────
@router.get("/bilibili", include_in_schema=False)
def bilibili_page(container: ServiceContainer = Depends(get_container)):
    return FileResponse(container.settings.web_dir / "bilibili.html", media_type="text/html")


@router.get("/bilibili/static/{filename}", include_in_schema=False)
def bilibili_static(filename: str, container: ServiceContainer = Depends(get_container)):
    media_type = _STATIC_FILES.get(filename)
    if media_type is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy file.")
    return FileResponse(
        container.settings.web_dir / "static" / filename,
        media_type=media_type,
        headers={"Cache-Control": "no-cache"},
    )


# ── API ───────────────────────────────────────────────────────────────────────
@router.get("/api/bilibili/health")
def health(container: ServiceContainer = Depends(get_container)):
    return container.health()


@router.post("/api/bilibili/scan")
def scan(body: ScanRequest, container: ServiceContainer = Depends(get_container)):
    """Quét các link: liệt kê tập, chất lượng và phụ đề. Không tải video."""
    return container.scan_service.scan(body.urls).to_dict()


@router.get("/api/bilibili/scan/{scan_id}")
def get_scan(scan_id: str, container: ServiceContainer = Depends(get_container)):
    return container.scan_service.get(scan_id).to_dict()


@router.post("/api/bilibili/scan/{scan_id}/probe")
def probe_episode(scan_id: str, body: ProbeRequest, container: ServiceContainer = Depends(get_container)):
    """Quét chi tiết một tập chưa được quét (dùng cho series dài)."""
    episode = container.scan_service.probe_episode(scan_id, body.result_index, body.episode_id)
    return asdict(episode)


# ── Cài đặt: cookie đăng nhập ─────────────────────────────────────────────────
@router.get("/api/bilibili/settings/cookie")
def cookie_status(container: ServiceContainer = Depends(get_container)):
    """Trạng thái cookie. Không bao giờ trả về giá trị cookie."""
    return container.cookie_store.status()


@router.put("/api/bilibili/settings/cookie")
def save_cookie(body: CookieRequest, container: ServiceContainer = Depends(get_container)):
    return container.cookie_store.save_from_text(body.text, body.site)


@router.post("/api/bilibili/settings/cookie/check")
def check_cookie(container: ServiceContainer = Depends(get_container)):
    """Hỏi máy chủ Bilibili xem cookie đã lưu còn đăng nhập được không."""
    return container.cookie_checker.check()


@router.delete("/api/bilibili/settings/cookie")
def delete_cookie(container: ServiceContainer = Depends(get_container)):
    return container.cookie_store.clear()


# ── Job ───────────────────────────────────────────────────────────────────────
@router.post("/api/bilibili/jobs")
def create_jobs(body: CreateJobsRequest, container: ServiceContainer = Depends(get_container)):
    """Tạo mỗi tập một job từ lựa chọn của người dùng và đưa vào hàng đợi."""
    jobs = container.job_service.create_from_selection(
        scan_id=body.scan_id, items=[item.model_dump() for item in body.items], voice=body.voice,
        orig_vol=body.orig_vol, dub_vol=body.dub_vol, keep_source=body.keep_source,
    )
    return {"jobs": [job.to_dict() for job in jobs]}


@router.get("/api/bilibili/jobs")
def list_jobs(container: ServiceContainer = Depends(get_container)):
    return {"jobs": [job.to_dict() for job in container.job_service.list()]}


@router.post("/api/bilibili/jobs/clear-finished")
def clear_finished_jobs(container: ServiceContainer = Depends(get_container)):
    """Dọn các job đã hoàn tất khỏi hàng đợi (video trong thư viện được giữ nguyên)."""
    return {"deleted": container.job_service.clear_finished()}


@router.get("/api/bilibili/jobs/{job_id}")
def get_job(job_id: str, container: ServiceContainer = Depends(get_container)):
    return container.job_service.get(job_id).to_dict()


@router.post("/api/bilibili/jobs/{job_id}/cancel")
def cancel_job(job_id: str, container: ServiceContainer = Depends(get_container)):
    return container.job_service.cancel(job_id).to_dict()


@router.post("/api/bilibili/jobs/{job_id}/retry")
def retry_job(job_id: str, container: ServiceContainer = Depends(get_container)):
    return container.job_service.retry(job_id).to_dict()


@router.delete("/api/bilibili/jobs/{job_id}")
def delete_job(job_id: str, container: ServiceContainer = Depends(get_container)):
    container.job_service.delete(job_id)
    return {"deleted": job_id}


# ── Phụ đề và duyệt ───────────────────────────────────────────────────────────
@router.post("/api/bilibili/jobs/{job_id}/subtitle")
async def upload_job_subtitle(job_id: str, file: UploadFile = File(...),
                              container: ServiceContainer = Depends(get_container)):
    """Upload file .srt/.vtt cho job đang chờ phụ đề."""
    content = await file.read(5 * 1024 * 1024 + 1)
    return container.review_service.upload_subtitle(job_id, file.filename or "", content).to_dict()


@router.post("/api/bilibili/jobs/{job_id}/use-whisper")
def use_whisper_for_job(job_id: str, container: ServiceContainer = Depends(get_container)):
    """Job đang chờ phụ đề chuyển sang để Whisper tự bóc băng."""
    return container.review_service.use_whisper(job_id).to_dict()


@router.get("/api/bilibili/jobs/{job_id}/cues")
def get_job_cues(job_id: str, container: ServiceContainer = Depends(get_container)):
    return container.review_service.get_cues(job_id)


@router.put("/api/bilibili/jobs/{job_id}/cues")
def save_job_cues(job_id: str, body: SaveCuesRequest, container: ServiceContainer = Depends(get_container)):
    return container.review_service.save_cues(job_id, [cue.model_dump() for cue in body.cues])


@router.post("/api/bilibili/jobs/{job_id}/approve")
def approve_job_cues(job_id: str, container: ServiceContainer = Depends(get_container)):
    """Duyệt bản dịch: ghi phụ đề tiếng Việt và cho job chạy tiếp."""
    return container.review_service.approve(job_id).to_dict()


@router.get("/api/bilibili/jobs/{job_id}/preview")
def preview_job_video(
    job_id: str,
    range_header: Optional[str] = Header(None, alias="Range"),
    container: ServiceContainer = Depends(get_container),
):
    return range_response(container.review_service.preview_path(job_id), range_header, "video/mp4")


# ── Thư viện ──────────────────────────────────────────────────────────────────
@router.get("/api/bilibili/library")
def list_library(q: str = "", series: Optional[int] = None, tag: str = "", status: str = "", sort: str = "newest",
                 container: ServiceContainer = Depends(get_container)):
    """Danh sách video, có tìm kiếm không dấu (q) và lọc theo series, tag, trạng thái lồng tiếng."""
    return {"items": container.library_service.list(q=q, series_id=series, tag=tag, status=status, sort=sort)}


@router.get("/api/bilibili/library/{item_id}")
def get_library_item(item_id: str, container: ServiceContainer = Depends(get_container)):
    return container.library_service.get(item_id)


@router.patch("/api/bilibili/library/{item_id}")
def update_library_item(item_id: str, body: UpdateItemRequest, container: ServiceContainer = Depends(get_container)):
    """Đổi tên, ghi chú, series, tag. Chỉ đổi thông tin, không đổi file trên đĩa."""
    return container.library_service.update(item_id, title=body.title, note=body.note, series=body.series, tags=body.tags)


@router.delete("/api/bilibili/library/{item_id}")
def delete_library_item(item_id: str, container: ServiceContainer = Depends(get_container)):
    container.library_service.delete(item_id)
    return {"deleted": item_id}


@router.get("/api/bilibili/library/{item_id}/stream")
def stream_library_item(
    item_id: str,
    kind: str = "main",
    range_header: Optional[str] = Header(None, alias="Range"),
    container: ServiceContainer = Depends(get_container),
):
    """Phát video trong trình duyệt, tua được nhờ HTTP Range. kind=source: video gốc nếu được giữ lại."""
    return range_response(container.library_service.video_path(item_id, kind), range_header, "video/mp4")


@router.get("/api/bilibili/library/{item_id}/subtitle")
def library_item_subtitle(item_id: str, kind: str = "auto", container: ServiceContainer = Depends(get_container)):
    return FileResponse(container.library_service.subtitle_path(item_id, kind), media_type="text/vtt")


@router.get("/api/bilibili/library/{item_id}/thumbnail")
def library_item_thumbnail(item_id: str, container: ServiceContainer = Depends(get_container)):
    return FileResponse(container.library_service.thumbnail_path(item_id), media_type="image/jpeg")


@router.get("/api/bilibili/library/{item_id}/download")
def download_library_item(item_id: str, kind: str = "main", container: ServiceContainer = Depends(get_container)):
    service = container.library_service
    return FileResponse(service.video_path(item_id, kind), media_type="video/mp4",
                        filename=service.download_name(item_id, kind))


# ── Series và tag ─────────────────────────────────────────────────────────────
@router.get("/api/bilibili/series")
def list_series(container: ServiceContainer = Depends(get_container)):
    return {"series": container.library_service.list_series()}


@router.patch("/api/bilibili/series/{series_id}")
def rename_series(series_id: int, body: RenameRequest, container: ServiceContainer = Depends(get_container)):
    container.library_service.rename_series(series_id, body.name)
    return {"series": container.library_service.list_series()}


@router.delete("/api/bilibili/series/{series_id}")
def delete_series(series_id: int, container: ServiceContainer = Depends(get_container)):
    """Xóa nhóm series; các video trong đó được giữ lại."""
    container.library_service.delete_series(series_id)
    return {"series": container.library_service.list_series()}


@router.get("/api/bilibili/tags")
def list_tags(container: ServiceContainer = Depends(get_container)):
    return {"tags": container.library_service.list_tags()}


@router.delete("/api/bilibili/tags/{tag_id}")
def delete_tag(tag_id: int, container: ServiceContainer = Depends(get_container)):
    container.library_service.delete_tag(tag_id)
    return {"tags": container.library_service.list_tags()}


# ── Lưu trữ ───────────────────────────────────────────────────────────────────
@router.get("/api/bilibili/storage")
def storage_usage(container: ServiceContainer = Depends(get_container)):
    return {**container.storage_service.usage(), "move": container.library_mover.status()}


@router.put("/api/bilibili/storage/root")
def change_storage_root(body: StorageRootRequest, container: ServiceContainer = Depends(get_container)):
    """Bắt đầu chuyển thư viện sang thư mục khác (chạy nền). Theo dõi bằng GET /api/bilibili/storage."""
    return container.library_mover.start(body.path)


@router.post("/api/bilibili/storage/cleanup")
def storage_cleanup(body: CleanupRequest, container: ServiceContainer = Depends(get_container)):
    return container.storage_service.cleanup(body.targets)


# ── Cài đặt mặc định ──────────────────────────────────────────────────────────
@router.get("/api/bilibili/settings")
def get_settings(container: ServiceContainer = Depends(get_container)):
    return container.app_settings.get()


@router.put("/api/bilibili/settings")
def update_settings(body: SettingsRequest, container: ServiceContainer = Depends(get_container)):
    return container.app_settings.update(body.model_dump())
