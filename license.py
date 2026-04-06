#!/usr/bin/env python3
"""
license.py — Lizenz-Validierung via Gumroad API

Einfaches Freemium-System:
- Free: 100 Chats, keine Bilder, kein Delta-Sync
- Pro: Unbegrenzt, R2 Upload, Delta-Sync

Lizenz-Key wird ueber Gumroad verifiziert und lokal gecacht.
Nach erster Aktivierung funktioniert alles offline.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------

GUMROAD_PRODUCT_ID = "i1rrIwiiNvfRqkmVNQUXxw=="
GUMROAD_VERIFY_URL = "https://api.gumroad.com/v2/licenses/verify"
LICENSE_FILE_NAME = ".license"
REVALIDATION_DAYS = 30
FREE_CHAT_LIMIT = 100


class LicenseError(Exception):
    pass


# ---------------------------------------------------------------------------
# Pfad-Ermittlung
# ---------------------------------------------------------------------------

def get_license_path() -> Path:
    """Ermittelt den Speicherort fuer die .license Datei."""
    # PyInstaller-Frozen: neben der .exe
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidate = exe_dir / LICENSE_FILE_NAME
        # Teste ob Verzeichnis beschreibbar ist
        try:
            candidate.touch(exist_ok=True)
            return candidate
        except (PermissionError, OSError):
            pass

    # Entwicklungsmodus: neben dem Script
    script_dir = Path(__file__).parent
    candidate = script_dir / LICENSE_FILE_NAME
    try:
        candidate.touch(exist_ok=True)
        return candidate
    except (PermissionError, OSError):
        pass

    # Fallback: %APPDATA%
    appdata = os.environ.get("APPDATA", "")
    if appdata:
        app_dir = Path(appdata) / "ChatGPT2TypingMind"
        app_dir.mkdir(parents=True, exist_ok=True)
        return app_dir / LICENSE_FILE_NAME

    return Path.home() / LICENSE_FILE_NAME


# ---------------------------------------------------------------------------
# Cache lesen/schreiben
# ---------------------------------------------------------------------------

def load_cached_license() -> Optional[dict]:
    """Liest die gecachte Lizenz. Gibt None zurueck wenn nicht vorhanden."""
    path = get_license_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        if "license_key" not in data or "validated_at" not in data:
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def save_license_cache(data: dict) -> None:
    """Speichert die Lizenz-Daten lokal."""
    path = get_license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Gumroad API
# ---------------------------------------------------------------------------

def validate_online(license_key: str, increment: bool = True) -> dict:
    """
    Validiert einen Lizenz-Key ueber die Gumroad API.
    Gibt die API-Antwort als dict zurueck.
    Raises LicenseError bei Fehlern.
    """
    if not GUMROAD_PRODUCT_ID:
        raise LicenseError(
            "Product ID nicht konfiguriert. "
            "Setze GUMROAD_PRODUCT_ID in license.py."
        )

    license_key = license_key.strip()
    if not license_key:
        raise LicenseError("Lizenz-Key darf nicht leer sein / License key cannot be empty")

    payload = urllib.parse.urlencode({
        "product_id": GUMROAD_PRODUCT_ID,
        "license_key": license_key.strip(),
        "increment_uses_count": "true" if increment else "false",
    }).encode("utf-8")

    req = urllib.request.Request(
        GUMROAD_VERIFY_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )

    try:
        try:
            ctx = ssl.create_default_context()
        except Exception:
            # Fallback fuer PyInstaller-Frozen Apps ohne CA-Bundle
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with urllib.request.urlopen(req, context=ctx, timeout=10) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            msg = err_body.get("message", str(e))
        except Exception:
            msg = str(e)
        raise LicenseError(f"Gumroad API Fehler: {msg}")
    except (urllib.error.URLError, OSError, ssl.SSLError) as e:
        raise LicenseError(f"Netzwerkfehler: {e}")
    except json.JSONDecodeError:
        raise LicenseError("Ungueltige API-Antwort")

    if not body.get("success"):
        msg = body.get("message", "Ungueltiger Lizenz-Key")
        raise LicenseError(msg)

    return body


# ---------------------------------------------------------------------------
# Oeffentliche API
# ---------------------------------------------------------------------------

def activate(license_key: str) -> Tuple[bool, str]:
    """
    Aktiviert einen Lizenz-Key (mit Online-Validierung).
    Gibt (True, email) bei Erfolg oder (False, fehlermeldung) zurueck.
    """
    try:
        result = validate_online(license_key, increment=True)
    except LicenseError as e:
        return False, str(e)

    purchase = result.get("purchase", {})
    email = purchase.get("email", "")
    uses = result.get("uses", 0)

    cache = {
        "license_key": license_key.strip(),
        "product_id": GUMROAD_PRODUCT_ID,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "email": email,
        "uses": uses,
    }

    try:
        save_license_cache(cache)
    except OSError as e:
        return False, f"Lizenz validiert, aber Speichern fehlgeschlagen: {e}"

    return True, email


def is_pro() -> bool:
    """
    Prueft ob eine gueltige Pro-Lizenz vorliegt.
    Funktioniert offline nach erster Aktivierung.
    """
    cached = load_cached_license()
    if not cached:
        return False

    # Pruefe ob Revalidierung noetig
    try:
        validated = datetime.fromisoformat(cached["validated_at"])
        age_days = (datetime.now(timezone.utc) - validated).days
    except (ValueError, KeyError):
        age_days = REVALIDATION_DAYS + 1

    if age_days < REVALIDATION_DAYS:
        return True  # Cache ist frisch genug

    # Stille Revalidierung (ohne use count zu erhoehen)
    try:
        validate_online(cached["license_key"], increment=False)
        # Aktualisiere Timestamp
        cached["validated_at"] = datetime.now(timezone.utc).isoformat()
        save_license_cache(cached)
    except (LicenseError, OSError):
        pass  # Netzfehler: Cache akzeptieren (Offline-Modus)

    return True


def get_license_info() -> Optional[dict]:
    """Gibt gecachte Lizenz-Info zurueck (fuer UI-Anzeige)."""
    return load_cached_license()
