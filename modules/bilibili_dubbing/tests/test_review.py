"""Giai đoạn 3: phụ đề gốc từ 3 nguồn, dịch, duyệt và sửa."""
import tempfile
import unittest
from pathlib import Path

from modules.bilibili_dubbing.domain.errors import InvalidRequest
from modules.bilibili_dubbing.subtitles.document import Cue, SubtitleDocument
from modules.bilibili_dubbing.subtitles.translator import GoogleTranslatorAdapter, is_vietnamese, to_google_lang
from modules.bilibili_dubbing.tests import fakes
from modules.bilibili_dubbing.tests.support import ENDED, FlowTestCase

SRT = "1\n00:00:00,500 --> 00:00:01,500\nCâu một\n\n2\n00:00:02,000 --> 00:00:03,000\n<i>Câu</i> hai\ndòng hai\n"


class SubtitleDocumentTest(unittest.TestCase):
    def test_reads_srt_with_the_existing_parser_and_cleans_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.srt"
            path.write_text(SRT, encoding="utf-8")
            document = SubtitleDocument.from_file(path)
        self.assertEqual([(c.idx, c.start_ms, c.end_ms, c.source_text) for c in document.cues],
                         [(1, 500, 1500, "Câu một"), (2, 2000, 3000, "Câu hai dòng hai")])

    def test_normalize_sorts_drops_invalid_and_renumbers(self):
        document = SubtitleDocument([
            Cue(9, 5000, 6000, "sau"), Cue(3, 1000, 2000, "  trước  "), Cue(1, 3000, 3000, "độ dài 0"),
            Cue(2, 100, 200, "   "), Cue(4, 900, 500, "ngược"),
        ])
        self.assertEqual([(c.idx, c.source_text) for c in document.cues], [(1, "trước"), (2, "sau")])

    def test_from_segments(self):
        document = SubtitleDocument.from_segments([{"start": 1.25, "end": 2.5, "text": " xin chào "}])
        self.assertEqual((document.cues[0].start_ms, document.cues[0].end_ms, document.cues[0].source_text),
                         (1250, 2500, "xin chào"))

    def test_write_vtt_skips_empty_lines_and_round_trips(self):
        cues = [Cue(1, 500, 1500, "a", "Xin chào"), Cue(2, 2000, 3000, "b", "  "), Cue(3, 3_661_000, 3_662_500, "c", "Cuối")]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "out.vtt"
            self.assertEqual(SubtitleDocument.write_vtt(cues, path), 2)
            text = path.read_text(encoding="utf-8")
            self.assertTrue(text.startswith("WEBVTT\n\n1\n00:00:00.500 --> 00:00:01.500\nXin chào\n"))
            self.assertIn("01:01:01.000 --> 01:01:02.500", text)
            again = SubtitleDocument.from_file(path)
        self.assertEqual([(c.start_ms, c.source_text) for c in again.cues], [(500, "Xin chào"), (3_661_000, "Cuối")])

    def test_non_utf8_file_gives_clear_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "a.srt"
            path.write_bytes("1\n00:00:00,500 --> 00:00:01,500\nCâu một\n".encode("utf-16"))
            with self.assertRaises(InvalidRequest):
                SubtitleDocument.from_file(path)


class TranslatorTest(unittest.TestCase):
    def test_language_mapping(self):
        self.assertEqual([to_google_lang(x) for x in ("zh-Hans", "ai-zh", "zh-TW", "en-US", "xx", None)],
                         ["zh-CN", "zh-CN", "zh-TW", "en", "auto", "auto"])
        self.assertEqual([is_vietnamese(x) for x in ("vi", "vi-VN", "VI", "zh", None, "")],
                         [True, True, True, False, False, False])

    def test_batches_lines_and_keeps_order(self):
        calls = []

        def call(text, source):
            calls.append((text, source))
            return "\n".join("VI:" + line for line in text.split("\n"))

        adapter = GoogleTranslatorAdapter(max_chars=12, pause_s=0, call=call)
        progress = []
        result = adapter.translate_batch(["aaaa", "bbbb", "", "cc\ncc", "dddd"], "zh-Hans",
                                         lambda done, total: progress.append((done, total)))
        self.assertEqual(result, ["VI:aaaa", "VI:bbbb", "", "VI:cc cc", "VI:dddd"])
        self.assertEqual([c[0] for c in calls], ["aaaa\nbbbb", "cc cc\ndddd"])
        self.assertEqual({c[1] for c in calls}, {"zh-CN"})
        self.assertEqual(progress[-1], (4, 5))

    def test_falls_back_to_per_line_when_line_count_changes(self):
        def call(text, source):
            return "gộp mất dòng" if "\n" in text else "VI:" + text

        adapter = GoogleTranslatorAdapter(pause_s=0, call=call)
        self.assertEqual(adapter.translate_batch(["a", "b", "c"], None), ["VI:a", "VI:b", "VI:c"])

    def test_retries_then_gives_empty_string(self):
        attempts = {"n": 0}

        def flaky(text, source):
            attempts["n"] += 1
            if attempts["n"] < 3:
                raise RuntimeError("429")
            return "ok"

        self.assertEqual(GoogleTranslatorAdapter(pause_s=0, call=flaky).translate_batch(["a"], "en"), ["ok"])

        def broken(text, source):
            return "<html>Error 500 (Server Error)</html>"

        self.assertEqual(GoogleTranslatorAdapter(pause_s=0, retries=2, call=broken).translate_batch(["a", "b"], "en"),
                         ["", ""])


class ReviewFlowTest(FlowTestCase):
    def cues(self, job_id):
        return self.client.get(f"/api/bilibili/jobs/{job_id}/cues")

    # ── Ba nguồn phụ đề ───────────────────────────────────────────────────────
    def test_platform_subtitle_is_translated_and_waits_for_review(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        self.assertEqual((job["status"], job["stage"]), ("AWAITING_REVIEW", "review"))
        data = self.cues(job["id"]).json()
        self.assertEqual((data["source_lang"], data["editable"], data["untranslated"]), ("zh-CN", True, 0))
        self.assertEqual([(c["idx"], c["source_text"], c["vi_text"], c["edited"]) for c in data["cues"]],
                         [(1, "Xin chào", "[vi] Xin chào", False), (2, "Tạm biệt", "[vi] Tạm biệt", False)])
        self.assertEqual(self.translator.calls, [(["Xin chào", "Tạm biệt"], "zh-CN")])
        self.assertEqual(self.client.get("/api/bilibili/library").json()["items"], [])   # chưa duyệt thì chưa vào thư viện

    def test_whisper_source_uses_configured_model(self):
        job = self.start_and_wait({"AWAITING_REVIEW"}, subtitle="whisper")
        self.assertEqual(job["status"], "AWAITING_REVIEW", job.get("error"))
        self.assertEqual(self.transcriber.calls, [("source.mp4", "small")])
        data = self.cues(job["id"]).json()
        self.assertEqual([(c["start_ms"], c["source_text"], c["vi_text"]) for c in data["cues"]],
                         [(0, "大家好", "[vi] 大家好"), (1100, "再见", "[vi] 再见")])
        self.assertIsNone(data["source_lang"])

    def test_whisper_falls_back_to_smaller_model_when_memory_runs_out(self):
        attempts = []
        real = self.transcriber

        def low_memory(video_path, work_dir, model_size):
            attempts.append(model_size)
            if model_size in ("small", "base"):
                raise RuntimeError("mkl_malloc: failed to allocate memory")       # đúng lỗi ctranslate2 báo trên Windows
            return real(video_path, work_dir, model_size)

        self.container.subtitle_providers["whisper"]._transcriber = low_memory
        job = self.start_and_wait({"AWAITING_REVIEW"}, subtitle="whisper")
        self.assertEqual(job["status"], "AWAITING_REVIEW", job.get("error"))
        self.assertEqual(attempts, ["small", "base", "tiny"])
        self.assertIn("đã dùng model tiny vì máy không đủ RAM cho small", job["message"])
        self.assertEqual(len(self.cues(job["id"]).json()["cues"]), 2)

    def test_whisper_out_of_memory_on_every_model_gives_clear_error(self):
        def always_fails(video_path, work_dir, model_size):
            raise MemoryError()

        self.container.subtitle_providers["whisper"]._transcriber = always_fails
        job = self.start_and_wait({"FAILED"}, subtitle="whisper")
        self.assertEqual(job["status"], "FAILED")
        self.assertIn("không đủ RAM", job["error"])
        self.assertNotIn("RuntimeError", job["error"])
        self.assertNotIn("Lỗi không mong đợi", job["error"])

    def test_other_whisper_errors_are_not_swallowed(self):
        calls = []

        def broken(video_path, work_dir, model_size):
            calls.append(model_size)
            raise RuntimeError("file âm thanh hỏng")

        self.container.subtitle_providers["whisper"]._transcriber = broken
        job = self.start_and_wait({"FAILED"}, subtitle="whisper")
        self.assertEqual(calls, ["small"])                                         # không thử lùi model
        self.assertIn("file âm thanh hỏng", job["error"])

    def test_vietnamese_subtitle_skips_translation(self):
        import modules.bilibili_dubbing.tests.fakes as f

        info = f.video_info()
        info["subtitles"] = {"vi": [{"ext": "srt", "data": "..."}]}
        self.source._extract = lambda url, flat: info
        job = self.start_and_wait({"AWAITING_REVIEW"}, subtitle="platform:vi")
        self.assertEqual(job["status"], "AWAITING_REVIEW", job.get("error"))
        self.assertEqual(self.translator.calls, [])
        self.assertEqual([c["vi_text"] for c in self.cues(job["id"]).json()["cues"]], ["Xin chào", "Tạm biệt"])

    def test_uploaded_source_waits_for_file_then_continues(self):
        job = self.start_and_wait({"AWAITING_SUBTITLE"}, subtitle="uploaded")
        self.assertEqual(job["status"], "AWAITING_SUBTITLE", job.get("error"))
        self.assertIn("upload", job["message"])
        url = f"/api/bilibili/jobs/{job['id']}/subtitle"

        bad_ext = self.client.post(url, files={"file": ("a.txt", SRT.encode("utf-8"))})
        empty = self.client.post(url, files={"file": ("a.srt", b"")})
        junk = self.client.post(url, files={"file": ("a.srt", "không phải phụ đề".encode("utf-8"))})
        utf16 = self.client.post(url, files={"file": ("a.srt", SRT.encode("utf-16"))})
        huge = self.client.post(url, files={"file": ("a.srt", b"x" * (5 * 1024 * 1024 + 1))})
        self.assertEqual([r.status_code for r in (bad_ext, empty, junk, utf16, huge)], [400] * 5)
        self.assertEqual(self.job(job["id"])["status"], "AWAITING_SUBTITLE")

        # tên file do người dùng gửi không được dùng làm đường dẫn
        ok = self.client.post(url, files={"file": ("..\\..\\evil.srt", SRT.encode("utf-8"))})
        self.assertEqual(ok.status_code, 200, ok.text)
        self.assertEqual(sorted(p.name for p in (self.data_dir / "work" / job["id"]).glob("uploaded*")), ["uploaded.srt"])
        self.assertFalse(list(self.data_dir.rglob("evil.srt")))

        waiting = self.wait_for(job["id"], {"AWAITING_REVIEW"} | ENDED)
        self.assertEqual(waiting["status"], "AWAITING_REVIEW", waiting.get("error"))
        self.assertEqual([c["vi_text"] for c in self.cues(job["id"]).json()["cues"]],
                         ["[vi] Câu một", "[vi] Câu hai dòng hai"])
        self.assertEqual(self.client.post(url, files={"file": ("a.srt", SRT.encode("utf-8"))}).status_code, 409)

    def test_missing_platform_subtitle_can_switch_to_whisper(self):
        original_download = self.source.download

        def download_without_subtitle(request, on_progress):
            request.subtitle_lang = None
            return original_download(request, on_progress)

        self.source.download = download_without_subtitle
        job = self.start_and_wait({"AWAITING_SUBTITLE"})
        self.assertEqual(job["status"], "AWAITING_SUBTITLE", job.get("error"))
        switched = self.client.post(f"/api/bilibili/jobs/{job['id']}/use-whisper")
        self.assertEqual(switched.status_code, 200)
        waiting = self.wait_for(job["id"], {"AWAITING_REVIEW"} | ENDED)
        self.assertEqual((waiting["status"], waiting["subtitle_source"]), ("AWAITING_REVIEW", "whisper"))
        self.assertEqual(len(self.source.requests), 1)                       # không tải lại video
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job['id']}/use-whisper").status_code, 409)

    # ── Sửa và duyệt ──────────────────────────────────────────────────────────
    def test_edit_save_approve_publishes_edited_subtitles(self):
        self.translator.fail_texts = {"Tạm biệt"}
        job = self.start_and_wait({"AWAITING_REVIEW"})
        job_id = job["id"]
        self.assertEqual(job["message"], "Chờ bạn duyệt 2 câu phụ đề tiếng Việt. 1 câu chưa dịch được, cần bạn điền.")
        self.assertEqual(self.cues(job_id).json()["untranslated"], 1)

        url = f"/api/bilibili/jobs/{job_id}/cues"
        saved = self.client.put(url, json={"cues": [
            {"idx": 1, "vi_text": "[vi] Xin chào"},                 # không đổi -> không tính là đã sửa
            {"idx": 2, "vi_text": "  Hẹn gặp\nlại  "}]})
        self.assertEqual(saved.json(), {"changed": 1, "untranslated": 0})
        data = self.cues(job_id).json()["cues"]
        self.assertEqual([(c["vi_text"], c["edited"]) for c in data], [("[vi] Xin chào", False), ("Hẹn gặp lại", True)])

        self.assertEqual(self.client.put(url, json={"cues": [{"idx": 99, "vi_text": "x"}]}).status_code, 400)
        self.assertEqual(self.client.put(url, json={"cues": [{"idx": 1, "vi_text": "x" * 1001}]}).status_code, 400)

        done = self.approve(job_id)
        self.assertEqual(done["status"], "DONE", done.get("error"))
        item = self.client.get(f"/api/bilibili/library/{done['item_id']}").json()
        self.assertTrue(item["has_sub_vi"])
        vtt = self.client.get(f"/api/bilibili/library/{item['id']}/subtitle?kind=vi").text
        self.assertIn("Hẹn gặp lại", vtt)
        self.assertEqual(self.client.put(url, json={"cues": [{"idx": 1, "vi_text": "muộn"}]}).status_code, 409)
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job_id}/approve").status_code, 409)
        self.assertFalse(self.cues(job_id).json()["editable"])

    def test_cannot_approve_when_everything_is_empty(self):
        self.translator.fail_texts = {"Xin chào", "Tạm biệt"}
        job = self.start_and_wait({"AWAITING_REVIEW"})
        refused = self.client.post(f"/api/bilibili/jobs/{job['id']}/approve")
        self.assertEqual((refused.status_code, refused.json()["code"]), (400, "invalid_request"))
        self.assertEqual(self.job(job["id"])["status"], "AWAITING_REVIEW")

    def test_preview_video_supports_range_while_reviewing(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        url = f"/api/bilibili/jobs/{job['id']}/preview"
        part = self.client.get(url, headers={"Range": "bytes=0-9"})
        self.assertEqual((part.status_code, len(part.content)), (206, 10))
        self.approve(job["id"])
        self.assertEqual(self.client.get(url).status_code, 404)               # thư mục làm việc đã được dọn

    def test_waiting_job_can_be_cancelled_retried_and_deleted(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        job_id = job["id"]
        self.assertEqual(self.client.delete(f"/api/bilibili/jobs/{job_id}").status_code, 409)
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job_id}/cancel").json()["status"], "CANCELLED")
        # chạy lại: không tải lại, không dịch lại, quay về đúng bước duyệt với bản đã có
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job_id}/retry").status_code, 200)
        again = self.wait_for(job_id, {"AWAITING_REVIEW"} | ENDED)
        self.assertEqual(again["status"], "AWAITING_REVIEW")
        self.assertEqual((len(self.source.requests), len(self.translator.calls)), (1, 1))
        self.client.post(f"/api/bilibili/jobs/{job_id}/cancel")
        self.assertEqual(self.client.delete(f"/api/bilibili/jobs/{job_id}").status_code, 200)
        self.assertEqual(self.cues(job_id).status_code, 404)                  # câu phụ đề bị xóa theo job
        self.assertEqual(self.container.cue_repo.count(job_id), 0)

    def test_cues_of_unknown_or_early_job(self):
        self.assertEqual(self.cues("job_khong_co").status_code, 404)
        self.assertEqual(self.client.post("/api/bilibili/jobs/job_khong_co/approve").status_code, 404)


if __name__ == "__main__":
    unittest.main()
