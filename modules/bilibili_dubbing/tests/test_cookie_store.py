import json
import tempfile
import time
import unittest
from http.cookiejar import MozillaCookieJar
from pathlib import Path

from modules.bilibili_dubbing.domain.errors import InvalidRequest
from modules.bilibili_dubbing.storage.cookie_store import CookieStore

NETSCAPE = "\n".join([
    "# Netscape HTTP Cookie File",
    ".bilibili.tv\tTRUE\t/\tTRUE\t1999999999\tSESSDATA\tsecret-tv",
    "#HttpOnly_.bilibili.tv\tTRUE\t/\tTRUE\t1999999999\tbili_jct\tcsrf",
    ".google.com\tTRUE\t/\tTRUE\t1999999999\tSID\tother-site-secret",
    "www.bilibili.com\tFALSE\t/\tFALSE\t0\tbuvid3\tabc",
])


class CookieStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.store = CookieStore(Path(self._tmp.name) / "sub" / "cookies.txt")

    def test_empty_status(self):
        self.assertEqual(self.store.status()["configured"], False)

    def test_netscape_keeps_only_bilibili_cookies(self):
        status = self.store.save_from_text(NETSCAPE)
        self.assertEqual(status["cookie_count"], 3)
        self.assertEqual(status["sites"], ["bilibili.com", "bilibili.tv"])
        self.assertTrue(status["has_login_cookie"])
        self.assertFalse(status["expired"])
        saved = self.store.path.read_text(encoding="utf-8")
        self.assertNotIn("google", saved)
        self.assertNotIn("other-site-secret", saved)
        self.assertNotIn("#HttpOnly_", saved)

    def test_saved_file_loads_with_standard_cookie_jar(self):
        self.store.save_from_text(NETSCAPE)
        jar = MozillaCookieJar(str(self.store.path))
        jar.load(ignore_discard=True, ignore_expires=True)
        self.assertEqual({c.name for c in jar}, {"SESSDATA", "bili_jct", "buvid3"})

    def test_status_never_contains_values(self):
        status = self.store.save_from_text(NETSCAPE)
        self.assertNotIn("secret-tv", json.dumps(status))

    def test_json_export_format(self):
        exported = json.dumps([
            {"domain": ".bilibili.com", "name": "SESSDATA", "value": "v", "path": "/", "secure": True,
             "expirationDate": 1999999999.5},
            {"domain": ".example.com", "name": "x", "value": "y"},
        ])
        status = self.store.save_from_text(exported)
        self.assertEqual((status["cookie_count"], status["expires_at"]), (1, 1999999999))

    def test_header_string_uses_selected_site(self):
        status = self.store.save_from_text("Cookie: SESSDATA=abc%2C123; bili_jct=xyz", "bilibili.tv")
        self.assertEqual((status["cookie_count"], status["sites"]), (2, ["bilibili.tv"]))
        self.assertGreater(status["expires_at"], time.time())

    def test_bare_value_becomes_sessdata(self):
        status = self.store.save_from_text("  abc%2C123%2Cdef  ", "bilibili.com")
        self.assertTrue(status["has_login_cookie"])
        self.assertIn("\tSESSDATA\tabc%2C123%2Cdef", self.store.path.read_text(encoding="utf-8"))

    def test_expired_cookie_is_reported(self):
        status = self.store.save_from_text(".bilibili.com\tTRUE\t/\tTRUE\t1000\tSESSDATA\told")
        self.assertTrue(status["expired"])

    def test_rejects_bad_input(self):
        for text, site in (("", "bilibili.com"), ("   ", "bilibili.com"), ("abc", "evil.com"),
                           ("hai tu", "bilibili.com"), (".google.com\tTRUE\t/\tTRUE\t0\ta\tb", "bilibili.com"),
                           ("[not json", "bilibili.com"), ("x" * 200_001, "bilibili.com")):
            with self.assertRaises(InvalidRequest, msg=text[:20]):
                self.store.save_from_text(text, site)
        self.assertFalse(self.store.path.exists())

    def test_lookalike_domains_are_dropped(self):
        with self.assertRaises(InvalidRequest):
            self.store.save_from_text(".evilbilibili.com\tTRUE\t/\tTRUE\t0\tSESSDATA\tv")

    def test_clear(self):
        self.store.save_from_text("abc")
        self.assertFalse(self.store.clear()["configured"])
        self.assertFalse(self.store.path.exists())
        self.assertFalse(self.store.clear()["configured"])


if __name__ == "__main__":
    unittest.main()
