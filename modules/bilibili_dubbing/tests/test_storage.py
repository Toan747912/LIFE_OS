import sqlite3
import tempfile
import unittest
from pathlib import Path

from modules.bilibili_dubbing.domain.errors import NotFound
from modules.bilibili_dubbing.domain.models import ScanResult
from modules.bilibili_dubbing.sources.bilibili import BilibiliSource
from modules.bilibili_dubbing.storage.database import MIGRATIONS, Database
from modules.bilibili_dubbing.storage.repositories import ScanRepository, SettingsRepository
from modules.bilibili_dubbing.tests import fakes


class StorageTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.db = Database(Path(self._tmp.name) / "nested" / "test.db")


class DatabaseTest(StorageTestCase):
    def test_creates_schema_and_is_idempotent(self):
        self.assertEqual(self.db.schema_version(), len(MIGRATIONS))
        again = Database(self.db.path)
        self.assertEqual(again.schema_version(), len(MIGRATIONS))
        with again.connect() as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"settings", "scans", "jobs", "cues", "library_items", "series", "tags", "item_tags"} <= tables)

    def test_rolls_back_on_error(self):
        with self.assertRaises(sqlite3.IntegrityError):
            with self.db.connect() as conn:
                conn.execute("INSERT INTO settings(key, value) VALUES('a', '1')")
                conn.execute("INSERT INTO settings(key, value) VALUES('a', '2')")
        self.assertIsNone(SettingsRepository(self.db).get("a"))


class SettingsRepositoryTest(StorageTestCase):
    def test_set_get_overwrite(self):
        repo = SettingsRepository(self.db)
        self.assertEqual(repo.get("voice", "default"), "default")
        repo.set("voice", "a")
        repo.set("voice", "b")
        self.assertEqual(repo.get("voice"), "b")
        self.assertEqual(repo.all(), {"voice": "b"})


class ScanRepositoryTest(StorageTestCase):
    def _scan(self, scan_id: str, created_at: str = "2026-10-05T00:00:00+00:00") -> ScanResult:
        source = BilibiliSource(extractor=fakes.fake_extractor)
        return ScanResult(scan_id=scan_id, created_at=created_at, cookie_configured=False,
                          results=[source.scan(fakes.SERIES_URL, 2)])

    def test_round_trip_preserves_nested_objects(self):
        repo = ScanRepository(self.db)
        original = self._scan("sc_1")
        repo.save(original)
        loaded = repo.get("sc_1")
        self.assertEqual(loaded.to_dict(), original.to_dict())
        self.assertEqual(loaded.results[0].episodes[0].formats[0].codec, "avc")

    def test_missing_scan_raises_not_found(self):
        with self.assertRaises(NotFound):
            ScanRepository(self.db).get("nope")

    def test_keeps_only_latest_scans(self):
        repo = ScanRepository(self.db)
        repo.KEEP_LATEST = 3
        for n in range(5):
            repo.save(self._scan(f"sc_{n}", f"2026-10-05T00:00:0{n}+00:00"))
        with self.assertRaises(NotFound):
            repo.get("sc_0")
        self.assertEqual(repo.get("sc_4").scan_id, "sc_4")


if __name__ == "__main__":
    unittest.main()
