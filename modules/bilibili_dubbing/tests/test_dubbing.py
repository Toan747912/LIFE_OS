"""Giai đoạn 4: sinh giọng đọc và trộn vào video."""
import json
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

from modules.bilibili_dubbing.domain.errors import JobCancelled
from modules.bilibili_dubbing.dubbing.mixer import DubMixer, MixFailed
from modules.bilibili_dubbing.dubbing.synthesizer import PARTIAL_FILE, Clip, TtsFailed, TtsSynthesizer, speaking_windows
from modules.bilibili_dubbing.media.ffmpeg_tools import FfmpegTools
from modules.bilibili_dubbing.subtitles.document import Cue
from modules.bilibili_dubbing.tests import fakes
from modules.bilibili_dubbing.tests.support import ENDED, FlowTestCase

VOICE = "vi-VN-HoaiMyNeural"


def cue(idx, start_ms, end_ms, text):
    return Cue(idx=idx, start_ms=start_ms, end_ms=end_ms, source_text="x", vi_text=text)


class SpeakingWindowTest(unittest.TestCase):
    def test_window_runs_until_next_cue_but_never_shorter_than_the_cue(self):
        cues = [cue(1, 0, 1000, "a"), cue(2, 3000, 4000, "b"), cue(3, 3500, 5000, "c")]
        self.assertEqual(speaking_windows(cues), {1: 3000, 2: 1000, 3: 1500})


@unittest.skipUnless(fakes.HAS_FFMPEG, "cần ffmpeg")
class TtsSynthesizerTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.out = Path(self._tmp.name) / "tts"
        self.speaker = fakes.FakeSpeaker(ms_per_char=40)
        self.synth = TtsSynthesizer(measure=FfmpegTools().duration_ms, speak=self.speaker, retry_wait_s=0.01)

    def rates(self, text):
        return [rate for spoken, _, rate in self.speaker.calls if spoken == text]

    def test_speeds_up_only_lines_that_overrun_their_window(self):
        fits = "Ngắn thôi"                                   # 9 ký tự = 360 ms trong khung 2000 ms
        tight = "Câu này dài hơn khung một chút thôi nhé"     # 39 ký tự = 1560 ms trong khung 1200 ms -> +30%
        huge = "x" * 100                                      # 4000 ms trong khung 1000 ms -> chạm trần +50%
        clips = self.synth.synthesize(
            [cue(1, 0, 2000, fits), cue(2, 2000, 3200, tight), cue(3, 3200, 4200, huge)], VOICE, self.out)
        self.assertEqual((clips[0].rate, clips[2].rate), ("+0%", "+50%"))
        tight_percent = int(clips[1].rate.strip("+%"))                # mp3 có thêm vài chục ms đệm nên không tròn 30
        self.assertTrue(28 <= tight_percent <= 36, clips[1].rate)
        self.assertEqual(self.rates(fits), ["+0%"])
        self.assertEqual(self.rates(tight), ["+0%", clips[1].rate])
        self.assertEqual(self.rates(huge), ["+0%", "+50%"])
        self.assertLess(clips[1].audio_ms, 1560)
        for clip in clips:
            self.assertGreater((self.out / clip.audio_file).stat().st_size, 0)
            self.assertAlmostEqual(clip.audio_ms, FfmpegTools().duration_ms(self.out / clip.audio_file), delta=5)

    def test_uses_gap_before_next_line_instead_of_speeding_up(self):
        text = "y" * 50                                       # 2000 ms: dài hơn câu (1000 ms) nhưng câu sau cách 3 giây
        clips = self.synth.synthesize([cue(1, 0, 1000, text), cue(2, 3000, 6000, "z")], VOICE, self.out)
        self.assertEqual(clips[0].rate, "+0%")

    def test_skips_empty_lines_and_cleans_text(self):
        clips = self.synth.synthesize(
            [cue(1, 0, 1000, "   "), cue(2, 1000, 2000, "..."), cue(3, 2000, 3000, '"Xin" <chào>')], VOICE, self.out)
        self.assertEqual([(c.idx, c.text) for c in clips], [(3, "Xin chào")])
        self.assertEqual(len(self.speaker.calls), 1)

    def test_retries_network_errors_and_empty_files(self):
        self.speaker.fail_times = {"lỗi mạng": 2}
        self.speaker.empty_times = {"file rỗng": 1}
        clips = self.synth.synthesize([cue(1, 0, 3000, "lỗi mạng"), cue(2, 3000, 6000, "file rỗng")], VOICE, self.out)
        self.assertEqual(len(clips), 2)
        self.assertEqual((len(self.rates("lỗi mạng")), len(self.rates("file rỗng"))), (3, 2))

    def test_gives_up_with_line_number_and_leaves_no_empty_file(self):
        self.speaker.fail_times = {"hỏng": 99}
        with self.assertRaises(TtsFailed) as raised:
            self.synth.synthesize([cue(1, 0, 2000, "ổn"), cue(7, 2000, 4000, "hỏng")], VOICE, self.out)
        self.assertIn("câu số 7", raised.exception.message)
        self.assertEqual(len(self.rates("hỏng")), 3)
        self.assertFalse((self.out / "audio_7.mp3").exists())
        self.assertEqual([p.stat().st_size > 0 for p in self.out.glob("*.mp3")], [True])

    def test_rerun_reuses_finished_lines_and_redoes_changed_ones(self):
        cues = [cue(i, i * 1000, i * 1000 + 900, f"câu {i}") for i in range(1, 15)]
        first = self.synth.synthesize(cues, VOICE, self.out)
        self.assertEqual(len(self.speaker.calls), 14)
        self.assertTrue((self.out / PARTIAL_FILE).is_file())

        self.speaker.calls.clear()
        cues[4].vi_text = "câu đã sửa"
        second = self.synth.synthesize(cues, VOICE, self.out)
        self.assertEqual([c[0] for c in self.speaker.calls], ["câu đã sửa"])
        self.assertEqual([c.audio_file for c in second], [c.audio_file for c in first])

        self.speaker.calls.clear()
        self.synth.synthesize(cues, "vi-VN-NamMinhNeural", self.out)       # đổi giọng: đọc lại tất cả
        self.assertEqual(len(self.speaker.calls), 14)

    def test_interrupted_run_keeps_finished_batches(self):
        cues = [cue(i, i * 1000, i * 1000 + 900, f"câu {i}") for i in range(1, 31)]
        checks = {"n": 0}

        def stop_after_first_batch():
            checks["n"] += 1
            if checks["n"] == 2:
                raise JobCancelled("hủy")

        with self.assertRaises(JobCancelled):
            self.synth.synthesize(cues, VOICE, self.out, should_stop=stop_after_first_batch)
        self.assertEqual(len(self.speaker.calls), 12)                       # đúng một lô
        self.speaker.calls.clear()
        progress = []
        clips = self.synth.synthesize(cues, VOICE, self.out, on_progress=lambda done, total: progress.append((done, total)))
        self.assertEqual((len(clips), len(self.speaker.calls)), (30, 18))   # chỉ đọc nốt 18 câu còn lại
        self.assertEqual((progress[0], progress[-1]), ((12, 30), (30, 30)))


class DubMixerTest(unittest.TestCase):
    def clips(self):
        return [Clip(idx=1, start_ms=500, end_ms=1500, text="a", audio_file="audio_1.mp3", audio_ms=900, rate="+0%"),
                Clip(idx=2, start_ms=2000, end_ms=2500, text="b", audio_file="audio_2.mp3", audio_ms=1400, rate="+50%")]

    def test_audio_map_matches_legacy_mixer_format(self):
        audio_map = DubMixer.to_audio_map(self.clips(), Path("/w/tts"))
        self.assertEqual(audio_map[0]["start"], timedelta(milliseconds=500))
        self.assertEqual(audio_map[0]["end"], timedelta(milliseconds=1500))
        self.assertEqual(audio_map[1]["end"], timedelta(milliseconds=3400))    # clip dài hơn khung: track phải đủ dài
        self.assertEqual(audio_map[1]["audio_path"], str(Path("/w/tts") / "audio_2.mp3"))
        self.assertEqual(set(audio_map[0]), {"index", "start", "end", "duration_ms", "audio_duration_ms", "audio_path", "text"})

    def test_passes_user_settings_and_soft_subtitles(self):
        captured = {}
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "subs.vi.vtt").write_text("WEBVTT\n")

            def fake_mix(**kwargs):
                captured.update(kwargs)
                Path(kwargs["output_video_path"]).write_bytes(b"video")

            out = DubMixer(mix=fake_mix).mix(tmp / "source.mp4", self.clips(), tmp / "tts", tmp / "subs.vi.vtt",
                                             tmp / "dubbed.mp4", orig_vol=0.3, dub_vol=1.4)
            self.assertEqual(out, tmp / "dubbed.mp4")
        self.assertEqual((captured["orig_vol"], captured["dub_vol"], captured["hard_sub"], captured["enable_dynamic_sub"]),
                         (0.3, 1.4, False, False))
        self.assertTrue(captured["vtt_path"].endswith("subs.vi.vtt"))

    def test_error_mapping(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)

            def ffmpeg_fails(**kwargs):
                Path(kwargs["output_video_path"]).write_bytes(b"dang do")
                raise subprocess.CalledProcessError(1, ["ffmpeg"])

            with self.assertRaises(MixFailed) as raised:
                DubMixer(mix=ffmpeg_fails).mix(tmp / "s.mp4", self.clips(), tmp, None, tmp / "d.mp4", 0.15, 1.0)
            self.assertIn("mã 1", raised.exception.message)
            self.assertFalse((tmp / "d.mp4").exists())                         # không để lại file dở dang
            with self.assertRaises(MixFailed):
                DubMixer(mix=lambda **kwargs: None).mix(tmp / "s.mp4", self.clips(), tmp, None, tmp / "d.mp4", 0.15, 1.0)
            with self.assertRaises(MixFailed):
                DubMixer(mix=lambda **kwargs: None).mix(tmp / "s.mp4", [], tmp, None, tmp / "d.mp4", 0.15, 1.0)


class DubbingFlowTest(FlowTestCase):
    def streams(self, path):
        out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,codec_name",
                              "-of", "json", str(path)], capture_output=True, text=True).stdout
        return [(s["codec_type"], s["codec_name"]) for s in json.loads(out)["streams"]]

    def test_full_pipeline_produces_dubbed_video_with_soft_subtitles(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        done = self.approve(job["id"])
        self.assertEqual(done["status"], "DONE", done.get("error"))
        item = self.client.get(f"/api/bilibili/library/{done['item_id']}").json()
        self.assertEqual((item["dubbed"], item["voice"], item["has_source"], item["has_sub_vi"]),
                         (True, "vi-VN-HoaiMyNeural", False, True))
        video = self.data_dir / "library" / item["id"] / "video.mp4"
        # Bộ trộn thật của LIFE_OS: hình được sao chép (không encode lại), tiếng trộn AAC, phụ đề mềm nhúng sẵn.
        self.assertEqual(self.streams(video), [("video", "h264"), ("audio", "aac"), ("subtitle", "mov_text")])
        self.assertEqual(sorted(p.name for p in video.parent.iterdir()), ["subs.orig.vtt", "subs.vi.vtt", "video.mp4"])
        # Hàm làm sạch của pipeline cũ bỏ dấu ngoặc vuông trước khi đọc.
        self.assertEqual(sorted(c[0] for c in self.speaker.calls if c[2] == "+0%"), ["vi Tạm biệt", "vi Xin chào"])
        self.assertEqual(self.client.get(f"/api/bilibili/library/{item['id']}/stream?kind=source").status_code, 404)
        self.assertFalse((self.data_dir / "work" / job["id"]).exists())

    def test_edited_text_is_what_gets_spoken(self):
        job = self.start_and_wait({"AWAITING_REVIEW"})
        self.client.put(f"/api/bilibili/jobs/{job['id']}/cues", json={"cues": [
            {"idx": 1, "vi_text": "Chào cả nhà"}, {"idx": 2, "vi_text": ""}]})
        self.assertEqual(self.approve(job["id"])["status"], "DONE")
        self.assertEqual({c[0] for c in self.speaker.calls}, {"Chào cả nhà"})   # câu để trống không được đọc

    def test_keep_source_and_voice_and_volume_choices(self):
        captured = {}

        def fake_mix(**kwargs):
            captured.update(kwargs)
            Path(kwargs["output_video_path"]).write_bytes(b"ban long tieng")

        self.mix = fake_mix
        self.container_module.set_container(self.new_container())
        job = self.start_and_wait({"AWAITING_REVIEW"}, keep_source=True, voice="vi-VN-NamMinhNeural",
                                  orig_vol=0.05, dub_vol=1.5)
        done = self.approve(job["id"])
        self.assertEqual(done["status"], "DONE", done.get("error"))
        self.assertEqual((captured["orig_vol"], captured["dub_vol"]), (0.05, 1.5))
        self.assertEqual({c[1] for c in self.speaker.calls}, {"vi-VN-NamMinhNeural"})
        item = self.client.get(f"/api/bilibili/library/{done['item_id']}").json()
        self.assertEqual((item["has_source"], item["voice"]), (True, "vi-VN-NamMinhNeural"))
        base = f"/api/bilibili/library/{item['id']}"
        self.assertEqual(self.client.get(base + "/stream").content, b"ban long tieng")
        source = self.client.get(base + "/stream?kind=source")
        self.assertEqual(source.status_code, 200)
        self.assertGreater(len(source.content), 1000)
        self.assertIn("g%E1%BB%91c", self.client.get(base + "/download?kind=source").headers["content-disposition"])

    def test_tts_failure_then_retry_only_speaks_missing_lines(self):
        self.speaker.fail_times = {"vi Tạm biệt": 3}
        job = self.start_and_wait({"AWAITING_REVIEW"})
        failed = self.approve(job["id"])
        self.assertEqual(failed["status"], "FAILED")
        self.assertIn("câu số 2", failed["error"])
        self.assertEqual(self.client.get("/api/bilibili/library").json()["items"], [])

        self.speaker.calls.clear()
        self.client.post(f"/api/bilibili/jobs/{job['id']}/retry")
        done = self.wait_for(job["id"], ENDED)
        self.assertEqual(done["status"], "DONE", done.get("error"))
        self.assertEqual({c[0] for c in self.speaker.calls}, {"vi Tạm biệt"})     # câu 1 không bị đọc lại

    def test_mix_failure_then_retry_does_not_resynthesize(self):
        state = {"fail": True}
        from modules.bilibili_dubbing.dubbing.mixer import legacy_mix

        def flaky_mix(**kwargs):
            if state["fail"]:
                raise subprocess.CalledProcessError(1, ["ffmpeg"])
            legacy_mix(**kwargs)

        self.mix = flaky_mix
        self.container_module.set_container(self.new_container())
        job = self.start_and_wait({"AWAITING_REVIEW"})
        failed = self.approve(job["id"])
        self.assertEqual((failed["status"], failed["stage"]), ("FAILED", "mix"))
        self.assertIn("FFmpeg", failed["error"])
        spoken = len(self.speaker.calls)
        state["fail"] = False
        self.client.post(f"/api/bilibili/jobs/{job['id']}/retry")
        self.assertEqual(self.wait_for(job["id"], ENDED)["status"], "DONE")
        self.assertEqual(len(self.speaker.calls), spoken)

    def test_cancel_while_synthesizing(self):
        import asyncio
        import threading

        started, release = threading.Event(), threading.Event()
        original = self.speaker.__call__

        async def slow_speak(text, voice, rate, path):
            started.set()
            while not release.is_set():
                await asyncio.sleep(0.02)
            await original(text, voice, rate, path)

        self.container.synthesizer._speak = slow_speak
        job = self.start_and_wait({"AWAITING_REVIEW"})
        self.client.post(f"/api/bilibili/jobs/{job['id']}/approve")
        self.assertTrue(started.wait(10))
        self.assertEqual(self.job(job["id"])["status"], "SYNTHESIZING")
        self.assertEqual(self.client.post(f"/api/bilibili/jobs/{job['id']}/cancel").status_code, 200)
        release.set()
        self.assertEqual(self.wait_for(job["id"], ENDED)["status"], "CANCELLED")
        self.assertEqual(self.client.get("/api/bilibili/library").json()["items"], [])


if __name__ == "__main__":
    unittest.main()
