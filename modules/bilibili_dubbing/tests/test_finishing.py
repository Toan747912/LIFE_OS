"""Giai đoạn 6: lô nhiều video, kiểm tra cookie trực tuyến, dọn job đã xong, báo thiếu phụ thuộc."""
import tempfile
import unittest
from pathlib import Path

from modules.bilibili_dubbing.storage.cookie_checker import NAV_URL, CookieChecker
from modules.bilibili_dubbing.storage.cookie_store import CookieStore
from modules.bilibili_dubbing.tests.support import ENDED, FlowTestCase


class CookieCheckerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "cookies.txt"
        self.calls = []

    def checker(self, payload=None, error=None):
        def fetch(url, cookie_path, timeout_s):
            self.calls.append((url, cookie_path))
            if error:
                raise error
            return payload

        return CookieChecker(self.path, fetch=fetch)

    def test_no_cookie_file(self):
        result = self.checker({}).check()
        self.assertEqual((result["checked"], result["logged_in"]), (False, None))
        self.assertEqual(self.calls, [])

    def test_valid_cookie_reports_account_without_leaking_values(self):
        CookieStore(self.path).save_from_text("gia-tri-bi-mat", "bilibili.com")
        result = self.checker({"code": 0, "data": {"isLogin": True, "uname": "toan", "vipStatus": 1}}).check()
        self.assertEqual((result["checked"], result["logged_in"], result["username"], result["vip"]),
                         (True, True, "toan", True))
        self.assertIn("còn hiệu lực", result["message"])
        self.assertNotIn("gia-tri-bi-mat", str(result))
        self.assertEqual(self.calls, [(NAV_URL, self.path)])

    def test_expired_cookie(self):
        CookieStore(self.path).save_from_text("cu", "bilibili.com")
        for payload in ({"code": -101, "message": "账号未登录"}, {"code": 0, "data": {"isLogin": False}}, {}):
            result = self.checker(payload).check()
            self.assertEqual((result["checked"], result["logged_in"]), (True, False), payload)
            self.assertIn("hết hạn", result["message"])

    def test_network_failure_is_not_reported_as_expired(self):
        CookieStore(self.path).save_from_text("x", "bilibili.com")
        result = self.checker(error=TimeoutError("timed out")).check()
        self.assertEqual((result["checked"], result["logged_in"]), (False, None))
        self.assertIn("Kiểm tra mạng", result["message"])

    def test_bilibili_tv_cookie_is_not_checked_online(self):
        CookieStore(self.path).save_from_text("x", "bilibili.tv")
        result = self.checker({"code": 0, "data": {"isLogin": True}}).check()
        self.assertEqual((result["checked"], result["logged_in"]), (False, None))
        self.assertIn("bilibili.tv", result["message"])
        self.assertEqual(self.calls, [])                                     # không gửi cookie sai trang đi đâu cả


class FinishingFlowTest(FlowTestCase):
    def cookie_fetch(self, url, cookie_path, timeout_s):
        return {"code": 0, "data": {"isLogin": True, "uname": "toan", "vipStatus": 0}}

    def test_batch_of_three_videos_from_several_links(self):
        urls = [f"https://www.bilibili.com/video/BV1aa411c7m{n}" for n in "ABC"]
        scan = self.client.post("/api/bilibili/scan", json={"urls": urls}).json()
        self.assertEqual([r["ok"] for r in scan["results"]], [True, True, True])
        body = {"scan_id": scan["scan_id"], "items": [
            {"result_index": index, "episode_id": "p1", "format_id": "30080", "subtitle": "platform:zh-CN"}
            for index in range(3)]}
        jobs = self.client.post("/api/bilibili/jobs", json=body).json()["jobs"]
        self.assertEqual(len(jobs), 3)
        for job in jobs:                               # cả lô tải và dịch xong trước, không job nào chặn job nào
            self.assertEqual(self.wait_for(job["id"], {"AWAITING_REVIEW"} | ENDED)["status"], "AWAITING_REVIEW")
        for job in jobs:
            self.client.post(f"/api/bilibili/jobs/{job['id']}/approve")
        for job in jobs:
            done = self.wait_for(job["id"], ENDED, timeout=40)
            self.assertEqual(done["status"], "DONE", done.get("error"))
        items = self.client.get("/api/bilibili/library").json()["items"]
        self.assertEqual((len(items), {i["dubbed"] for i in items}), (3, {True}))
        self.assertEqual([r.url for r in self.source.requests], urls)          # đúng thứ tự, mỗi video tải một lần
        self.assertEqual(list((self.data_dir / "work").iterdir()), [])         # không để lại file tạm

    def test_clear_finished_jobs_keeps_videos_and_unfinished_jobs(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        item_id = self.approve(job["id"])["item_id"]
        waiting = self.start_and_wait({"AWAITING_REVIEW"})
        self.source.fail_times = 1
        failed = self.start_and_wait({"FAILED"})

        cleared = self.client.post("/api/bilibili/jobs/clear-finished").json()
        self.assertEqual(cleared, {"deleted": 1})
        remaining = {j["id"]: j["status"] for j in self.client.get("/api/bilibili/jobs").json()["jobs"]}
        self.assertEqual(remaining, {waiting["id"]: "AWAITING_REVIEW", failed["id"]: "FAILED"})
        self.assertEqual(self.client.get(f"/api/bilibili/library/{item_id}/stream").status_code, 200)
        self.assertEqual(self.client.post("/api/bilibili/jobs/clear-finished").json(), {"deleted": 0})

    def test_cookie_check_endpoint(self):
        url = "/api/bilibili/settings/cookie/check"
        self.assertEqual(self.client.post(url).json()["checked"], False)       # chưa lưu cookie
        self.client.put("/api/bilibili/settings/cookie", json={"text": "bi-mat", "site": "bilibili.com"})
        result = self.client.post(url)
        self.assertEqual((result.json()["logged_in"], result.json()["username"]), (True, "toan"))
        self.assertNotIn("bi-mat", result.text)

    def test_health_lists_every_dependency(self):
        health = self.client.get("/api/bilibili/health").json()
        self.assertEqual(set(health), {"yt_dlp", "ffmpeg", "edge_tts", "deep_translator", "faster_whisper",
                                       "cookie_configured", "schema_version"})
        self.assertIsInstance(health["edge_tts"], bool)


if __name__ == "__main__":
    unittest.main()
