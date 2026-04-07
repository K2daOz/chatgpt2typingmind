"""Unit-Tests fuer license.py"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from license import (
    activate,
    get_license_path,
    is_pro,
    load_cached_license,
    save_license_cache,
    validate_online,
    LicenseError,
    FREE_CHAT_LIMIT,
    GUMROAD_PRODUCT_ID,
)


class TestFreeChatLimit(unittest.TestCase):
    def test_free_chat_limit_is_100(self):
        self.assertEqual(FREE_CHAT_LIMIT, 100)

    def test_product_id_set(self):
        self.assertTrue(len(GUMROAD_PRODUCT_ID) > 0, "Product ID must be configured")


class TestLicensePath(unittest.TestCase):
    def test_returns_path_object(self):
        path = get_license_path()
        self.assertIsInstance(path, Path)

    def test_path_ends_with_license(self):
        path = get_license_path()
        self.assertEqual(path.name, ".license")


class TestCacheReadWrite(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.license_path = Path(self.tmpdir) / ".license"

    def tearDown(self):
        if self.license_path.exists():
            self.license_path.unlink()

    @patch("license.get_license_path")
    def test_save_and_load(self, mock_path):
        mock_path.return_value = self.license_path
        data = {
            "license_key": "TEST-KEY-1234",
            "validated_at": "2026-04-01T00:00:00+00:00",
            "email": "test@example.com",
            "uses": 1,
        }
        save_license_cache(data)
        loaded = load_cached_license()
        self.assertEqual(loaded["license_key"], "TEST-KEY-1234")
        self.assertEqual(loaded["email"], "test@example.com")

    @patch("license.get_license_path")
    def test_load_nonexistent(self, mock_path):
        mock_path.return_value = Path(self.tmpdir) / "nonexistent"
        self.assertIsNone(load_cached_license())

    @patch("license.get_license_path")
    def test_load_corrupt_json(self, mock_path):
        mock_path.return_value = self.license_path
        self.license_path.write_text("{invalid json", encoding="utf-8")
        self.assertIsNone(load_cached_license())

    @patch("license.get_license_path")
    def test_load_missing_fields(self, mock_path):
        mock_path.return_value = self.license_path
        self.license_path.write_text('{"foo": "bar"}', encoding="utf-8")
        self.assertIsNone(load_cached_license())

    @patch("license.get_license_path")
    def test_load_empty_file(self, mock_path):
        mock_path.return_value = self.license_path
        self.license_path.write_text("", encoding="utf-8")
        self.assertIsNone(load_cached_license())


class TestValidateOnline(unittest.TestCase):
    def test_empty_key_rejected(self):
        with self.assertRaises(LicenseError):
            validate_online("")

    def test_whitespace_key_rejected(self):
        with self.assertRaises(LicenseError):
            validate_online("   ")

    @patch("license.GUMROAD_PRODUCT_ID", "")
    def test_missing_product_id(self):
        with self.assertRaises(LicenseError) as ctx:
            validate_online("SOME-KEY")
        self.assertIn("Product ID", str(ctx.exception))


class TestActivate(unittest.TestCase):
    @patch("license.validate_online")
    @patch("license.save_license_cache")
    def test_success(self, mock_save, mock_validate):
        mock_validate.return_value = {
            "success": True,
            "purchase": {"email": "buyer@example.com"},
            "uses": 1,
        }
        success, msg = activate("VALID-KEY-1234")
        self.assertTrue(success)
        self.assertEqual(msg, "buyer@example.com")
        mock_save.assert_called_once()

    @patch("license.validate_online")
    def test_failure(self, mock_validate):
        mock_validate.side_effect = LicenseError("Invalid key")
        success, msg = activate("BAD-KEY")
        self.assertFalse(success)
        self.assertIn("Invalid key", msg)

    def test_empty_key(self):
        success, msg = activate("")
        self.assertFalse(success)


class TestIsPro(unittest.TestCase):
    @patch("license.load_cached_license")
    def test_no_cache(self, mock_load):
        mock_load.return_value = None
        self.assertFalse(is_pro())

    @patch("license.load_cached_license")
    def test_fresh_cache(self, mock_load):
        mock_load.return_value = {
            "license_key": "KEY",
            "validated_at": "2026-04-07T00:00:00+00:00",
            "email": "test@example.com",
        }
        self.assertTrue(is_pro())

    @patch("license.validate_online")
    @patch("license.save_license_cache")
    @patch("license.load_cached_license")
    def test_stale_cache_revalidates(self, mock_load, mock_save, mock_validate):
        mock_load.return_value = {
            "license_key": "KEY",
            "validated_at": "2025-01-01T00:00:00+00:00",  # > 30 days old
            "email": "test@example.com",
        }
        mock_validate.return_value = {"success": True}
        self.assertTrue(is_pro())

    @patch("license.validate_online")
    @patch("license.load_cached_license")
    def test_stale_cache_offline_still_pro(self, mock_load, mock_validate):
        mock_load.return_value = {
            "license_key": "KEY",
            "validated_at": "2025-01-01T00:00:00+00:00",
            "email": "test@example.com",
        }
        mock_validate.side_effect = LicenseError("Network error")
        self.assertTrue(is_pro())  # Offline grace period


if __name__ == "__main__":
    unittest.main()
