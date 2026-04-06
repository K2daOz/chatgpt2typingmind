#!/usr/bin/env python3
"""
discover.py — Erkennt ChatGPT-Projekte und generiert config.json

Scannt den ChatGPT-Export, gruppiert Konversationen nach Projekt/Custom GPT,
leitet sinnvolle Ordnernamen ab und erzeugt eine config.json die der
Anwender reviewen und anpassen kann.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


def discover_projects(canonical: Dict[str, Any]) -> Dict[str, Dict]:
    """
    Extrahiert alle Projekte/Custom GPTs aus canonical_workspace.json.

    Gibt Dict zurueck:
      { project_id: { "titles": [...], "count": N, "type": "project"|"gpt" } }
    """
    projects: Dict[str, Dict] = {}

    for conv in canonical.get("conversations", []):
        pid = conv.get("project_id")
        if not pid:
            continue

        if pid not in projects:
            projects[pid] = {
                "titles": [],
                "count": 0,
                "type": "project" if pid.startswith("g-p-") else "gpt",
            }

        projects[pid]["count"] += 1
        title = conv.get("title") or ""
        if title and title not in projects[pid]["titles"]:
            projects[pid]["titles"].append(title)

    return projects


def suggest_folder_name(
    project_id: str,
    titles: List[str],
    projects_json_map: Optional[Dict[str, Dict]] = None,
) -> str:
    """
    Leitet einen sinnvollen Ordnernamen fuer ein Projekt/GPT ab.

    Prioritaet:
      1. projects.json Titel (falls vorhanden)
      2. Haeufigster gemeinsamer Praefix der Chat-Titel
      3. Erster Chat-Titel
      4. Fallback: "Projekt [ID-Kuerzel]"
    """
    # 1. projects.json
    if projects_json_map and project_id in projects_json_map:
        name = projects_json_map[project_id].get("title", "")
        if name and not name.startswith("Projekt "):
            return _clean_name(name)

    if not titles:
        return f"Projekt {project_id[:12]}"

    # 2. Gemeinsamer Praefix (mind. 3 Zeichen, mind. 2 Titel)
    if len(titles) >= 2:
        prefix = _common_prefix(titles)
        if len(prefix) >= 3:
            return _clean_name(prefix)

    # 3. Erster Chat-Titel als Name
    first = titles[0]
    # Kuerzen wenn zu lang (max 40 Zeichen)
    if len(first) > 40:
        first = first[:37] + "..."
    return _clean_name(first)


def _common_prefix(titles: List[str]) -> str:
    """Findet den laengsten gemeinsamen Praefix von Chat-Titeln."""
    if not titles:
        return ""
    prefix = titles[0]
    for t in titles[1:]:
        while not t.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    # Am letzten Wort abschneiden (nicht mitten im Wort)
    prefix = prefix.rstrip()
    if " " in prefix:
        prefix = prefix.rsplit(" ", 1)[0]
    return prefix.strip()


def _clean_name(name: str) -> str:
    """Bereinigt einen Namen: Whitespace trimmen, keine Sonderzeichen am Ende."""
    name = name.strip()
    name = re.sub(r"[\s]+", " ", name)
    name = name.rstrip(".-_:,;")
    return name


def generate_config(
    canonical: Dict[str, Any],
    existing_config: Optional[Dict] = None,
    projects_json_map: Optional[Dict[str, Dict]] = None,
) -> Dict:
    """
    Erzeugt eine config.json mit folder_map aus dem ChatGPT-Export.

    Wenn existing_config vorhanden: bestehende Eintraege bleiben erhalten
    (User-Anpassungen werden nicht ueberschrieben).
    """
    if existing_config is None:
        existing_config = {}

    discovered = discover_projects(canonical)
    existing_folder_map = existing_config.get("folder_map", {})

    folder_map: Dict[str, Dict] = {}

    for pid, info in sorted(discovered.items(), key=lambda x: -x[1]["count"]):
        titles = info["titles"]

        if pid in existing_folder_map:
            # Bestehenden Eintrag beibehalten (User hat ggf. angepasst)
            entry = dict(existing_folder_map[pid])
            # Nur Metadaten aktualisieren
            entry["conversations"] = info["count"]
            entry["sample_titles"] = titles[:5]
            entry["type"] = info["type"]
            folder_map[pid] = entry
        else:
            # Neuer Eintrag — Namen vorschlagen
            suggested = suggest_folder_name(pid, titles, projects_json_map)
            folder_map[pid] = {
                "folder": suggested,
                "parent": None,
                "type": info["type"],
                "conversations": info["count"],
                "sample_titles": titles[:5],
            }

    config = {
        "_comment": "Auto-generiert durch: python migrate.py --discover",
        "folder_map": folder_map,
        "project_instructions": existing_config.get("project_instructions", {}),
        "image_base_url": existing_config.get("image_base_url", ""),
        "output": existing_config.get("output", {
            "zip": True,
            "flat_json": True,
        }),
    }

    return config


def print_discovery_summary(config: Dict) -> None:
    """Gibt eine Zusammenfassung der erkannten Projekte aus."""
    folder_map = config.get("folder_map", {})
    if not folder_map:
        print("  Keine Projekte/GPTs gefunden.")
        return

    projects = {k: v for k, v in folder_map.items() if v.get("type") == "project"}
    gpts = {k: v for k, v in folder_map.items() if v.get("type") == "gpt"}

    print(f"  Erkannt: {len(projects)} Projekte, {len(gpts)} Custom GPTs")
    print()

    if projects:
        print("  Projekte:")
        for pid, info in projects.items():
            parent = f" (unter '{info['parent']}')" if info.get("parent") else ""
            print(f"    [{info['conversations']:>3} Chats] {info['folder']}{parent}")

    if gpts:
        print("\n  Custom GPTs:")
        for pid, info in gpts.items():
            print(f"    [{info['conversations']:>3} Chats] {info['folder']}")
