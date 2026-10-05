import tempfile
import unittest
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    HAS_TEST_CLIENT = True
except Exception:  # thiếu httpx thì bỏ qua nhóm test này
    HAS_TEST_CLIENT = False

from modules.bilibili_dubbing.config import BilibiliSettings
from modules.bilibili_dubbing.sources.bilibili import BilibiliSource
from modules.bilibili_dubbing.sources.registry import SourceRegistry
from modules.bilibili_dubbing.sources.scan_service import ScanService
from modules.bilibili_dubbing.storage.database import MIGRATIONS
from modules.bilibili_dubbing.tests import fakes


class ParseUrlsTest(unittest.TestCase):
    def test_splits_dedupes_and_keeps_order(self):
        raw = "a\n b ,a\r\n\n c"
        self.assertEqual(ScanService.parse_urls(raw), ["a", "b", "c"])


@unittest.skipUnless(HAS_TEST_CLIENT, "cần httpx để chạy TestClient")
class ApiTest(unittest.TestCase):
    def setUp(self):
        from modules.bilibili_dubbing.api import container as container_module
        from modules.bilibili_dubbing.api.router import router

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        settings = BilibiliSettings(data_dir=Path(self._tmp.name), max_urls_per_scan=3, max_probe_per_source=1)
        registry = SourceRegistry([BilibiliSource(extractor=fakes.fake_extractor)])
        container_module.set_container(container_module.ServiceContainer(settings, registry))
        self.addCleanup(container_module.set_container, None)

        app = FastAPI()
        app.include_router(router)
        self.client = TestClient(app)

    def test_page_and_static_files(self):
        page = self.client.get("/bilibili")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Bilibili Dubbing", page.text)
        self.assertEqual(self.client.get("/bilibili/static/bilibili.js").status_code, 200)
        self.assertEqual(self.client.get("/bilibili/static/bilibili.css").status_code, 200)
        self.assertEqual(self.client.get("/bilibili/static/secret.txt").status_code, 404)
        self.assertEqual(self.client.get("/bilibili/static/..%2Fbilibili.html").status_code, 404)

    def test_health(self):
        body = self.client.get("/api/bilibili/health").json()
        self.assertEqual(body["schema_version"], len(MIGRATIONS))
        self.assertFalse(body["cookie_configured"])

    def test_scan_mixed_links_isolates_failures(self):
        response = self.client.post("/api/bilibili/scan", json={"urls": [
            fakes.SINGLE_URL, "https://www.youtube.com/watch?v=1", fakes.LOCKED_URL,
        ]})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        ok, unsupported, locked = body["results"]
        self.assertTrue(ok["ok"])
        self.assertEqual(ok["episodes"][0]["formats"][0]["label"], "1080p · AVC")
        self.assertEqual([s["lang"] for s in ok["episodes"][0]["subtitles"]], ["zh-CN", "ai-zh"])
        self.assertEqual((unsupported["ok"], unsupported["error_code"]), (False, "unsupported_url"))
        self.assertEqual((locked["ok"], locked["error_code"]), (False, "access_denied"))

        saved = self.client.get(f"/api/bilibili/scan/{body['scan_id']}")
        self.assertEqual(saved.json(), body)

    def test_scan_validation_errors(self):
        empty = self.client.post("/api/bilibili/scan", json={"urls": ["  "]})
        self.assertEqual((empty.status_code, empty.json()["code"]), (400, "invalid_request"))
        too_many = self.client.post("/api/bilibili/scan", json={"urls": ["a", "b", "c", "d"]})
        self.assertEqual(too_many.status_code, 400)
        self.assertEqual(self.client.post("/api/bilibili/scan", json={}).status_code, 422)

    def test_cookie_save_status_delete(self):
        url = "/api/bilibili/settings/cookie"
        self.assertFalse(self.client.get(url).json()["configured"])
        saved = self.client.put(url, json={"text": "secret-value", "site": "bilibili.tv"})
        self.assertEqual(saved.status_code, 200)
        self.assertNotIn("secret-value", saved.text)
        self.assertEqual(saved.json()["sites"], ["bilibili.tv"])
        self.assertNotIn("secret-value", self.client.get(url).text)
        self.assertTrue(self.client.get("/api/bilibili/health").json()["cookie_configured"])
        bad = self.client.put(url, json={"text": "a b", "site": "bilibili.tv"})
        self.assertEqual((bad.status_code, bad.json()["code"]), (400, "invalid_request"))
        self.assertFalse(self.client.delete(url).json()["configured"])

    def test_unknown_scan_is_404(self):
        response = self.client.get("/api/bilibili/scan/sc_missing")
        self.assertEqual((response.status_code, response.json()["code"]), (404, "not_found"))

    def test_probe_episode_on_demand_and_persist(self):
        scan = self.client.post("/api/bilibili/scan", json={"urls": [fakes.SERIES_URL]}).json()
        episodes = scan["results"][0]["episodes"]
        self.assertEqual([e["probed"] for e in episodes], [True, False, False])

        probe_url = f"/api/bilibili/scan/{scan['scan_id']}/probe"
        third = self.client.post(probe_url, json={"result_index": 0, "episode_id": "p3"}).json()
        self.assertTrue(third["probed"] and third["accessible"])
        second = self.client.post(probe_url, json={"result_index": 0, "episode_id": "p2"}).json()
        self.assertEqual((second["accessible"], second["error_code"]), (False, "access_denied"))

        saved = self.client.get(f"/api/bilibili/scan/{scan['scan_id']}").json()
        self.assertEqual([e["probed"] for e in saved["results"][0]["episodes"]], [True, True, True])

        missing = self.client.post(probe_url, json={"result_index": 5, "episode_id": "p1"})
        self.assertEqual(missing.status_code, 404)


if __name__ == "__main__":
    unittest.main()
