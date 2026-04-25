"""
settings.py — Persistente App-Einstellungen

Speichert Benutzereinstellungen lokal in einer JSON-Datei.
Speicherort: neben der .exe oder %APPDATA%/ChatGPT2TypingMind/.settings.json

Sensible Felder (Secret Keys) werden mit Base64-Obfuskation gespeichert.
Das ist KEINE echte Verschluesselung — nur ein leichter Schutz gegen
versehentliches Anzeigen. User wird informiert.
"""

from __future__ import annotations

import base64
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

SETTINGS_FILE_NAME = ".settings.json"

# Felder die obfuskiert werden (nicht im Klartext sichtbar)
SENSITIVE_FIELDS = {"r2_secret_access_key", "r2_access_key_id"}


def get_settings_path() -> Path:
    """Ermittelt Speicherort fuer .settings.json (gleich wie .license)."""
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / SETTINGS_FILE_NAME
        try:
            candidate.touch(exist_ok=True)
            return candidate
        except (PermissionError, OSError):
            pass

    script_dir = Path(__file__).parent
    candidate = script_dir / SETTINGS_FILE_NAME
    try:
        candidate.touch(exist_ok=True)
        return candidate
    except (PermissionError, OSError):
        pass

    appdata = os.environ.get("APPDATA", "")
    if appdata:
        app_dir = Path(appdata) / "ChatGPT2TypingMind"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / SETTINGS_FILE_NAME

    return Path.home() / SETTINGS_FILE_NAME


def _obfuscate(value: str) -> str:
    if not value:
        return ""
    return "b64:" + base64.b64encode(value.encode("utf-8")).decode("ascii")


def _deobfuscate(value: str) -> str:
    if not value:
        return ""
    if value.startswith("b64:"):
        try:
            return base64.b64decode(value[4:]).decode("utf-8")
        except Exception:
            return ""
    return value


def load_settings() -> Dict[str, Any]:
    """Laedt Settings. Gibt leeres Dict zurueck wenn nicht vorhanden."""
    path = get_settings_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        # Sensible Felder deobfuskieren
        for key in SENSITIVE_FIELDS:
            if key in data and isinstance(data[key], str):
                data[key] = _deobfuscate(data[key])
        return data
    except (json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: Dict[str, Any]) -> bool:
    """Speichert Settings. Gibt True zurueck bei Erfolg."""
    path = get_settings_path()
    try:
        # Sensible Felder obfuskieren
        to_save = dict(settings)
        for key in SENSITIVE_FIELDS:
            if key in to_save and isinstance(to_save[key], str):
                to_save[key] = _obfuscate(to_save[key])

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(to_save, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        return True
    except OSError:
        return False


def get(key: str, default: Any = None) -> Any:
    return load_settings().get(key, default)


def set_value(key: str, value: Any) -> bool:
    settings = load_settings()
    settings[key] = value
    return save_settings(settings)
