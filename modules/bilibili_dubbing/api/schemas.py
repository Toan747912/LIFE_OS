from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    urls: List[str] = Field(..., description="Danh sách link Bilibili hoặc mã BV")


class ProbeRequest(BaseModel):
    result_index: int = Field(..., ge=0, description="Vị trí của link trong kết quả quét")
    episode_id: str


class CookieRequest(BaseModel):
    text: str = Field(..., description="Nội dung cookie: file cookies.txt, JSON của extension, chuỗi header hoặc giá trị SESSDATA")
    site: str = Field("bilibili.com", description="bilibili.com hoặc bilibili.tv (dùng khi nội dung không kèm tên miền)")


class JobItem(BaseModel):
    result_index: int = Field(..., ge=0)
    episode_id: str
    format_id: str
    subtitle: str = Field("whisper", description="platform:<lang> | whisper | uploaded")


class CreateJobsRequest(BaseModel):
    scan_id: str
    items: List[JobItem]
    voice: str = "vi-VN-HoaiMyNeural"
    orig_vol: float = 0.15
    dub_vol: float = 1.0
    keep_source: bool = False


class CueEdit(BaseModel):
    idx: int
    vi_text: str = ""


class SaveCuesRequest(BaseModel):
    cues: List[CueEdit]


class UpdateItemRequest(BaseModel):
    title: Optional[str] = None
    note: Optional[str] = None
    series: Optional[str] = Field(None, description="Tên series; chuỗi rỗng = bỏ khỏi series")
    tags: Optional[List[str]] = None


class RenameRequest(BaseModel):
    name: str


class StorageRootRequest(BaseModel):
    path: str


class CleanupRequest(BaseModel):
    targets: List[str]


class SettingsRequest(BaseModel):
    default_voice: Optional[str] = None
    default_orig_vol: Optional[float] = None
    default_dub_vol: Optional[float] = None
    default_keep_source: Optional[bool] = None
    whisper_model: Optional[str] = None
