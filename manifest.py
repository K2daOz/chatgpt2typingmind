#!/usr/bin/env python3
"""
manifest.py

Verwaltet das Manifest fuer inkrementelle Synchronisierung.
Speichert welche Chat-IDs bereits importiert wurden, damit bei
nachfolgenden Runs nur neue Chats verarbeitet werden (Delta-Sync).

Das Manifest liegt standardmaessig neben der config.json oder
im Drive-Sync-Ordner (fuer Multi-Device-Sync).
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


MANIFEST_VERSION = 1


def create_empty_manifest() -> Dict[str, Any]:
    """Erzeugt ein leeres Manifest."""
    return {
        "version": MANIFEST_VERSION,
        "last_run": None,
        "runs": [],
        "imported_chat_ids": [],
        "tm_native_ids": [],
        "stats": {
            "total": 0,
            "chatgpt": 0,
            "tm_native": 0,
        },
    }


def load_manifest(path: Path) -> Dict[str, Any]:
    """Laedt Manifest von Disk. Gibt leeres Manifest zurueck falls nicht vorhanden."""
    if not path.exists():
        return create_empty_manifest()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("version") != MANIFEST_VERSION:
            print(f"  Warnung: Manifest-Version {data.get('version')} != {MANIFEST_VERSION}")
        return data
    except Exception as e:
        print(f"  Warnung: Manifest beschaedigt: {e}")
        # Backup der beschaedigten Datei
        try:
            bak = path.with_suffix(".json.bak")
            path.rename(bak)
            print(f"  Backup gespeichert: {bak}")
        except OSError:
            pass
        return create_empty_manifest()


def save_manifest(path: Path, manifest: Dict[str, Any]) -> None:
    """Speichert Manifest auf Disk."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def get_imported_ids(manifest: Dict[str, Any]) -> Set[str]:
    """Gibt die Menge aller bereits importierten Chat-IDs zurueck."""
    return set(manifest.get("imported_chat_ids", []))


def get_tm_native_ids(manifest: Dict[str, Any]) -> Set[str]:
    """Gibt die Menge aller TM-nativen Chat-IDs zurueck."""
    return set(manifest.get("tm_native_ids", []))


def compute_delta(
    all_canonical_ids: List[str],
    manifest: Dict[str, Any],
) -> List[str]:
    """
    Berechnet welche Chat-IDs neu sind (nicht im Manifest).
    Gibt Liste der neuen IDs zurueck.
    """
    imported = get_imported_ids(manifest)
    new_ids = [cid for cid in all_canonical_ids if cid not in imported]
    return new_ids


def update_manifest(
    manifest: Dict[str, Any],
    imported_ids: List[str],
    tm_native_ids: List[str],
    mode: str = "full",
    chatgpt_count: int = 0,
) -> Dict[str, Any]:
    """
    Aktualisiert Manifest nach einem Run.
    Bei Delta-Modus werden IDs hinzugefuegt, bei Full ersetzt.
    """
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    if mode == "full":
        manifest["imported_chat_ids"] = sorted(set(imported_ids))
        manifest["tm_native_ids"] = sorted(set(tm_native_ids))
    else:
        # Delta: merge
        existing = set(manifest.get("imported_chat_ids", []))
        existing.update(imported_ids)
        manifest["imported_chat_ids"] = sorted(existing)

        existing_native = set(manifest.get("tm_native_ids", []))
        existing_native.update(tm_native_ids)
        manifest["tm_native_ids"] = sorted(existing_native)

    manifest["last_run"] = now
    manifest["stats"] = {
        "total": len(manifest["imported_chat_ids"]) + len(manifest["tm_native_ids"]),
        "chatgpt": len(manifest["imported_chat_ids"]),
        "tm_native": len(manifest["tm_native_ids"]),
    }

    # Run-Eintrag
    manifest["runs"].append({
        "timestamp": now,
        "mode": mode,
        "new_chats": chatgpt_count,
        "total_after": manifest["stats"]["total"],
    })

    # Maximal 50 Runs behalten
    manifest["runs"] = manifest["runs"][-50:]

    return manifest
