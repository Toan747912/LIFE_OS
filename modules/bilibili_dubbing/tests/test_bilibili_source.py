import unittest

from modules.bilibili_dubbing.domain.errors import AccessDenied, ContentUnavailable, ScanFailed
from modules.bilibili_dubbing.sources.bilibili import BilibiliSource
from modules.bilibili_dubbing.tests import fakes


class UrlHandlingTest(unittest.TestCase):
    def setUp(self):
        self.source = BilibiliSource(extractor=fakes.fake_extractor)

    def test_accepts_bilibili_hosts_and_bv_id(self):
        for url in (
            "https://www.bilibili.com/video/BV1xx411c7mD",
            "www.bilibili.com/video/BV1xx411c7mD",
            "https://b23.tv/abc123",
            "https://www.bilibili.tv/vi/video/123",
            "BV1xx411c7mD",
        ):
            self.assertTrue(self.source.can_handle(url), url)

    def test_rejects_other_hosts(self):
        for url in (
            "https://www.youtube.com/watch?v=1",
            "https://evil-bilibili.com/video/BV1",
            "https://bilibili.com.evil.io/x",
            "file:///etc/passwd",
            "ftp://bilibili.com/x",
        ):
            self.assertFalse(self.source.can_handle(url), url)

    def test_normalize_bv_id(self):
        self.assertEqual(self.source.normalize(" BV1xx411c7mD "), "https://www.bilibili.com/video/BV1xx411c7mD")


class FormatMappingTest(unittest.TestCase):
    def setUp(self):
        self.options = BilibiliSource.build_format_options(fakes.video_info()["formats"], 600)

    def test_groups_by_height_and_codec_keeping_best_bitrate(self):
        keys = [(o.height, o.codec) for o in self.options]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), {(1080, "avc"), (1080, "hevc"), (1080, "av1"), (480, "avc")})
        low = next(o for o in self.options if o.height == 480)
        self.assertEqual(low.format_id, "30032")

    def test_playable_format_listed_first_within_same_height(self):
        self.assertEqual((self.options[0].height, self.options[0].codec), (1080, "avc"))
        self.assertTrue(self.options[0].browser_playable)
        self.assertFalse(next(o for o in self.options if o.codec == "hevc").browser_playable)

    def test_selector_adds_audio_for_video_only_streams(self):
        self.assertEqual(self.options[0].selector, "30080+bestaudio")

    def test_size_includes_best_audio(self):
        audio = int(192 * 1000 / 8 * 600)
        self.assertEqual(self.options[0].size_bytes, 150_000_000 + audio)

    def test_muxed_stream_selector_and_missing_size(self):
        options = BilibiliSource.build_format_options(
            [{"format_id": "mp4-720", "vcodec": "avc1", "acodec": "mp4a", "height": 720, "ext": "mp4"}], None)
        self.assertEqual(options[0].selector, "mp4-720")
        self.assertIsNone(options[0].size_bytes)

    def test_fps_shown_only_above_30(self):
        self.assertIn("60fps", next(o for o in self.options if o.codec == "av1").label)
        self.assertNotIn("fps", self.options[0].label)


class SubtitleMappingTest(unittest.TestCase):
    def test_excludes_danmaku_and_marks_ai_tracks(self):
        tracks = BilibiliSource.build_subtitle_tracks(fakes.video_info()["subtitles"], {})
        self.assertEqual([t.lang for t in tracks], ["zh-CN", "ai-zh"])
        self.assertEqual([t.kind for t in tracks], ["uploaded", "auto"])
        self.assertIn("AI", tracks[1].name)

    def test_only_danmaku_means_no_subtitles(self):
        self.assertEqual(BilibiliSource.build_subtitle_tracks({"danmaku": [{"ext": "xml"}]}, {}), [])


class ScanTest(unittest.TestCase):
    def setUp(self):
        self.source = BilibiliSource(extractor=fakes.fake_extractor)

    def test_single_video(self):
        result = self.source.scan(fakes.SINGLE_URL, max_probe=5)
        self.assertTrue(result.ok)
        self.assertEqual(result.kind, "video")
        self.assertEqual(len(result.episodes), 1)
        episode = result.episodes[0]
        self.assertTrue(episode.probed and episode.accessible)
        self.assertEqual(episode.duration_s, 600)

    def test_series_isolates_failing_episode_and_respects_probe_limit(self):
        result = self.source.scan(fakes.SERIES_URL, max_probe=2)
        self.assertEqual(result.kind, "playlist")
        first, second, third = result.episodes
        self.assertTrue(first.probed and first.accessible)
        self.assertTrue(second.probed)
        self.assertFalse(second.accessible)
        self.assertEqual(second.error_code, "access_denied")
        self.assertFalse(third.probed)
        self.assertEqual(third.title, "Tập 3")

    def test_probe_fills_unprobed_episode(self):
        result = self.source.scan(fakes.SERIES_URL, max_probe=0)
        episode = self.source.probe(result.episodes[2])
        self.assertTrue(episode.probed and episode.accessible)
        self.assertEqual(episode.title, "Series mẫu p3")

    def test_no_formats_marks_episode_inaccessible(self):
        source = BilibiliSource(extractor=lambda url, flat: {"title": "x", "formats": []})
        episode = source.scan(fakes.SINGLE_URL, 1).episodes[0]
        self.assertFalse(episode.accessible)
        self.assertEqual(episode.error_code, "access_denied")


class YtDlpOptionsTest(unittest.TestCase):
    """yt-dlp chỉ trả phụ đề khi được yêu cầu: thiếu cờ thì mọi video đều hiện 'không có phụ đề'."""

    def test_requests_subtitles_without_downloading(self):
        try:
            import yt_dlp
        except ImportError:
            self.skipTest("chưa cài yt-dlp")
        captured = {}

        class FakeYDL:
            def __init__(self, options):
                captured.update(options)

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download):
                captured["download"] = download
                return {"title": "x", "formats": []}

            def sanitize_info(self, info):
                return info

        original = yt_dlp.YoutubeDL
        yt_dlp.YoutubeDL = FakeYDL
        self.addCleanup(setattr, yt_dlp, "YoutubeDL", original)
        BilibiliSource()._extract_with_ytdlp(fakes.SINGLE_URL, False)
        self.assertTrue(captured["writesubtitles"])
        self.assertTrue(captured["writeautomaticsub"])
        self.assertTrue(captured["skip_download"])
        self.assertFalse(captured["download"])


class DurationTest(unittest.TestCase):
    def test_estimates_duration_when_site_gives_none(self):
        info = {"title": "x", "formats": [
            {"format_id": "1", "vcodec": "avc1", "acodec": "none", "height": 720, "tbr": 1000, "filesize": 125_000_000}]}
        episode = BilibiliSource(extractor=lambda url, flat: info).scan(fakes.SINGLE_URL, 1).episodes[0]
        self.assertEqual((episode.duration_s, episode.duration_estimated), (1000, True))

    def test_bitrate_given_in_bits_per_second_is_converted(self):
        # bilibili.tv: yt-dlp đưa "bandwidth" (bit/giây) vào vbr. 125 MB ở 700 kbps là khoảng 24 phút.
        info = {"title": "x", "formats": [
            {"format_id": "v", "vcodec": "avc1", "acodec": "none", "height": 720, "vbr": 700_000, "filesize": 125_000_000},
            {"format_id": "lo", "vcodec": "avc1", "acodec": "none", "height": 720, "vbr": 300_000, "filesize": 50_000_000},
            {"format_id": "a", "vcodec": "none", "acodec": "mp4a", "abr": 128_000, "filesize": 20_000_000}]}
        episode = BilibiliSource(extractor=lambda url, flat: info).scan(fakes.SINGLE_URL, 1).episodes[0]
        self.assertEqual(episode.duration_s, 1428)
        self.assertTrue(episode.duration_estimated)
        self.assertEqual(episode.formats[0].format_id, "v")
        self.assertEqual(episode.formats[0].size_bytes, 145_000_000)

    def test_implausible_estimate_is_dropped(self):
        info = {"title": "x", "formats": [
            {"format_id": "v", "vcodec": "avc1", "acodec": "none", "height": 720, "tbr": 90_000, "filesize": 1_000_000}]}
        episode = BilibiliSource(extractor=lambda url, flat: info).scan(fakes.SINGLE_URL, 1).episodes[0]
        self.assertIsNone(episode.duration_s)
        self.assertFalse(episode.duration_estimated)

    def test_real_duration_is_not_marked_estimated(self):
        episode = BilibiliSource(extractor=fakes.fake_extractor).scan(fakes.SINGLE_URL, 1).episodes[0]
        self.assertEqual((episode.duration_s, episode.duration_estimated), (600, False))


class ErrorClassificationTest(unittest.TestCase):
    def test_maps_messages_to_error_types(self):
        cases = {
            "ERROR: [BiliBili] 1: This video is geo restricted": AccessDenied,
            "ERROR: This video is for premium members only": AccessDenied,
            "ERROR: You have to login or become premium": AccessDenied,
            "ERROR: This video is DRM protected": AccessDenied,
            "ERROR: Unable to download JSON metadata: HTTP Error 404: Not Found": ContentUnavailable,
            "ERROR: Unsupported URL: https://www.bilibili.com/": ContentUnavailable,
            "ERROR: \x1b[0;31msomething odd\x1b[0m": ScanFailed,
            "ERROR: Unable to download webpage: ('Unable to connect to proxy', OSError())": ScanFailed,
        }
        for message, expected in cases.items():
            self.assertIsInstance(BilibiliSource.classify_error(message), expected, message)

    def test_network_error_has_friendly_message_and_drops_report_hint(self):
        network = BilibiliSource.classify_error("ERROR: Unable to download webpage: The read operation timed out")
        self.assertIn("kiểm tra mạng", network.message)
        other = BilibiliSource.classify_error("ERROR: weird failure; please report this issue on https://x")
        self.assertNotIn("please report", other.message)

    def test_strips_ansi_codes(self):
        error = BilibiliSource.classify_error("\x1b[0;31mERROR:\x1b[0m boom")
        self.assertNotIn("\x1b", error.message)


if __name__ == "__main__":
    unittest.main()
