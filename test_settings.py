"""Unit-Tests fuer settings.py"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from settings import (
    load_settings, save_settings, get, set_value,
    _obfuscate, _deobfuscate, SENSITIVE_FIELDS,
)


class TestObfuscation(unittest.TestCase):
    def test_roundtrip(self):
        original = "my-secret-key-1234"
        obf = _obfuscate(original)
        self.assertTrue(obf.startswith("b64:"))
        self.assertNotEqual(obf, original)
        self.assertEqual(_deobfuscate(obf), original)

    def test_empty_string(self):
        self.assertEqual(_obfuscate(""), "")
        self.assertEqual(_deobfuscate(""), "")

    def test_plaintext_passthrough(self):
        # Wenn kein b64: Praefix, wird Plaintext zurueckgegeben
        self.assertEqual(_deobfuscate("plain"), "plain")

    def test_invalid_b64(self):
        # Ungueltiges b64 sollte leeren String liefern
        self.assertEqual(_deobfuscate("b64:!!!"), "")


class TestLoadSave(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.path = Path(self.tmpdir) / ".settings.json"

    @patch("settings.get_settings_path")
    def test_save_and_load(self, mock_path):
        mock_path.return_value = self.path
        save_settings({"language": "de", "r2_bucket": "test-bucket"})
        loaded = load_settings()
        self.assertEqual(loaded["language"], "de")
        self.assertEqual(loaded["r2_bucket"], "test-bucket")

    @patch("settings.get_settings_path")
    def test_sensitive_fields_obfuscated_on_disk(self, mock_path):
        mock_path.return_value = self.path
        save_settings({"r2_secret_access_key": "super-secret"})
        # Auf Disk sollte obfuskiert sein
        raw = self.path.read_text(encoding="utf-8")
        self.assertNotIn("super-secret", raw)
        self.assertIn("b64:", raw)
        # Beim Laden wieder Plaintext
        loaded = load_settings()
        self.assertEqual(loaded["r2_secret_access_key"], "super-secret")

    @patch("settings.get_settings_path")
    def test_load_nonexistent(self, mock_path):
        mock_path.return_value = Path(self.tmpdir) / "nope.json"
        self.assertEqual(load_settings(), {})

    @patch("settings.get_settings_path")
    def test_load_corrupt(self, mock_path):
        mock_path.return_value = self.path
        self.path.write_text("{invalid", encoding="utf-8")
        self.assertEqual(load_settings(), {})

    @patch("settings.get_settings_path")
    def test_get_with_default(self, mock_path):
        mock_path.return_value = self.path
        self.assertEqual(get("missing", "fallback"), "fallback")
        save_settings({"existing": "value"})
        self.assertEqual(get("existing"), "value")

    @patch("settings.get_settings_path")
    def test_set_value(self, mock_path):
        mock_path.return_value = self.path
        set_value("key1", "value1")
        set_value("key2", "value2")
        loaded = load_settings()
        self.assertEqual(loaded["key1"], "value1")
        self.assertEqual(loaded["key2"], "value2")


class TestSensitiveFields(unittest.TestCase):
    def test_secret_keys_in_sensitive_list(self):
        self.assertIn("r2_secret_access_key", SENSITIVE_FIELDS)
        self.assertIn("r2_access_key_id", SENSITIVE_FIELDS)


if __name__ == "__main__":
    unittest.main()
