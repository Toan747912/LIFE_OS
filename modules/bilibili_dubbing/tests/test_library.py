"""Giai đoạn 5: quản lý thư viện (sửa thông tin, series, tag, tìm kiếm), nơi lưu, dung lượng, cài đặt."""
import shutil
import threading
import time
import unittest
from pathlib import Path

from modules.bilibili_dubbing.config import PROJECT_ROOT
from modules.bilibili_dubbing.storage.text_utils import clean_name, fold
from modules.bilibili_dubbing.tests import fakes
from modules.bilibili_dubbing.tests.support import ENDED, FlowTestCase


class TextUtilsTest(unittest.TestCase):
    def test_fold_ignores_accents_and_case(self):
        self.assertEqual(fold("Lớp Học ĐẶC biệt"), "lop hoc dac biet")
        self.assertIn(fold("dac biet"), fold("Lớp học Đặc Biệt"))

    def test_clean_name(self):
        self.assertEqual(clean_name("  Tên \t có\n  khoảng   trắng \x00 ", 50), "Tên có khoảng trắng")
        self.assertEqual(clean_name("x" * 100, 10), "x" * 10)


class LibraryManagementTest(FlowTestCase):
    def publish(self, **create_args):
        job = self.start_and_wait({"AWAITING_REVIEW"}, **create_args)
        done = self.approve(job["id"])
        self.assertEqual(done["status"], "DONE", done.get("error"))
        return done["item_id"]

    def patch(self, item_id, **body):
        return self.client.patch(f"/api/bilibili/library/{item_id}", json=body)

    def titles(self, **params):
        return [i["title"] for i in self.client.get("/api/bilibili/library", params=params).json()["items"]]

    # ── Sửa thông tin ─────────────────────────────────────────────────────────
    def test_rename_note_series_tags(self):
        item_id = self.publish()
        updated = self.patch(item_id, title="  Tập 11:  bản   đẹp ", note=" ghi chú ", series="Hải Tặc",
                             tags=["#hành động", "Hành Động", "  anime ", ""])
        self.assertEqual(updated.status_code, 200, updated.text)
        data = updated.json()
        self.assertEqual((data["title"], data["note"], data["series"], data["tags"]),
                         ("Tập 11: bản đẹp", "ghi chú", "Hải Tặc", ["anime", "hành động"]))
        # chỉ đổi trường được gửi; file trên đĩa giữ nguyên
        only_note = self.patch(item_id, note="mới").json()
        self.assertEqual((only_note["title"], only_note["series"], only_note["tags"]),
                         ("Tập 11: bản đẹp", "Hải Tặc", ["anime", "hành động"]))
        self.assertTrue((self.data_dir / "library" / item_id / "video.mp4").is_file())
        self.assertEqual(self.patch(item_id, series="").json()["series"], None)
        self.assertEqual(self.patch(item_id, tags=[]).json()["tags"], [])

    def test_update_validation(self):
        item_id = self.publish()
        bad = [self.patch(item_id, title="   "), self.patch(item_id, note="x" * 2001),
               self.patch(item_id, tags=[f"t{i}" for i in range(13)])]
        self.assertEqual([r.status_code for r in bad], [400, 400, 400])
        self.assertEqual(self.patch("it_khong_co", title="x").status_code, 404)
        long_title = self.patch(item_id, title="y" * 500).json()["title"]
        self.assertEqual(len(long_title), 200)

    def test_download_name_follows_new_title(self):
        item_id = self.publish()
        self.patch(item_id, title='Tên: có / ký tự * lạ?')
        header = self.client.get(f"/api/bilibili/library/{item_id}/download").headers["content-disposition"]
        self.assertNotIn("/", header.split("filename")[-1].replace("utf-8''", ""))
        self.assertIn("T%C3%AAn", header)

    # ── Series và tag ─────────────────────────────────────────────────────────
    def test_series_and_tag_lifecycle(self):
        first, second = self.publish(), self.publish()
        self.patch(first, series="Phim A", tags=["hay", "xem lại"])
        self.patch(second, series="phim a", tags=["hay"])               # không phân biệt hoa thường
        series = self.client.get("/api/bilibili/series").json()["series"]
        self.assertEqual([(s["name"], s["item_count"]) for s in series], [("Phim A", 2)])
        tags = self.client.get("/api/bilibili/tags").json()["tags"]
        self.assertEqual([(t["name"], t["item_count"]) for t in tags], [("hay", 2), ("xem lại", 1)])

        series_id = series[0]["id"]
        self.assertEqual(self.client.patch(f"/api/bilibili/series/{series_id}", json={"name": "Phim B"}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/bilibili/library/{first}").json()["series"], "Phim B")
        self.assertEqual(self.client.patch(f"/api/bilibili/series/{series_id}", json={"name": " "}).status_code, 400)
        self.patch(second, series="Phim C")
        self.assertEqual(self.client.patch(f"/api/bilibili/series/{series_id}", json={"name": "PHIM C"}).status_code, 409)

        self.patch(first, tags=["hay"])                                  # "xem lại" không còn ai dùng -> tự biến mất
        self.assertEqual([t["name"] for t in self.client.get("/api/bilibili/tags").json()["tags"]], ["hay"])
        tag_id = self.client.get("/api/bilibili/tags").json()["tags"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/bilibili/tags/{tag_id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/bilibili/library/{first}").json()["tags"], [])

        self.assertEqual(self.client.delete(f"/api/bilibili/series/{series_id}").status_code, 200)
        kept = self.client.get(f"/api/bilibili/library/{first}").json()   # xóa series không xóa video
        self.assertEqual((kept["series"], kept["has_video"]), (None, True))
        self.assertEqual(self.client.delete(f"/api/bilibili/series/{series_id}").status_code, 404)
        self.assertEqual(self.client.delete("/api/bilibili/tags/9999").status_code, 404)

    def test_playlist_episode_is_filed_under_its_series(self):
        scan = self.scan(fakes.SERIES_URL)
        job = self.create(scan).json()["jobs"][0]
        item_id = self.run_to_done(job["id"])["item_id"]
        item = self.client.get(f"/api/bilibili/library/{item_id}").json()
        self.assertEqual((item["series"], item["episode_label"]), ("Series mẫu", "Tập 1"))
        self.assertEqual(self.client.get("/api/bilibili/library/" + self.publish()).json()["series"], None)

    # ── Tìm kiếm, lọc, sắp xếp ────────────────────────────────────────────────
    def test_search_filter_sort(self):
        a, b, c = self.publish(), self.publish(), self.publish()
        self.patch(a, title="Lớp học đặc biệt", series="Trường", tags=["học đường"], note="xem cùng em")
        self.patch(b, title="Chuyến đi biển", series="Du lịch", tags=["biển"])
        self.patch(c, title="Ăn sáng ở Đà Nẵng", series="Du lịch", tags=["ẩm thực", "biển"])
        self.container.library_repo.update(b, size_bytes=10 ** 9)

        self.assertEqual(self.titles(q="dac biet"), ["Lớp học đặc biệt"])             # không dấu vẫn ra
        self.assertEqual(self.titles(q="DA NANG an"), ["Ăn sáng ở Đà Nẵng"])          # nhiều từ, mọi từ phải khớp
        self.assertEqual(self.titles(q="cung em"), ["Lớp học đặc biệt"])              # tìm cả trong ghi chú
        self.assertEqual(self.titles(q="du lich", sort="title"), ["Ăn sáng ở Đà Nẵng", "Chuyến đi biển"])
        self.assertEqual(self.titles(q="khong co gi"), [])
        self.assertEqual(sorted(self.titles(tag="Biển")), ["Chuyến đi biển", "Ăn sáng ở Đà Nẵng"])
        series_id = next(s["id"] for s in self.client.get("/api/bilibili/series").json()["series"] if s["name"] == "Trường")
        self.assertEqual(self.titles(series=series_id), ["Lớp học đặc biệt"])
        self.assertEqual(len(self.titles(status="dubbed")), 3)
        self.assertEqual(self.titles(status="undubbed"), [])
        self.assertEqual(self.titles(sort="title"), ["Ăn sáng ở Đà Nẵng", "Chuyến đi biển", "Lớp học đặc biệt"])
        self.assertEqual(self.titles(sort="size")[0], "Chuyến đi biển")
        self.assertEqual(self.titles(sort="oldest")[0], "Lớp học đặc biệt")
        self.assertEqual(self.client.get("/api/bilibili/library", params={"sort": "lung tung"}).status_code, 400)
        self.assertEqual(self.client.get("/api/bilibili/library", params={"status": "x"}).status_code, 400)

    # ── Dung lượng và dọn dẹp ─────────────────────────────────────────────────
    def test_usage_and_cleanup(self):
        kept = self.publish(keep_source=True)
        self.source.fail_times = 1
        failed = self.start_and_wait({"FAILED"})                       # job thất bại để lại thư mục tạm
        work = self.data_dir / "work"
        (work / failed["id"] / "rac.bin").write_bytes(b"x" * 3000)
        (work / "job_mo_coi").mkdir()
        (work / "job_mo_coi" / "a.bin").write_bytes(b"x" * 2000)
        orphan_item = self.data_dir / "library" / "it_mo_coi"
        orphan_item.mkdir()
        (orphan_item / "video.mp4").write_bytes(b"x" * 5000)
        (self.data_dir / "library" / "thu_muc_cua_ban").mkdir()        # không phải của module: không được đụng
        waiting = self.start_and_wait({"AWAITING_REVIEW"})             # job đang chờ: file tạm phải được giữ

        usage = self.client.get("/api/bilibili/storage").json()
        self.assertEqual(usage["item_count"], 1)
        self.assertTrue(usage["is_default_root"])
        self.assertGreater(usage["library_bytes"], 1000)
        self.assertGreater(usage["disk_free_bytes"], 0)
        clean = usage["cleanable"]
        self.assertEqual((clean["stopped_jobs"]["count"], clean["orphan_work"]["count"],
                          clean["kept_sources"]["count"], clean["orphan_library"]["count"]), (1, 1, 1, 1))
        self.assertGreaterEqual(clean["stopped_jobs"]["bytes"], 3000)
        self.assertEqual((clean["orphan_work"]["bytes"], clean["orphan_library"]["bytes"]), (2000, 5000))
        self.assertGreater(usage["active_work_bytes"], 0)

        bad = self.client.post("/api/bilibili/storage/cleanup", json={"targets": ["tat_ca"]})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.client.post("/api/bilibili/storage/cleanup", json={"targets": []}).status_code, 400)

        result = self.client.post("/api/bilibili/storage/cleanup", json={"targets": ["orphan_work", "orphan_library"]}).json()
        self.assertEqual(result["freed"], {"orphan_work": 2000, "orphan_library": 5000})
        self.assertFalse((work / "job_mo_coi").exists())
        self.assertFalse(orphan_item.exists())
        self.assertTrue((work / failed["id"]).exists())                 # chưa chọn thì chưa dọn
        self.assertTrue((self.data_dir / "library" / "thu_muc_cua_ban").is_dir())

        before = self.client.get(f"/api/bilibili/library/{kept}").json()
        result = self.client.post("/api/bilibili/storage/cleanup", json={"targets": ["stopped_jobs", "kept_sources"]}).json()
        self.assertGreater(result["freed"]["kept_sources"], 1000)
        self.assertEqual(result["skipped_busy"], 0)
        after = self.client.get(f"/api/bilibili/library/{kept}").json()
        self.assertEqual((before["has_source"], after["has_source"], after["has_video"]), (True, False, True))
        self.assertLess(after["size_bytes"], before["size_bytes"])
        self.assertFalse((work / failed["id"]).exists())
        self.assertTrue((work / waiting["id"] / "source.mp4").is_file())  # job đang chờ duyệt không bị dọn
        again = self.client.get("/api/bilibili/storage").json()["cleanable"]
        self.assertEqual([again[k]["count"] for k in ("stopped_jobs", "orphan_work", "kept_sources", "orphan_library")], [0] * 4)

        # job đã bị dọn file tạm vẫn chạy lại được: tải lại từ đầu
        self.client.post(f"/api/bilibili/jobs/{failed['id']}/retry")
        self.assertEqual(self.wait_for(failed["id"], {"AWAITING_REVIEW"} | ENDED)["status"], "AWAITING_REVIEW")

    # ── Đổi nơi lưu ───────────────────────────────────────────────────────────
    def move(self, path):
        return self.client.put("/api/bilibili/storage/root", json={"path": str(path)})

    def test_move_library_to_new_folder(self):
        first, second = self.publish(keep_source=True), self.publish()
        old_root = self.data_dir / "library"
        new_root = self.data_dir.parent / (self.data_dir.name + "_o_khac") / "Thư viện"
        self.addCleanup(shutil.rmtree, new_root.parent, True)
        before = self.client.get(f"/api/bilibili/library/{first}/stream").content

        started = self.move(new_root)
        self.assertEqual(started.status_code, 200, started.text)
        state = self.container.library_mover.wait(30)
        self.assertEqual((state["status"], state["done"], state["total"], state["leftover"]), ("done", 2, 2, []))

        usage = self.client.get("/api/bilibili/storage").json()
        self.assertEqual((usage["library_root"], usage["is_default_root"]), (str(new_root.resolve()), False))
        self.assertEqual(usage["move"]["status"], "done")
        self.assertEqual(sorted(p.name for p in new_root.iterdir()), sorted([first, second]))
        self.assertEqual(list(old_root.iterdir()), [])                          # nơi cũ đã được dọn
        self.assertEqual(self.client.get(f"/api/bilibili/library/{first}/stream").content, before)
        self.assertEqual(self.client.get(f"/api/bilibili/library/{first}/stream?kind=source").status_code, 200)
        self.assertEqual(self.client.get(f"/api/bilibili/library/{second}/subtitle?kind=vi").status_code, 200)
        self.assertFalse(self.container.runner.paused)

        third = self.publish()                                                  # video mới vào đúng nơi mới
        self.assertTrue((new_root / third / "video.mp4").is_file())
        self.assertEqual(self.client.delete(f"/api/bilibili/library/{second}").status_code, 200)
        self.assertFalse((new_root / second).exists())

    def test_move_refuses_unsafe_targets(self):
        self.publish()
        outside = self.data_dir.parent / (self.data_dir.name + "_dich")
        self.addCleanup(shutil.rmtree, outside, True)
        (outside / "co_file").mkdir(parents=True)
        (outside / "co_file" / "anh.jpg").write_bytes(b"x")
        (outside / "la_file.txt").write_bytes(b"x")
        cases = {
            "": 400, "tuong/doi": 400,
            str(self.data_dir / "library"): 400,                                # chính nó
            str(self.data_dir / "library" / "con"): 400,                        # nằm trong thư viện hiện tại
            str(self.data_dir): 400,                                            # chứa thư viện hiện tại
            str(self.data_dir / "work" / "x"): 400,                             # thư mục làm việc tạm
            str(PROJECT_ROOT / "core" / "input"): 400,                          # thư mục của chức năng khác
            str(PROJECT_ROOT / "modules" / "x"): 400,
            str(outside / "co_file"): 400,                                      # đã có file lạ
            str(outside / "la_file.txt"): 400,                                  # là file
        }
        for path, expected in cases.items():
            response = self.move(path)
            self.assertEqual(response.status_code, expected, f"{path!r}: {response.text}")
        self.assertEqual(self.container.library_mover.status()["status"], "idle")
        self.assertTrue(self.client.get("/api/bilibili/storage").json()["is_default_root"])
        self.assertEqual(sorted(p.name for p in outside.iterdir()), ["co_file", "la_file.txt"])   # không bị đụng

    def test_move_refused_while_a_job_is_running_and_jobs_wait_during_move(self):
        self.publish()
        target = self.data_dir.parent / (self.data_dir.name + "_ban")
        self.addCleanup(shutil.rmtree, target, True)
        self.source.gate = threading.Event()
        running = self.create(self.scan()).json()["jobs"][0]
        self.wait_for(running["id"], {"DOWNLOADING"})
        self.assertEqual(self.move(target).status_code, 409)
        self.source.gate.set()
        self.wait_for(running["id"], {"AWAITING_REVIEW"} | ENDED)

        # Trong lúc chuyển, job mới được xếp hàng nhưng chưa chạy; chuyển xong mới chạy.
        self.assertTrue(self.container.runner.pause())
        queued = self.create(self.scan()).json()["jobs"][0]
        time.sleep(0.4)
        self.assertEqual(self.job(queued["id"])["status"], "QUEUED")
        self.container.runner.resume()
        self.assertEqual(self.wait_for(queued["id"], {"AWAITING_REVIEW"} | ENDED)["status"], "AWAITING_REVIEW")

    def test_failed_move_leaves_library_where_it_was(self):
        first, second = self.publish(), self.publish()
        target = self.data_dir.parent / (self.data_dir.name + "_loi")
        self.addCleanup(shutil.rmtree, target, True)
        real_copytree = shutil.copytree
        calls = {"n": 0}

        def copy_then_fail(source, destination, *args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                raise OSError("ổ đĩa đầy")
            return real_copytree(source, destination, *args, **kwargs)

        shutil.copytree = copy_then_fail
        self.addCleanup(setattr, shutil, "copytree", real_copytree)
        self.assertEqual(self.move(target).status_code, 200)
        state = self.container.library_mover.wait(30)
        self.assertEqual(state["status"], "failed")
        self.assertIn("ổ đĩa đầy", state["error"])
        self.assertTrue(self.client.get("/api/bilibili/storage").json()["is_default_root"])
        self.assertEqual(list(target.iterdir()), [])                            # phần sao chép dở đã được dọn
        for item_id in (first, second):
            self.assertEqual(self.client.get(f"/api/bilibili/library/{item_id}/stream").status_code, 200)
        self.assertFalse(self.container.runner.paused)

    # ── Cài đặt mặc định ──────────────────────────────────────────────────────
    def test_settings_defaults_and_whisper_model(self):
        settings = self.client.get("/api/bilibili/settings").json()
        self.assertEqual((settings["default_voice"], settings["default_orig_vol"], settings["default_dub_vol"],
                          settings["default_keep_source"], settings["whisper_model"]),
                         ("vi-VN-HoaiMyNeural", 0.15, 1.0, False, "small"))
        saved = self.client.put("/api/bilibili/settings", json={
            "default_voice": "vi-VN-NamMinhNeural", "default_orig_vol": 0.3, "default_keep_source": True,
            "whisper_model": "medium"}).json()
        self.assertEqual((saved["default_voice"], saved["default_orig_vol"], saved["default_dub_vol"],
                          saved["default_keep_source"], saved["whisper_model"]),
                         ("vi-VN-NamMinhNeural", 0.3, 1.0, True, "medium"))
        bad = [{"default_voice": "en-US-X"}, {"whisper_model": "khong-co"}, {"default_orig_vol": 2}, {"default_dub_vol": 0.1}]
        self.assertEqual([self.client.put("/api/bilibili/settings", json=b).status_code for b in bad], [400] * 4)
        self.assertEqual(self.client.get("/api/bilibili/settings").json()["whisper_model"], "medium")

        job = self.start_and_wait({"AWAITING_REVIEW"}, subtitle="whisper")   # model mới được dùng khi bóc băng
        self.assertEqual(job["status"], "AWAITING_REVIEW", job.get("error"))
        self.assertEqual(self.transcriber.calls[-1], ("source.mp4", "medium"))


if __name__ == "__main__":
    unittest.main()
