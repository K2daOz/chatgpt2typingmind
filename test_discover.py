"""Unit-Tests fuer discover.py"""

import unittest
from discover import (
    discover_projects,
    suggest_folder_name,
    generate_config,
    _common_prefix,
    _clean_name,
)


class TestDiscoverProjects(unittest.TestCase):
    def test_empty_canonical(self):
        result = discover_projects({"conversations": []})
        self.assertEqual(result, {})

    def test_conversations_without_project(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "title": "Hello"},
            {"conversation_id": "2", "title": "World"},
        ]}
        result = discover_projects(canonical)
        self.assertEqual(result, {})

    def test_groups_by_project_id(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "p1", "title": "Chat A"},
            {"conversation_id": "2", "project_id": "p1", "title": "Chat B"},
            {"conversation_id": "3", "project_id": "p2", "title": "Chat C"},
        ]}
        result = discover_projects(canonical)
        self.assertEqual(len(result), 2)
        self.assertEqual(result["p1"]["count"], 2)
        self.assertEqual(result["p2"]["count"], 1)

    def test_project_vs_gpt_type(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "g-p-abc123", "title": "A"},
            {"conversation_id": "2", "project_id": "g-xyz789", "title": "B"},
        ]}
        result = discover_projects(canonical)
        self.assertEqual(result["g-p-abc123"]["type"], "project")
        self.assertEqual(result["g-xyz789"]["type"], "gpt")

    def test_deduplicates_titles(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "p1", "title": "Same"},
            {"conversation_id": "2", "project_id": "p1", "title": "Same"},
            {"conversation_id": "3", "project_id": "p1", "title": "Different"},
        ]}
        result = discover_projects(canonical)
        self.assertEqual(len(result["p1"]["titles"]), 2)

    def test_skips_empty_titles(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "p1", "title": ""},
            {"conversation_id": "2", "project_id": "p1", "title": "Real Title"},
        ]}
        result = discover_projects(canonical)
        self.assertEqual(result["p1"]["titles"], ["Real Title"])


class TestSuggestFolderName(unittest.TestCase):
    def test_no_titles_fallback(self):
        name = suggest_folder_name("g-p-abc123def456", [])
        self.assertTrue(name.startswith("Projekt g-p-abc123"))

    def test_single_title_unchanged(self):
        name = suggest_folder_name("p1", ["My Project"])
        self.assertEqual(name, "My Project")

    def test_uses_first_title_unchanged(self):
        # Keine Common-Prefix-Extraktion mehr — erster Titel wird 1:1 uebernommen
        name = suggest_folder_name("p1", ["Marketing Plan A", "Marketing Plan B"])
        self.assertEqual(name, "Marketing Plan A")

    def test_long_title_not_truncated(self):
        # Keine Truncation mehr — Name wird unveraendert uebernommen
        long_title = "A" * 50
        name = suggest_folder_name("p1", [long_title])
        self.assertEqual(name, long_title)

    def test_title_whitespace_preserved(self):
        # Kein strip/clean mehr — Whitespace bleibt erhalten
        name = suggest_folder_name("p1", ["  Hello World  "])
        self.assertEqual(name, "  Hello World  ")

    def test_projects_json_takes_priority(self):
        projects_map = {"p1": {"title": "Real Name"}}
        name = suggest_folder_name("p1", ["Chat Title"], projects_map)
        self.assertEqual(name, "Real Name")

    def test_projects_json_generic_name_skipped(self):
        projects_map = {"p1": {"title": "Projekt p1"}}
        name = suggest_folder_name("p1", ["Better Name"], projects_map)
        self.assertEqual(name, "Better Name")


class TestCommonPrefix(unittest.TestCase):
    def test_empty_list(self):
        self.assertEqual(_common_prefix([]), "")

    def test_single_title(self):
        # Single title: prefix is the whole string, then split at last word
        result = _common_prefix(["Hello World"])
        self.assertIn("Hello", result)

    def test_common_prefix(self):
        result = _common_prefix(["Marketing Plan A", "Marketing Plan B"])
        self.assertIn("Marketing", result)

    def test_no_common_prefix(self):
        self.assertEqual(_common_prefix(["Alpha", "Beta", "Gamma"]), "")

    def test_word_boundary(self):
        result = _common_prefix(["Testing ABC", "Testing DEF"])
        self.assertEqual(result, "Testing")


class TestCleanName(unittest.TestCase):
    def test_strips_whitespace(self):
        self.assertEqual(_clean_name("  Hello  "), "Hello")

    def test_strips_trailing_punctuation(self):
        self.assertEqual(_clean_name("Hello..."), "Hello")
        self.assertEqual(_clean_name("Hello---"), "Hello")

    def test_collapses_spaces(self):
        self.assertEqual(_clean_name("Hello    World"), "Hello World")


class TestGenerateConfig(unittest.TestCase):
    def test_empty_canonical(self):
        canonical = {"conversations": []}
        config = generate_config(canonical)
        self.assertEqual(config["folder_map"], {})
        self.assertIn("project_instructions", config)
        self.assertIn("image_base_url", config)

    def test_generates_folder_map(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "p1", "title": "Test Chat"},
        ]}
        config = generate_config(canonical)
        self.assertIn("p1", config["folder_map"])
        self.assertEqual(config["folder_map"]["p1"]["folder"], "Test Chat")

    def test_preserves_existing_config(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "p1", "title": "Auto Name"},
        ]}
        existing = {
            "folder_map": {
                "p1": {"folder": "Custom Name", "parent": "Clients"},
            },
            "image_base_url": "https://example.com",
        }
        config = generate_config(canonical, existing)
        # User's custom name preserved
        self.assertEqual(config["folder_map"]["p1"]["folder"], "Custom Name")
        self.assertEqual(config["folder_map"]["p1"]["parent"], "Clients")
        # Other config preserved
        self.assertEqual(config["image_base_url"], "https://example.com")

    def test_sorted_by_chat_count(self):
        canonical = {"conversations": [
            {"conversation_id": "1", "project_id": "few", "title": "A"},
            {"conversation_id": "2", "project_id": "many", "title": "B"},
            {"conversation_id": "3", "project_id": "many", "title": "C"},
            {"conversation_id": "4", "project_id": "many", "title": "D"},
        ]}
        config = generate_config(canonical)
        keys = list(config["folder_map"].keys())
        self.assertEqual(keys[0], "many")  # Most chats first


if __name__ == "__main__":
    unittest.main()
