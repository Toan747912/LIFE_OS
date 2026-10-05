"""Kiểm thử trọn luồng giai đoạn 2: tạo job -> tải -> thư viện -> phát / tải xuống / xóa."""
import tempfile
import time
import unittest
from pathlib import Path

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.sources.registry import SourceRegistry
from modules.bilibili_dubbing.tests import fakes
from modules.bilibili_dubbing.tests.support import FlowTestCase


class JobFlowTest(FlowTestCase):
    # ── Luồng chính ───────────────────────────────────────────────────────────
    def test_download_publish_play_download_delete(self):
        response = self.create(self.scan())
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()["jobs"][0]
        self.assertEqual(job["status"], "QUEUED")
        done = self.run_to_done(job["id"])
        self.assertEqual(done["progress"], 100)

        request = self.source.requests[0]
        self.assertEqual((request.selector, request.subtitle_lang), ("30080+bestaudio", "zh-CN"))

        items = self.client.get("/api/bilibili/library").json()["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["id"], done["item_id"])
        self.assertEqual((item["duration_s"], item["dubbed"], item["has_video"], item["has_sub_orig"], item["has_sub_vi"]),
                         (2, True, True, True, True))
        self.assertEqual((item["quality"], item["sub_orig_lang"], item["codec"]), ("1080p · AVC", "zh-CN", "h264"))
        self.assertGreater(item["size_bytes"], 1000)
        self.assertNotIn("video_rel", item)                      # không lộ đường dẫn trên đĩa

        base = f"/api/bilibili/library/{item['id']}"
        full = self.client.get(base + "/stream")
        self.assertEqual((full.status_code, full.headers["accept-ranges"]), (200, "bytes"))
        size = len(full.content)
        self.assertEqual(int(full.headers["content-length"]), size)

        part = self.client.get(base + "/stream", headers={"Range": "bytes=10-19"})
        self.assertEqual(part.status_code, 206)
        self.assertEqual(part.headers["content-range"], f"bytes 10-19/{size}")
        self.assertEqual(part.content, full.content[10:20])
        tail = self.client.get(base + "/stream", headers={"Range": "bytes=-5"})
        self.assertEqual(tail.content, full.content[-5:])
        open_end = self.client.get(base + "/stream", headers={"Range": f"bytes={size - 3}-"})
        self.assertEqual(open_end.content, full.content[-3:])
        self.assertEqual(self.client.get(base + "/stream", headers={"Range": f"bytes={size}-"}).status_code, 416)

        subtitle = self.client.get(base + "/subtitle")                 # mặc định: bản tiếng Việt đã duyệt
        self.assertEqual(subtitle.status_code, 200)
        self.assertTrue(subtitle.text.startswith("WEBVTT"))
        self.assertIn("[vi] Xin chào", subtitle.text)
        original = self.client.get(base + "/subtitle?kind=orig")
        self.assertIn("Xin chào", original.text)
        self.assertNotIn("[vi]", original.text)

        download = self.client.get(base + "/download")
        self.assertEqual(download.content, full.content)
        self.assertIn("attachment", download.headers["content-disposition"])

        # thư mục làm việc đã được dọn, file nằm trong thư viện
        self.assertFalse((self.data_dir / "work" / job["id"]).exists())
        self.assertTrue((self.data_dir / "library" / item["id"] / "video.mp4").is_file())

        self.assertEqual(self.client.delete(base).status_code, 200)
        self.assertFalse((self.data_dir / "library" / item["id"]).exists())
        self.assertEqual(self.client.get(base).status_code, 404)
        self.assertEqual(self.client.get(base + "/stream").status_code, 404)

    def test_whisper_choice_does_not_request_platform_subtitle(self):
        job = self.create(self.scan(), subtitle="whisper").json()["jobs"][0]
        self.run_to_done(job["id"])
        self.assertIsNone(self.source.requests[0].subtitle_lang)
        item = self.client.get("/api/bilibili/library").json()["items"][0]
        self.assertEqual((item["has_sub_orig"], item["has_sub_vi"]), (False, True))
        self.assertEqual(self.client.get(f"/api/bilibili/library/{item['id']}/subtitle?kind=orig").status_code, 404)

    # ── Lỗi, chạy lại, hủy, xóa ───────────────────────────────────────────────
    def test_failed_job_can_be_retried(self):
        self.source.fail_times = 1
        job = self.create(self.scan()).json()["jobs"][0]
        failed = self.wait_for(job["id"], {"FAILED", "DONE"})
        self.assertEqual(failed["status"], "FAILED")
        self.assertIn("kiểm tra mạng", failed["error"])
        self.assertEqual(self.client.get("/api/bilibili/library").json()["items"], [])

        retried = self.client.post(f"/api/bilibili/jobs/{job['id']}/retry")
        self.assertEqual(retried.status_code, 200)
        self.run_to_done(job["id"])
        self.assertEqual(len(self.client.get("/api/bilibili/library").json()["items"]), 1)
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job['id']}/retry").status_code, 409)

    def test_cancel_running_and_queued_jobs_then_delete(self):
        import threading

        self.source.gate = threading.Event()
        scan = self.scan()
        first = self.create(scan).json()["jobs"][0]
        second = self.create(scan).json()["jobs"][0]
        self.assertTrue(self.source.started.wait(5))
        self.wait_for(first["id"], {"DOWNLOADING"})
        self.assertEqual(self.client.get(f"/api/bilibili/jobs/{second['id']}").json()["status"], "QUEUED")

        # job đang chạy không xóa được khi chưa hủy
        self.assertEqual(self.client.delete(f"/api/bilibili/jobs/{first['id']}").status_code, 409)

        cancelled_queued = self.client.post(f"/api/bilibili/jobs/{second['id']}/cancel").json()
        self.assertEqual(cancelled_queued["status"], "CANCELLED")
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{first['id']}/cancel").status_code, 200)
        self.assertEqual(self.wait_for(first["id"], {"CANCELLED", "DONE", "FAILED"})["status"], "CANCELLED")
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{first['id']}/cancel").status_code, 409)

        # job đã hủy khi đang chờ không được worker chạy nữa
        time.sleep(0.3)
        self.assertEqual(self.client.get(f"/api/bilibili/jobs/{second['id']}").json()["status"], "CANCELLED")
        self.assertEqual(len(self.source.requests), 1)

        self.assertEqual(self.client.delete(f"/api/bilibili/jobs/{first['id']}").status_code, 200)
        self.assertFalse((self.data_dir / "work" / first["id"]).exists())
        self.assertEqual(self.client.get(f"/api/bilibili/jobs/{first['id']}").status_code, 404)
        self.assertEqual(len(self.client.get("/api/bilibili/jobs").json()["jobs"]), 1)

    def test_jobs_run_one_at_a_time_in_order(self):
        scan = self.scan(fakes.SERIES_URL)
        self.client.post(f"/api/bilibili/scan/{scan['scan_id']}/probe", json={"result_index": 0, "episode_id": "p3"})
        body = {"scan_id": scan["scan_id"], "items": [
            {"result_index": 0, "episode_id": "p1", "format_id": "30080", "subtitle": "whisper"},
            {"result_index": 0, "episode_id": "p3", "format_id": "30032", "subtitle": "whisper"}]}
        jobs = self.client.post("/api/bilibili/jobs", json=body).json()["jobs"]
        self.assertEqual([j["episode_label"] for j in jobs], ["Tập 1", "Tập 3"])
        self.assertEqual(jobs[0]["series_title"], "Series mẫu")
        # Job 1 dừng chờ duyệt thì worker chuyển sang job 2, không đứng chờ.
        for job in jobs:
            self.assertEqual(self.wait_for(job["id"], {"AWAITING_REVIEW", "FAILED"})["status"], "AWAITING_REVIEW")
        for job in jobs:
            self.run_to_done(job["id"])
        self.assertEqual([r.url[-4:] for r in self.source.requests], ["?p=1", "?p=3"])
        self.assertEqual([r.selector for r in self.source.requests], ["30080+bestaudio", "30032+bestaudio"])

    # ── Kiểm tra đầu vào ──────────────────────────────────────────────────────
    def test_rejects_invalid_selections(self):
        scan = self.scan(fakes.SERIES_URL)
        cases = [
            self.create(scan, format_id="khong-co"),                       # chất lượng không có trong kết quả quét
            self.create(scan, subtitle="platform:xx"),                     # phụ đề không có
            self.create(scan, subtitle="lung-tung"),                       # nguồn phụ đề lạ
            self.create(scan, episode_id="p2"),                            # tập không truy cập được (VIP)
            self.create(scan, episode_id="p3"),                            # tập chưa quét chi tiết
            self.create(scan, voice="en-US-Bad"),
            self.create(scan, orig_vol=5),
            self.client.post("/api/bilibili/jobs", json={"scan_id": scan["scan_id"], "items": []}),
        ]
        self.assertEqual([c.status_code for c in cases], [400] * len(cases), [c.text for c in cases])
        self.assertEqual(self.create({"scan_id": "sc_khong_co"}).status_code, 404)
        duplicate = {"scan_id": scan["scan_id"], "items": [
            {"result_index": 0, "episode_id": "p1", "format_id": "30080"}] * 2}
        self.assertEqual(self.client.post("/api/bilibili/jobs", json=duplicate).status_code, 400)
        self.assertEqual(self.client.get("/api/bilibili/jobs").json()["jobs"], [])

    def test_refuses_when_disk_space_is_low(self):
        low = BilibiliSettings(data_dir=self.data_dir, min_free_bytes=10 ** 18, max_probe_per_source=2)
        container = self.new_container(settings=low)
        self.container_module.set_container(container)
        job = self.create(self.scan()).json()["jobs"][0]
        failed = self.wait_for(job["id"], {"FAILED", "DONE"})
        self.assertEqual(failed["status"], "FAILED")
        self.assertIn("MB", failed["error"])
        self.assertEqual(self.source.requests, [])

    # ── Khởi động lại server ──────────────────────────────────────────────────
    def test_interrupted_job_resumes_after_restart(self):
        import threading

        self.source.gate = threading.Event()
        job = self.create(self.scan()).json()["jobs"][0]
        self.wait_for(job["id"], {"DOWNLOADING"})
        # Giả lập tiến trình bị tắt đột ngột: bỏ container cũ mà không cập nhật DB.
        self.container.runner.stop(timeout=0.2)
        stuck = self.client.get(f"/api/bilibili/jobs/{job['id']}").json()
        self.assertEqual(stuck["status"], "DOWNLOADING")

        fresh_source = fakes.FakeDownloadSource()
        restarted = self.new_container(source=fresh_source)
        self.container_module._container = restarted            # không gọi stop() lên worker cũ đang kẹt
        # Worker cũ vẫn còn sống trong test (ngoài đời tiến trình chết thì nó chết theo):
        # cho nó dừng êm và không ghi gì vào DB nữa.
        old_worker = self.container.runner._thread
        self.container.job_repo.update = lambda *args, **kwargs: None
        self.container.runner._cancel_events[job["id"]].set()
        self.source.gate.set()
        old_worker.join(5)
        self.assertFalse(old_worker.is_alive())
        self.run_to_done(job["id"])
        self.assertEqual(len(fresh_source.requests), 1)


class CancelRaceTest(FlowTestCase):
    def test_cancel_arriving_just_as_job_pauses_is_not_lost(self):
        """Hủy đúng lúc pipeline vừa ghi trạng thái chờ nhưng worker chưa kịp nhả job: job vẫn phải thành CANCELLED."""
        import threading

        from modules.bilibili_dubbing.domain.enums import JobStatus

        paused, release = threading.Event(), threading.Event()
        jobs = self.container.job_repo

        def run_then_linger(job, cancel_event):
            jobs.update(job.id, status=JobStatus.AWAITING_REVIEW, message="Chờ bạn duyệt.")
            paused.set()
            release.wait(5)                     # worker vẫn đang "giữ" job dù trạng thái đã là chờ

        self.container.pipeline.run = run_then_linger
        job = self.create(self.scan()).json()["jobs"][0]
        self.assertTrue(paused.wait(5))
        self.assertEqual(self.job(job["id"])["status"], "AWAITING_REVIEW")
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job['id']}/cancel").status_code, 200)
        release.set()
        self.assertEqual(self.wait_for(job["id"], {"CANCELLED"}, timeout=5)["status"], "CANCELLED")
        self.assertEqual(self.client.delete(f"/api/bilibili/jobs/{job['id']}").status_code, 200)

    def test_late_cancel_flag_does_not_touch_a_finished_job(self):
        import threading

        from modules.bilibili_dubbing.domain.enums import JobStatus

        finished, release = threading.Event(), threading.Event()
        jobs = self.container.job_repo

        def finish_then_linger(job, cancel_event):
            jobs.update(job.id, status=JobStatus.DONE, message="Hoàn tất.")
            cancel_event.set()                  # cờ hủy bật sau khi job đã xong
            finished.set()
            release.wait(5)

        self.container.pipeline.run = finish_then_linger
        job = self.create(self.scan()).json()["jobs"][0]
        self.assertTrue(finished.wait(5))
        release.set()
        import time
        time.sleep(0.3)
        self.assertEqual(self.job(job["id"])["status"], "DONE")


class StorageManagerSafetyTest(unittest.TestCase):
    def setUp(self):
        from modules.bilibili_dubbing.storage.database import Database
        from modules.bilibili_dubbing.storage.repositories import SettingsRepository
        from modules.bilibili_dubbing.storage.storage_manager import StorageManager

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)
        settings = BilibiliSettings(data_dir=self.root / "data")
        settings.ensure_dirs()
        self.repo = SettingsRepository(Database(settings.db_path))
        self.storage = StorageManager(settings, self.repo)

    def test_rejects_names_that_escape_the_roots(self):
        from modules.bilibili_dubbing.domain.errors import UnsafePath

        for name in ("..", ".", "", "a/b", "a\\b", "../x", "C:evil"):
            with self.assertRaises(UnsafePath, msg=name):
                self.storage.job_dir(name)
            with self.assertRaises(UnsafePath, msg=name):
                self.storage.remove_item_dir(name)

    def test_item_file_cannot_leave_item_dir(self):
        from modules.bilibili_dubbing.domain.errors import NotFound, UnsafePath

        outside = self.root / "bi_mat.txt"
        outside.write_text("x")
        self.storage.item_dir("it_1")
        with self.assertRaises(UnsafePath):
            self.storage.item_file("it_1", "../../../bi_mat.txt")
        with self.assertRaises(NotFound):
            self.storage.item_file("it_1", "khong_co.mp4")
        with self.assertRaises(NotFound):
            self.storage.item_file("it_1", None)

    def test_move_only_from_work_dir_and_remove_only_inside_roots(self):
        from modules.bilibili_dubbing.domain.errors import UnsafePath

        outside = self.root / "ngoai.mp4"
        outside.write_text("x")
        with self.assertRaises(UnsafePath):
            self.storage.move_into_item(outside, "it_1", "video.mp4")
        self.assertTrue(outside.exists())

        inside = self.storage.job_dir("job_1") / "source.mp4"
        inside.write_text("video")
        with self.assertRaises(UnsafePath):
            self.storage.move_into_item(inside, "it_1", "../video.mp4")
        self.assertEqual(self.storage.move_into_item(inside, "it_1", "video.mp4"), "video.mp4")
        self.assertEqual(self.storage.item_file("it_1", "video.mp4").read_text(), "video")

        self.storage.remove_item_dir("it_1")
        self.storage.remove_job_dir("job_1")
        self.assertFalse((self.storage.library_root / "it_1").exists())
        self.assertTrue(outside.exists())
        self.storage.remove_item_dir("khong_ton_tai")           # không lỗi

    def test_library_root_follows_setting(self):
        from modules.bilibili_dubbing.storage.storage_manager import LIBRARY_ROOT_KEY

        custom = self.root / "o_khac"
        self.repo.set(LIBRARY_ROOT_KEY, str(custom))
        self.assertEqual(self.storage.library_root, custom.resolve())
        self.assertEqual(self.storage.item_dir("it_9").parent, custom.resolve())


class DownloadOptionsTest(unittest.TestCase):
    def test_options_match_user_selection(self):
        from modules.bilibili_dubbing.domain.models import DownloadRequest
        from modules.bilibili_dubbing.sources.bilibili import BilibiliSource

        with tempfile.TemporaryDirectory() as tmp:
            cookie = Path(tmp) / "cookies.txt"
            cookie.write_text("# Netscape HTTP Cookie File\n")
            source = BilibiliSource(cookie_path=cookie)
            request = DownloadRequest(url="u", selector="30080+bestaudio", dest_dir=Path(tmp) / "job", subtitle_lang="vi")
            options = source.build_download_options(request, lambda event: None)
            self.assertEqual(options["format"], "30080+bestaudio")
            self.assertTrue(options["outtmpl"].endswith("source.%(ext)s"))
            self.assertEqual((options["merge_output_format"], options["noplaylist"]), ("mp4", True))
            self.assertEqual((options["writesubtitles"], options["subtitleslangs"]), (True, ["vi"]))
            self.assertEqual(options["cookiefile"], str(cookie))

            plain = BilibiliSource().build_download_options(
                DownloadRequest(url="u", selector="x", dest_dir=Path(tmp)), lambda event: None)
            self.assertNotIn("writesubtitles", plain)
            self.assertNotIn("cookiefile", plain)

    def test_real_ytdlp_accepts_the_options(self):
        """Dựng YoutubeDL thật với bộ tùy chọn (không gọi mạng) để bắt lỗi sai tên tùy chọn hay postprocessor."""
        try:
            import yt_dlp
        except ImportError:
            self.skipTest("chưa cài yt-dlp")
        from modules.bilibili_dubbing.domain.models import DownloadRequest
        from modules.bilibili_dubbing.sources.bilibili import BilibiliSource

        with tempfile.TemporaryDirectory() as tmp:
            request = DownloadRequest(url="u", selector="30080+bestaudio", dest_dir=Path(tmp), subtitle_lang="vi")
            options = BilibiliSource().build_download_options(request, lambda event: None)
            with yt_dlp.YoutubeDL(options) as ydl:
                selector = ydl.build_format_selector(options["format"])
                self.assertTrue(callable(selector))
                names = [type(pp).__name__ for group in ydl._pps.values() for pp in group]
                self.assertIn("FFmpegThumbnailsConvertorPP", names)

    def test_finds_outputs_and_ignores_partial_files(self):
        from modules.bilibili_dubbing.sources.bilibili import BilibiliSource

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name in ("source.mp4.part", "source.f30080.mp4.part", "khac.mp4", "source.vi.ass", "source.jpg"):
                (folder / name).write_text("x")
            self.assertIsNone(BilibiliSource._first_file(folder, BilibiliSource._VIDEO_EXTS))
            (folder / "source.mp4").write_text("x")
            self.assertEqual(BilibiliSource._first_file(folder, BilibiliSource._VIDEO_EXTS).name, "source.mp4")
            self.assertEqual(BilibiliSource._first_file(folder, BilibiliSource._SUBTITLE_EXTS).name, "source.vi.ass")
            self.assertEqual(BilibiliSource._first_file(folder, BilibiliSource._IMAGE_EXTS).name, "source.jpg")


if __name__ == "__main__":
    unittest.main()


class BusyFileTest(FlowTestCase):
    """Windows: file đang được trình phát giữ thì không chuyển/xóa được (WinError 32). Giả lập bằng PermissionError."""

    def setUp(self):
        super().setUp()
        import shutil

        from modules.bilibili_dubbing.storage.storage_manager import StorageManager

        self.shutil = shutil
        self.real_move, self.real_rmtree = shutil.move, shutil.rmtree
        self.addCleanup(setattr, shutil, "move", self.real_move)
        self.addCleanup(setattr, shutil, "rmtree", self.real_rmtree)
        self.addCleanup(setattr, StorageManager, "BUSY_WAIT_S", StorageManager.BUSY_WAIT_S)
        StorageManager.BUSY_WAIT_S = 0.01

    def busy_move(self, failures, only_suffix=".mp4"):
        state = {"left": failures, "calls": 0}

        def move(source, target):
            if str(source).endswith(only_suffix) and "library" in str(target) and state["left"] > 0:
                state["left"] -= 1
                state["calls"] += 1
                raise PermissionError(32, "The process cannot access the file because it is being used by another process")
            return self.real_move(source, target)

        self.shutil.move = move
        return state

    def test_publish_waits_for_a_briefly_busy_file(self):
        state = self.busy_move(failures=3)
        job = self.start_and_wait({"AWAITING_REVIEW"})
        done = self.approve(job["id"])
        self.assertEqual(done["status"], "DONE", done.get("error"))
        self.assertEqual(state["calls"], 3)

    def test_publish_failure_keeps_downloaded_video_and_retry_succeeds(self):
        self.busy_move(failures=10 ** 6)
        job = self.start_and_wait({"AWAITING_REVIEW"})
        failed = self.approve(job["id"])
        self.assertEqual(failed["status"], "FAILED")
        self.assertIn("đang được chương trình khác sử dụng", failed["error"])
        self.assertNotIn("PermissionError", failed["error"])
        work = self.data_dir / "work" / job["id"]
        self.assertTrue((work / "source.mp4").is_file())                       # video đã tải không bị mất
        self.assertEqual(self.client.get("/api/bilibili/library").json()["items"], [])
        self.assertEqual(list((self.data_dir / "library").glob("*")), [])      # không để lại thư mục mồ côi

        self.shutil.move = self.real_move                                      # trình phát đã đóng
        self.client.post(f"/api/bilibili/jobs/{job['id']}/retry")
        done = self.wait_for(job["id"], {"DONE", "FAILED"})
        self.assertEqual(done["status"], "DONE", done.get("error"))
        self.assertEqual((len(self.source.requests), len(self.translator.calls)), (1, 1))   # không tải, không dịch lại

    def test_failure_after_video_moved_rolls_everything_back(self):
        self.busy_move(failures=10 ** 6, only_suffix="subs.vi.vtt")            # video chuyển xong, phụ đề thì kẹt
        job = self.start_and_wait({"AWAITING_REVIEW"})
        failed = self.approve(job["id"])
        self.assertEqual(failed["status"], "FAILED")
        work = self.data_dir / "work" / job["id"]
        self.assertTrue((work / "source.mp4").is_file())
        self.assertTrue((work / "subs.vi.vtt").is_file())
        self.shutil.move = self.real_move
        self.client.post(f"/api/bilibili/jobs/{job['id']}/retry")
        self.assertEqual(self.wait_for(job["id"], {"DONE", "FAILED"})["status"], "DONE")

    def test_delete_library_item_while_file_is_busy_keeps_the_record(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        item_id = self.approve(job["id"])["item_id"]

        def busy_rmtree(path, *args, **kwargs):
            raise PermissionError(32, "being used by another process")

        self.shutil.rmtree = busy_rmtree
        refused = self.client.delete(f"/api/bilibili/library/{item_id}")
        self.assertEqual((refused.status_code, refused.json()["code"]), (409, "file_busy"))
        self.assertEqual(self.client.get(f"/api/bilibili/library/{item_id}").status_code, 200)
        self.assertTrue((self.data_dir / "library" / item_id / "video.mp4").is_file())
        self.shutil.rmtree = self.real_rmtree
        self.assertEqual(self.client.delete(f"/api/bilibili/library/{item_id}").status_code, 200)

    def test_stream_does_not_keep_the_file_open_between_chunks(self):
        import os

        from modules.bilibili_dubbing.api import streaming

        target = self.data_dir / "big.bin"
        target.write_bytes(os.urandom(3 * 1024 * 1024 + 123))
        opened_before = len(os.listdir("/proc/self/fd")) if os.path.isdir("/proc/self/fd") else None
        reader = streaming._read(target, 0, target.stat().st_size)
        first = next(reader)                                                   # trình duyệt nhận 1 khối rồi tạm dừng
        self.assertEqual(len(first), 1024 * 1024)
        if opened_before is not None:
            self.assertEqual(len(os.listdir("/proc/self/fd")), opened_before)  # không còn handle nào mở
        moved = self.data_dir / "moved.bin"
        os.replace(target, moved)                                              # chuyển file trong lúc đang phát dở
        self.assertEqual(list(reader), [])                                     # luồng phát dừng êm, không lỗi
