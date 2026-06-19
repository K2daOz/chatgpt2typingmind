"""Unit-Tests fuer Chat-Metadata-Mapping (Sprint 1.1 Feature 1)"""

import unittest
from build_typingmind_export import chatgpt_conv_to_tm, METADATA_TAGS


def _names(chat):
    """Tag-Namen aus dem TypingMind-Objektformat extrahieren."""
    return {t["name"] for t in chat.get("tags", [])}


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
        self.assertIn("starred", _names(chat))

    def test_pinned_creates_tag(self):
        chat = chatgpt_conv_to_tm(self._make_raw(is_pinned=True), None, {}, "", None)
        self.assertIn("pinned", _names(chat))

    def test_pinned_time_creates_tag(self):
        # ChatGPT speichert Pins teils als pinned_time statt is_pinned
        chat = chatgpt_conv_to_tm(self._make_raw(pinned_time=1735689600), None, {}, "", None)
        self.assertIn("pinned", _names(chat))

    def test_archived_creates_tag(self):
        chat = chatgpt_conv_to_tm(self._make_raw(is_archived=True), None, {}, "", None)
        self.assertIn("archived", _names(chat))

    def test_all_flags_all_tags(self):
        chat = chatgpt_conv_to_tm(
            self._make_raw(is_starred=True, is_pinned=True, is_archived=True),
            None, {}, "", None
        )
        self.assertEqual(_names(chat), {"starred", "pinned", "archived"})

    def test_tags_are_objects_not_strings(self):
        # Regression K1: TypingMind erwartet {"id","name"}, keine Strings
        chat = chatgpt_conv_to_tm(self._make_raw(is_starred=True), None, {}, "", None)
        tag = chat["tags"][0]
        self.assertIsInstance(tag, dict)
        self.assertIn("id", tag)
        self.assertIn("name", tag)

    def test_tag_ids_stable_across_chats(self):
        # Gleicher Flag -> gleiche Tag-ID (TypingMind gruppiert statt dupliziert)
        c1 = chatgpt_conv_to_tm(self._make_raw(is_archived=True), None, {}, "", None)
        c2 = chatgpt_conv_to_tm(self._make_raw(is_archived=True), None, {}, "", None)
        self.assertEqual(c1["tags"][0]["id"], c2["tags"][0]["id"])

    def test_false_flags_no_tags(self):
        chat = chatgpt_conv_to_tm(
            self._make_raw(is_starred=False, is_pinned=False, is_archived=False),
            None, {}, "", None
        )
        self.assertNotIn("tags", chat)


if __name__ == "__main__":
    unittest.main()
