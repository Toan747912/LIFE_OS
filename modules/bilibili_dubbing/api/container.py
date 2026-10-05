"""Khởi tạo và nối các đối tượng của module (dependency injection thủ công)."""
from __future__ import annotations

import threading
from typing import Any, Dict, Optional

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.media.ffmpeg_tools import FfmpegTools
from modules.bilibili_dubbing.pipeline.job_service import JobService
from modules.bilibili_dubbing.pipeline.pipeline import DubbingPipeline
from modules.bilibili_dubbing.pipeline.runner import JobRunner
from modules.bilibili_dubbing.domain.enums import SubtitleSourceType
from modules.bilibili_dubbing.dubbing.mixer import DubMixer, MixFn
from modules.bilibili_dubbing.dubbing.synthesizer import SpeakFn, TtsSynthesizer
from modules.bilibili_dubbing.pipeline.review_service import ReviewService
from modules.bilibili_dubbing.pipeline.stages import (
    DownloadStage,
    MixStage,
    PublishStage,
    ReviewStage,
    SubtitleStage,
    SynthesizeStage,
    TranslateStage,
)
from modules.bilibili_dubbing.sources.bilibili import BilibiliSource
from modules.bilibili_dubbing.sources.registry import SourceRegistry
from modules.bilibili_dubbing.sources.scan_service import ScanService
from modules.bilibili_dubbing.storage.cookie_checker import CookieChecker, FetchFn
from modules.bilibili_dubbing.storage.cookie_store import CookieStore
from modules.bilibili_dubbing.storage.database import Database
from modules.bilibili_dubbing.storage.library_mover import LibraryMover
from modules.bilibili_dubbing.storage.library_service import LibraryService
from modules.bilibili_dubbing.storage.repositories import (
    CueRepository,
    JobRepository,
    LibraryRepository,
    ScanRepository,
    SettingsRepository,
    TaxonomyRepository,
)
from modules.bilibili_dubbing.storage.settings_service import AppSettingsService
from modules.bilibili_dubbing.storage.storage_manager import StorageManager
from modules.bilibili_dubbing.storage.storage_service import StorageService
from modules.bilibili_dubbing.subtitles.providers import (
    PlatformSubtitleProvider,
    Transcriber,
    UploadedSubtitleProvider,
    WhisperSubtitleProvider,
)
from modules.bilibili_dubbing.subtitles.translator import GoogleTranslatorAdapter, Translator


class ServiceContainer:
    def __init__(self, settings: Optional[BilibiliSettings] = None, registry: Optional[SourceRegistry] = None,
                 translator: Optional[Translator] = None, transcriber: Optional[Transcriber] = None,
                 speak: Optional[SpeakFn] = None, mix: Optional[MixFn] = None,
                 cookie_fetch: Optional[FetchFn] = None):
        self.settings = settings or BilibiliSettings()
        self.settings.ensure_dirs()
        self.database = Database(self.settings.db_path)
        self.settings_repo = SettingsRepository(self.database)
        self.scan_repo = ScanRepository(self.database)
        self.cookie_store = CookieStore(self.settings.cookie_path)
        self.cookie_checker = CookieChecker(self.settings.cookie_path, fetch=cookie_fetch)
        self.registry = registry or SourceRegistry([
            BilibiliSource(
                cookie_path=self.settings.cookie_path,
                socket_timeout_s=self.settings.socket_timeout_s,
            ),
        ])
        self.scan_service = ScanService(
            registry=self.registry,
            scans=self.scan_repo,
            cookie_path=self.settings.cookie_path,
            max_urls=self.settings.max_urls_per_scan,
            max_probe=self.settings.max_probe_per_source,
        )

        self.job_repo = JobRepository(self.database)
        self.library_repo = LibraryRepository(self.database)
        self.storage = StorageManager(self.settings, self.settings_repo)
        self.ffmpeg = FfmpegTools()
        self.cue_repo = CueRepository(self.database)
        self.taxonomy_repo = TaxonomyRepository(self.database)
        self.translator = translator or GoogleTranslatorAdapter()
        self.subtitle_providers = {
            SubtitleSourceType.PLATFORM.value: PlatformSubtitleProvider(),
            SubtitleSourceType.UPLOADED.value: UploadedSubtitleProvider(),
            SubtitleSourceType.WHISPER.value: WhisperSubtitleProvider(
                model_size=lambda: self.settings_repo.get("whisper_model", self.settings.default_whisper_model),
                transcriber=transcriber,
            ),
        }
        self.synthesizer = TtsSynthesizer(measure=self.ffmpeg.duration_ms, speak=speak,
                                          retry_wait_s=self.settings.tts_retry_wait_s)
        self.mixer = DubMixer(mix=mix)
        self.pipeline = DubbingPipeline(
            stages=[
                DownloadStage(self.registry, self.storage, self.ffmpeg),
                SubtitleStage(self.subtitle_providers, self.cue_repo),
                TranslateStage(self.translator, self.cue_repo),
                ReviewStage(self.cue_repo),
                SynthesizeStage(self.synthesizer, self.cue_repo),
                MixStage(self.mixer, self.ffmpeg),
                PublishStage(self.storage, self.library_repo, self.job_repo, self.taxonomy_repo),
            ],
            jobs=self.job_repo,
            storage=self.storage,
        )
        self.runner = JobRunner(self.pipeline, self.job_repo)
        self.job_service = JobService(
            jobs=self.job_repo, scans=self.scan_repo, runner=self.runner, storage=self.storage,
            max_jobs_per_request=self.settings.max_jobs_per_request,
        )
        self.library_service = LibraryService(self.library_repo, self.storage, self.taxonomy_repo)
        self.storage_service = StorageService(self.storage, self.library_repo, self.job_repo)
        self.library_mover = LibraryMover(self.settings, self.storage, self.library_repo, self.settings_repo,
                                          pause_jobs=self.runner.pause, resume_jobs=self.runner.resume)
        self.app_settings = AppSettingsService(self.settings_repo, self.settings)
        self.review_service = ReviewService(self.job_repo, self.cue_repo, self.runner, self.storage)
        self.runner.start()   # tiếp tục các job dang dở từ lần chạy trước

    def health(self) -> Dict[str, Any]:
        """Tình trạng các phụ thuộc bên ngoài, để giao diện báo sớm thay vì để job thất bại giữa chừng."""
        import importlib.util

        def installed(module: str) -> bool:
            try:
                return importlib.util.find_spec(module) is not None
            except (ImportError, ValueError):
                return False

        try:
            import yt_dlp
            ytdlp_version: Optional[str] = yt_dlp.version.__version__
        except ImportError:
            ytdlp_version = None
        return {
            "yt_dlp": ytdlp_version,
            "ffmpeg": self.ffmpeg.available(),
            "edge_tts": installed("edge_tts"),
            "deep_translator": installed("deep_translator"),
            "faster_whisper": installed("faster_whisper"),
            "cookie_configured": self.settings.cookie_path.is_file(),
            "schema_version": self.database.schema_version(),
        }


_container: Optional[ServiceContainer] = None
_lock = threading.Lock()


def get_container() -> ServiceContainer:
    """Tạo container ở lần gọi đầu tiên, để việc import module không tạo file hay thư mục nào."""
    global _container
    if _container is None:
        with _lock:
            if _container is None:
                _container = ServiceContainer()
    return _container


def set_container(container: Optional[ServiceContainer]) -> None:
    """Dùng cho test: thay container thật bằng container có nguồn giả."""
    global _container
    with _lock:
        if _container is not None and _container is not container:
            _container.runner.stop()
        _container = container
