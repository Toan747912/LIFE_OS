"""Lớp nền cho các test chạy trọn luồng job qua API với nguồn video, dịch và bóc băng giả."""
import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAS_TEST_CLIENT = True
except Exception:
    HAS_TEST_CLIENT = False

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.sources.registry import SourceRegistry
from modules.bilibili_dubbing.tests import fakes

ENDED = {"DONE", "FAILED", "CANCELLED"}


@unittest.skipUnless(HAS_TEST_CLIENT and fakes.HAS_FFMPEG, "cần httpx và ffmpeg")
class FlowTestCase(unittest.TestCase):
    def setUp(self):
        from modules.bilibili_dubbing.api import container as container_module
        from modules.bilibili_dubbing.api.router import router

        self.container_module = container_module
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.data_dir = Path(self._tmp.name)
        self.source = fakes.FakeDownloadSource()
        self.translator = fakes.FakeTranslator()
        self.transcriber = fakes.FakeTranscriber()
        self.speaker = fakes.FakeSpeaker()
        self.mix = None                      # None = bộ trộn thật của LIFE_OS (chạy ffmpeg thật)
        self.settings = BilibiliSettings(data_dir=self.data_dir, min_free_bytes=1, max_probe_per_source=2,
                                         tts_retry_wait_s=0.01)
        self.container = self.new_container()
        container_module.set_container(self.container)
        self.addCleanup(container_module.set_container, None)
        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def new_container(self, settings=None, source=None):
        return self.container_module.ServiceContainer(
            settings or self.settings, SourceRegistry([source or self.source]),
            translator=self.translator, transcriber=self.transcriber, speak=self.speaker, mix=self.mix,
            cookie_fetch=getattr(self, "cookie_fetch", None),
        )

    def scan(self, url=fakes.SINGLE_URL):
        return self.client.post("/api/bilibili/scan", json={"urls": [url]}).json()

    def create(self, scan, subtitle="platform:zh-CN", episode_id="p1", format_id="30080", **extra):
        body = {"scan_id": scan["scan_id"], "items": [
            {"result_index": 0, "episode_id": episode_id, "format_id": format_id, "subtitle": subtitle}], **extra}
        return self.client.post("/api/bilibili/jobs", json=body)

    def job(self, job_id):
        return self.client.get(f"/api/bilibili/jobs/{job_id}").json()

    def wait_for(self, job_id, statuses, timeout=20):
        deadline = time.time() + timeout
        job = {}
        while time.time() < deadline:
            job = self.job(job_id)
            if job["status"] in statuses:
                return job
            time.sleep(0.05)
        self.fail(f"job {job_id} không đạt {statuses}, đang ở {job.get('status')}: {job.get('error')}")

    def start_and_wait(self, statuses, **create_args):
        response = self.create(self.scan(), **create_args)
        self.assertEqual(response.status_code, 200, response.text)
        job_id = response.json()["jobs"][0]["id"]
        return self.wait_for(job_id, set(statuses) | {"FAILED"})

    def approve(self, job_id):
        response = self.client.post(f"/api/bilibili/jobs/{job_id}/approve")
        self.assertEqual(response.status_code, 200, response.text)
        return self.wait_for(job_id, ENDED)

    def run_to_done(self, job_id):
        """Chờ tới bước duyệt, duyệt luôn, rồi chờ hoàn tất."""
        waiting = self.wait_for(job_id, {"AWAITING_REVIEW"} | ENDED)
        self.assertEqual(waiting["status"], "AWAITING_REVIEW", waiting.get("error"))
        done = self.approve(job_id)
        self.assertEqual(done["status"], "DONE", done.get("error"))
        return done
