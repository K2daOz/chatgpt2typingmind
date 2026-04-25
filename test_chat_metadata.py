"""Unit-Tests fuer Chat-Metadata-Mapping (Sprint 1.1 Feature 1)"""

import unittest
from build_typingmind_export import chatgpt_conv_to_tm


class TestChatMetadataTags(unittest.TestCase):
    def _make_raw(self, **flags):
        return {
            "id": "test-id-123",
            "title": "Test Chat",
            "create_time": 1735689600,
            "update_time": 1735689600,
            "mapping": {},
            **flags,
        }

    def test_no_flags_no_tags(self):
        chat = chatgpt_conv_to_tm(self._make_raw(), None, {}, "", None)
        self.assertNotIn("tags", chat)

    def test_starred_creates_tag(self):
        chat = chatgpt_conv_to_tm(self._make_raw(is_starred=True), None, {}, "", None)
        self.assertIn("tags", chat)
        self.assertIn("starred", chat["tags"])

    def test_pinned_creates_tag(self):
        chat = chatgpt_conv_to_tm(self._make_raw(is_pinned=True), None, {}, "", None)
        self.assertIn("pinned", chat["tags"])

    def test_archived_creates_tag(self):
        chat = chatgpt_conv_to_tm(self._make_raw(is_archived=True), None, {}, "", None)
        self.assertIn("archived", chat["tags"])

    def test_all_flags_all_tags(self):
        chat = chatgpt_conv_to_tm(
            self._make_raw(is_starred=True, is_pinned=True, is_archived=True),
            None, {}, "", None
        )
        self.assertEqual(set(chat["tags"]), {"starred", "pinned", "archived"})

    def test_false_flags_no_tags(self):
        chat = chatgpt_conv_to_tm(
            self._make_raw(is_starred=False, is_pinned=False, is_archived=False),
            None, {}, "", None
        )
        self.assertNotIn("tags", chat)


if __name__ == "__main__":
    unittest.main()
