"""Unit-Tests fuer manifest.py"""

import json
import tempfile
import unittest
from pathlib import Path

from manifest import (
    create_empty_manifest,
    load_manifest,
    save_manifest,
    get_imported_ids,
    compute_delta,
    update_manifest,
    MANIFEST_VERSION,
)


class TestCreateEmpty(unittest.TestCase):
    def test_has_version(self):
        m = create_empty_manifest()
        self.assertEqual(m["version"], MANIFEST_VERSION)

    def test_empty_ids(self):
        m = create_empty_manifest()
        self.assertEqual(m["imported_chat_ids"], [])
        self.assertEqual(m["tm_native_ids"], [])

    def test_has_runs(self):
        m = create_empty_manifest()
        self.assertIsInstance(m["runs"], list)


class TestLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir) / "manifest.json"

    def test_save_and_load(self):
        m = create_empty_manifest()
        m["imported_chat_ids"] = ["id1", "id2"]
        save_manifest(self.path, m)
        loaded = load_manifest(self.path)
        self.assertEqual(loaded["imported_chat_ids"], ["id1", "id2"])

    def test_load_nonexistent(self):
        m = load_manifest(Path(self.tmpdir) / "nope.json")
        self.assertEqual(m["version"], MANIFEST_VERSION)
        self.assertEqual(m["imported_chat_ids"], [])

    def test_load_corrupt_creates_backup(self):
        self.path.write_text("{corrupt", encoding="utf-8")
        m = load_manifest(self.path)
        self.assertEqual(m["imported_chat_ids"], [])
        bak = self.path.with_suffix(".json.bak")
        self.assertTrue(bak.exists())

    def test_load_wrong_version_warns(self):
        data = create_empty_manifest()
        data["version"] = "0.0.0"
        self.path.write_text(json.dumps(data), encoding="utf-8")
        m = load_manifest(self.path)
        # Should still load, just warn
        self.assertEqual(m["version"], "0.0.0")


class TestGetImportedIds(unittest.TestCase):
    def test_returns_set(self):
        m = create_empty_manifest()
        m["imported_chat_ids"] = ["a", "b", "c"]
        ids = get_imported_ids(m)
        self.assertIsInstance(ids, set)
        self.assertEqual(ids, {"a", "b", "c"})

    def test_empty_manifest(self):
        m = create_empty_manifest()
        self.assertEqual(get_imported_ids(m), set())


class TestComputeDelta(unittest.TestCase):
    def test_all_new(self):
        m = create_empty_manifest()
        delta = compute_delta(["a", "b", "c"], m)
        self.assertEqual(set(delta), {"a", "b", "c"})

    def test_some_new(self):
        m = create_empty_manifest()
        m["imported_chat_ids"] = ["a", "b"]
        delta = compute_delta(["a", "b", "c", "d"], m)
        self.assertEqual(set(delta), {"c", "d"})

    def test_none_new(self):
        m = create_empty_manifest()
        m["imported_chat_ids"] = ["a", "b"]
        delta = compute_delta(["a", "b"], m)
        self.assertEqual(delta, [])


class TestUpdateManifest(unittest.TestCase):
    def test_adds_new_ids(self):
        m = create_empty_manifest()
        updated = update_manifest(m, ["id1", "id2"], [], "full", 2)
        self.assertIn("id1", updated["imported_chat_ids"])
        self.assertIn("id2", updated["imported_chat_ids"])

    def test_records_run(self):
        m = create_empty_manifest()
        updated = update_manifest(m, ["id1"], [], "full", 1)
        self.assertEqual(len(updated["runs"]), 1)
        self.assertEqual(updated["runs"][0]["mode"], "full")

    def test_updates_stats(self):
        m = create_empty_manifest()
        updated = update_manifest(m, ["a", "b"], ["tm1"], "full", 2)
        self.assertEqual(updated["stats"]["chatgpt"], 2)
        self.assertEqual(updated["stats"]["tm_native"], 1)


if __name__ == "__main__":
    unittest.main()
