"""Các bước của pipeline. Mỗi stage chỉ biết JobContext và thư mục làm việc của job."""
from __future__ import annotations

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from modules.bilibili_dubbing.domain.enums import JobStatus, SubtitleSourceType
from modules.bilibili_dubbing.domain.errors import ScanFailed
from modules.bilibili_dubbing.domain.models import DownloadRequest, LibraryItem
from modules.bilibili_dubbing.dubbing.mixer import DubMixer
from modules.bilibili_dubbing.dubbing.synthesizer import Clip, TtsSynthesizer
from modules.bilibili_dubbing.media.ffmpeg_tools import FfmpegTools
from modules.bilibili_dubbing.pipeline.context import JobContext
from modules.bilibili_dubbing.sources.registry import SourceRegistry
from modules.bilibili_dubbing.storage.repositories import (
    CueRepository,
    JobRepository,
    LibraryRepository,
    TaxonomyRepository,
)
from modules.bilibili_dubbing.storage.storage_manager import StorageManager
from modules.bilibili_dubbing.subtitles.document import SubtitleDocument
from modules.bilibili_dubbing.subtitles.providers import SubtitleProvider, SubtitleUnavailable
from modules.bilibili_dubbing.subtitles.translator import Translator, is_vietnamese

DOWNLOAD_MARKER = "download.json"
SUBTITLE_MARKER = "subtitle.json"
TRANSLATE_MARKER = "translate.done"
REVIEW_MARKER = "review.approved"
VI_SUBTITLE_FILE = "subs.vi.vtt"
TTS_DIR = "tts"
TTS_MARKER = "tts.json"
DUBBED_FILE = "dubbed.mp4"
MIX_MARKER = "mix.json"


class PipelinePause(Exception):
    """Stage cần người dùng làm gì đó: job chuyển sang trạng thái chờ và nhường worker cho job khác."""

    def __init__(self, status: JobStatus, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


class PipelineStage(ABC):
    name: str = "stage"
    status: JobStatus = JobStatus.QUEUED
    # False: stage không tự chạy việc gì mà chỉ dừng chờ người dùng, nên pipeline không ghi trạng thái trước khi
    # gọi run(). Trạng thái chờ và thông báo được ghi cùng lúc khi stage ném PipelinePause, để không có khoảnh
    # khắc job đã hiện "chờ duyệt" mà worker vẫn đang giữ nó.
    announce: bool = True

    @abstractmethod
    def is_done(self, ctx: JobContext) -> bool:
        """Kết quả của stage đã có trên đĩa chưa (để chạy lại job không làm lại việc đã xong)."""

    @abstractmethod
    def run(self, ctx: JobContext) -> None:
        ...


class DownloadStage(PipelineStage):
    name = "download"
    status = JobStatus.DOWNLOADING

    def __init__(self, registry: SourceRegistry, storage: StorageManager, ffmpeg: FfmpegTools):
        self._registry = registry
        self._storage = storage
        self._ffmpeg = ffmpeg

    @staticmethod
    def read_marker(ctx: JobContext) -> Optional[Dict[str, Any]]:
        marker = ctx.work_dir / DOWNLOAD_MARKER
        if not marker.is_file():
            return None
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        return data if (ctx.work_dir / data.get("video", "")).is_file() else None

    def is_done(self, ctx: JobContext) -> bool:
        return self.read_marker(ctx) is not None

    def run(self, ctx: JobContext) -> None:
        spec = ctx.spec
        self._storage.ensure_free_space(spec.expected_bytes)
        ctx.report(0, "Đang kết nối tới Bilibili...", force=True)

        def on_progress(fraction: Optional[float], downloaded: int) -> None:
            megabytes = downloaded / 1048576
            percent = None if fraction is None else int(fraction * 100)
            ctx.report(percent, f"Đang tải video: {megabytes:.0f} MB")

        wants_subtitle = spec.subtitle_source == SubtitleSourceType.PLATFORM.value and spec.subtitle_lang
        result = self._registry.by_name(spec.source).download(
            DownloadRequest(
                url=spec.url, selector=spec.selector, dest_dir=ctx.work_dir,
                subtitle_lang=spec.subtitle_lang if wants_subtitle else None,
                expected_bytes=spec.expected_bytes,
            ),
            on_progress,
        )
        ctx.check_cancelled()

        probed = self._ffmpeg.probe(result.video_path)
        marker: Dict[str, Any] = {
            "video": result.video_path.name,
            "thumbnail": result.thumbnail_path.name if result.thumbnail_path else None,
            "subtitle_vtt": None,
            "duration_s": probed.get("duration_s") or result.duration_s,
            "vcodec": probed.get("vcodec"),
            "height": probed.get("height"),
        }
        if result.subtitle_path is not None:
            vtt = ctx.work_dir / "subs.orig.vtt"
            if self._ffmpeg.to_vtt(result.subtitle_path, vtt):
                marker["subtitle_vtt"] = vtt.name
        # Ghi marker sau cùng: có marker nghĩa là stage đã xong trọn vẹn.
        (ctx.work_dir / DOWNLOAD_MARKER).write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
        ctx.report(100, "Đã tải xong video.", force=True)


class SubtitleStage(PipelineStage):
    """Lấy phụ đề gốc từ nguồn người dùng đã chọn và lưu từng câu vào bảng `cues`."""

    name = "subtitle"
    status = JobStatus.PREPARING_SUBS

    def __init__(self, providers: Dict[str, SubtitleProvider], cues: CueRepository):
        self._providers = providers
        self._cues = cues

    @staticmethod
    def read_marker(ctx: JobContext) -> Optional[Dict[str, Any]]:
        marker = ctx.work_dir / SUBTITLE_MARKER
        try:
            return json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None
        except (OSError, ValueError):
            return None

    def is_done(self, ctx: JobContext) -> bool:
        return self.read_marker(ctx) is not None and self._cues.count(ctx.job.id) > 0

    def run(self, ctx: JobContext) -> None:
        download = DownloadStage.read_marker(ctx)
        if download is None:
            raise ScanFailed("Không tìm thấy video đã tải để lấy phụ đề.")
        spec = ctx.spec
        provider = self._providers.get(spec.subtitle_source)
        if provider is None:
            raise ScanFailed(f"Nguồn phụ đề không được hỗ trợ: {spec.subtitle_source}")
        ctx.report(0, "Đang lấy phụ đề gốc...", force=True)
        try:
            result = provider.obtain(
                ctx.work_dir, ctx.work_dir / download["video"], spec.subtitle_lang,
                lambda message: ctx.report(5, message, force=True),
            )
        except SubtitleUnavailable as exc:
            raise PipelinePause(JobStatus.AWAITING_SUBTITLE, exc.message) from exc
        ctx.check_cancelled()
        self._cues.replace_all(ctx.job.id, result.document.cues)
        (ctx.work_dir / TRANSLATE_MARKER).unlink(missing_ok=True)
        (ctx.work_dir / REVIEW_MARKER).unlink(missing_ok=True)
        (ctx.work_dir / SUBTITLE_MARKER).write_text(json.dumps({
            "source": spec.subtitle_source, "lang": result.source_lang, "count": len(result.document),
            "note": result.note,
        }, ensure_ascii=False), encoding="utf-8")
        ctx.report(100, f"Đã có {len(result.document)} câu phụ đề gốc.", force=True)


class TranslateStage(PipelineStage):
    """Dịch sang tiếng Việt. Phụ đề gốc đã là tiếng Việt thì dùng luôn, không dịch."""

    name = "translate"
    status = JobStatus.TRANSLATING

    def __init__(self, translator: Translator, cues: CueRepository):
        self._translator = translator
        self._cues = cues

    def is_done(self, ctx: JobContext) -> bool:
        return (ctx.work_dir / TRANSLATE_MARKER).is_file()

    def run(self, ctx: JobContext) -> None:
        marker = SubtitleStage.read_marker(ctx) or {}
        cues = self._cues.list(ctx.job.id)
        if is_vietnamese(marker.get("lang")):
            self._cues.set_translations(ctx.job.id, {c.idx: c.source_text for c in cues})
            message = "Phụ đề gốc đã là tiếng Việt, không cần dịch."
        else:
            ctx.report(0, f"Đang dịch {len(cues)} câu sang tiếng Việt...", force=True)
            texts = self._translator.translate_batch(
                [c.source_text for c in cues], marker.get("lang"),
                lambda done, total: ctx.report(int(done * 100 / max(total, 1)), f"Đang dịch: {done}/{total} câu"),
            )
            ctx.check_cancelled()
            self._cues.set_translations(ctx.job.id, {c.idx: text for c, text in zip(cues, texts)})
            missing = sum(1 for text in texts if not text)
            message = f"Đã dịch {len(cues) - missing}/{len(cues)} câu." + (
                f" {missing} câu chưa dịch được, cần bạn điền." if missing else "")
        (ctx.work_dir / TRANSLATE_MARKER).write_text("ok", encoding="utf-8")
        ctx.report(100, message, force=True)


class ReviewStage(PipelineStage):
    """Điểm dừng duy nhất của pipeline: chờ người dùng xem và sửa bản dịch."""

    name = "review"
    status = JobStatus.AWAITING_REVIEW
    announce = False

    def __init__(self, cues: CueRepository):
        self._cues = cues

    def is_done(self, ctx: JobContext) -> bool:
        return (ctx.work_dir / REVIEW_MARKER).is_file() and (ctx.work_dir / VI_SUBTITLE_FILE).is_file()

    def run(self, ctx: JobContext) -> None:
        cues = self._cues.list(ctx.job.id)
        missing = sum(1 for cue in cues if not cue.vi_text.strip())
        message = f"Chờ bạn duyệt {len(cues)} câu phụ đề tiếng Việt."
        if missing:
            message += f" {missing} câu chưa dịch được, cần bạn điền."
        note = (SubtitleStage.read_marker(ctx) or {}).get("note")
        if note:
            message += " " + note
        raise PipelinePause(JobStatus.AWAITING_REVIEW, message)


class SynthesizeStage(PipelineStage):
    """Sinh giọng đọc tiếng Việt cho từng câu đã duyệt."""

    name = "synthesize"
    status = JobStatus.SYNTHESIZING

    def __init__(self, synthesizer: TtsSynthesizer, cues: CueRepository):
        self._synthesizer = synthesizer
        self._cues = cues

    @staticmethod
    def read_clips(ctx: JobContext) -> Optional[list]:
        marker = ctx.work_dir / TTS_MARKER
        try:
            data = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None
        except (OSError, ValueError):
            return None
        if not data or data.get("voice") != ctx.spec.voice:
            return None
        clips = [Clip(**item) for item in data.get("clips", [])]
        if not clips or not all((ctx.work_dir / TTS_DIR / clip.audio_file).is_file() for clip in clips):
            return None
        return clips

    def is_done(self, ctx: JobContext) -> bool:
        return self.read_clips(ctx) is not None

    def run(self, ctx: JobContext) -> None:
        cues = [cue for cue in self._cues.list(ctx.job.id) if cue.vi_text.strip()]
        if not cues:
            raise ScanFailed("Không có câu tiếng Việt nào để lồng tiếng.")
        ctx.report(0, f"Đang sinh giọng đọc cho {len(cues)} câu...", force=True)
        clips = self._synthesizer.synthesize(
            cues, ctx.spec.voice, ctx.work_dir / TTS_DIR,
            on_progress=lambda done, total: ctx.report(int(done * 100 / max(total, 1)),
                                                       f"Đang sinh giọng đọc: {done}/{total} câu"),
            should_stop=ctx.check_cancelled,
        )
        ctx.check_cancelled()
        (ctx.work_dir / MIX_MARKER).unlink(missing_ok=True)
        (ctx.work_dir / TTS_MARKER).write_text(json.dumps({
            "voice": ctx.spec.voice, "clips": [clip.__dict__ for clip in clips],
        }, ensure_ascii=False), encoding="utf-8")
        sped_up = sum(1 for clip in clips if clip.rate != "+0%")
        ctx.report(100, f"Đã sinh giọng cho {len(clips)} câu ({sped_up} câu phải đọc nhanh hơn để kịp khung).", force=True)


class MixStage(PipelineStage):
    """Trộn giọng Việt đè lên tiếng gốc (giữ nhỏ làm nền) và nhúng phụ đề mềm."""

    name = "mix"
    status = JobStatus.MIXING

    def __init__(self, mixer: DubMixer, ffmpeg: FfmpegTools):
        self._mixer = mixer
        self._ffmpeg = ffmpeg

    @staticmethod
    def read_marker(ctx: JobContext) -> Optional[Dict[str, Any]]:
        marker = ctx.work_dir / MIX_MARKER
        try:
            data = json.loads(marker.read_text(encoding="utf-8")) if marker.is_file() else None
        except (OSError, ValueError):
            return None
        return data if data and (ctx.work_dir / DUBBED_FILE).is_file() else None

    def is_done(self, ctx: JobContext) -> bool:
        return self.read_marker(ctx) is not None

    def run(self, ctx: JobContext) -> None:
        download = DownloadStage.read_marker(ctx)
        clips = SynthesizeStage.read_clips(ctx)
        if download is None or clips is None:
            raise ScanFailed("Thiếu video gốc hoặc giọng đọc để trộn.")
        ctx.report(10, "FFmpeg đang trộn giọng lồng tiếng vào video...", force=True)
        output = self._mixer.mix(
            video_path=ctx.work_dir / download["video"], clips=clips, audio_dir=ctx.work_dir / TTS_DIR,
            subtitle_path=ctx.work_dir / VI_SUBTITLE_FILE, output_path=ctx.work_dir / DUBBED_FILE,
            orig_vol=ctx.spec.orig_vol, dub_vol=ctx.spec.dub_vol,
        )
        probed = self._ffmpeg.probe(output)
        (ctx.work_dir / MIX_MARKER).write_text(json.dumps({
            "duration_s": probed.get("duration_s"), "vcodec": probed.get("vcodec"), "clips": len(clips),
        }), encoding="utf-8")
        ctx.report(100, "Đã trộn xong video lồng tiếng.", force=True)


class PublishStage(PipelineStage):
    """Đưa kết quả vào thư viện: video đã lồng tiếng, phụ đề, ảnh thu nhỏ, và video gốc nếu người dùng muốn giữ."""

    name = "publish"
    status = JobStatus.PUBLISHING

    def __init__(self, storage: StorageManager, library: LibraryRepository, jobs: JobRepository,
                 taxonomy: Optional[TaxonomyRepository] = None):
        self._storage = storage
        self._library = library
        self._jobs = jobs
        self._taxonomy = taxonomy

    def is_done(self, ctx: JobContext) -> bool:
        return bool(ctx.job.item_id)

    def run(self, ctx: JobContext) -> None:
        marker = DownloadStage.read_marker(ctx)
        if marker is None:
            raise ScanFailed("Không tìm thấy video đã tải để đưa vào thư viện.")
        ctx.report(0, "Đang đưa video vào thư viện...", force=True)
        spec = ctx.spec
        item_id = "it_" + uuid.uuid4().hex[:12]
        moved = []      # (tên trong thư viện, đường dẫn gốc) để hoàn tác nếu lỗi

        def move(work_name: Optional[str], library_name: str) -> Optional[str]:
            if not work_name or not (ctx.work_dir / work_name).is_file():
                return None
            self._storage.move_into_item(ctx.work_dir / work_name, item_id, library_name)
            moved.append((library_name, ctx.work_dir / work_name))
            return library_name

        try:
            mixed = MixStage.read_marker(ctx)
            source_rel = None
            if mixed is not None:
                video_rel = move(DUBBED_FILE, "video.mp4")
                if spec.keep_source:
                    source_rel = move(marker["video"], "source.mp4")
            else:                                   # không có bản lồng tiếng: video gốc là sản phẩm
                video_rel = move(marker["video"], "video.mp4")
            sub_vi_rel = move(VI_SUBTITLE_FILE, VI_SUBTITLE_FILE)
            thumb_rel = move(marker.get("thumbnail"), "thumb.jpg")
            sub_rel = move(marker.get("subtitle_vtt"), "subs.orig.vtt")
            item = LibraryItem(
                id=item_id,
                title=spec.title,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                # Tập thuộc playlist/series được xếp sẵn vào series cùng tên.
                series_id=(self._taxonomy.get_or_create_series(spec.series_title[:80])
                           if self._taxonomy and spec.series_title else None),
                source_url=spec.url,
                episode_label=spec.episode_label,
                duration_s=(mixed or {}).get("duration_s") or marker.get("duration_s"),
                quality=spec.quality_label,
                voice=spec.voice if mixed is not None else None,
                source_rel=source_rel,
                video_rel=video_rel,
                sub_vi_rel=sub_vi_rel,
                sub_orig_rel=sub_rel,
                sub_orig_lang=spec.subtitle_lang if sub_rel else None,
                thumb_rel=thumb_rel,
                size_bytes=self._storage.dir_size(self._storage.item_dir(item_id)),
                dubbed=mixed is not None,
                codec=(mixed or {}).get("vcodec") or marker.get("vcodec") or spec.codec,
                browser_playable=spec.browser_playable,
            )
            self._library.create(item)
        except Exception:
            # Trả mọi file đã chuyển về thư mục làm việc để bấm Chạy lại không mất video đã tải.
            for library_name, original in reversed(moved):
                try:
                    self._storage.move_back(item_id, library_name, original)
                except OSError:
                    pass
            self._storage.remove_item_dir(item_id)
            raise
        self._jobs.update(ctx.job.id, item_id=item_id)
        ctx.job.item_id = item_id
        self._storage.remove_job_dir(ctx.job.id)
