"""
translations.py — Zweisprachiges Uebersetzungssystem (DE/EN)
"""

from __future__ import annotations
from typing import Dict

LANGUAGES = ["de", "en"]
DEFAULT_LANG = "en"

_current_lang = DEFAULT_LANG

STRINGS: Dict[str, Dict[str, str]] = {
    # --- Wizard ---
    "wizard_title_free": {
        "de": "ChatGPT -> TypingMind Migration [FREE]",
        "en": "ChatGPT -> TypingMind Migration [FREE]",
    },
    "wizard_title_pro": {
        "de": "ChatGPT -> TypingMind Migration [PRO]",
        "en": "ChatGPT -> TypingMind Migration [PRO]",
    },
    "btn_next": {"de": "Weiter >", "en": "Next >"},
    "btn_back": {"de": "< Zurueck", "en": "< Back"},
    "btn_cancel": {"de": "Abbrechen", "en": "Cancel"},
    "btn_finish": {"de": "Schliessen", "en": "Close"},
    "btn_license": {"de": "Lizenz", "en": "License"},

    # --- Page 1: Export ---
    "p1_title": {
        "de": "ChatGPT-Export waehlen",
        "en": "Select ChatGPT Export",
    },
    "p1_subtitle": {
        "de": (
            "Waehle den ENTPACKTEN Ordner deines ChatGPT-Datenexports "
            "(nicht die ZIP-Datei!).\n"
            "So bekommst du den Export: ChatGPT -> Einstellungen -> "
            "Datenkontrolle -> Meine Daten exportieren"
        ),
        "en": (
            "Select the UNZIPPED folder of your ChatGPT data export "
            "(not the ZIP file!).\n"
            "How to get it: ChatGPT -> Settings -> Data Controls -> "
            "Export my data"
        ),
    },
    "p1_placeholder": {
        "de": "Pfad zum entpackten ChatGPT-Export-Ordner...",
        "en": "Path to unzipped ChatGPT export folder...",
    },
    "p1_browse": {"de": "Durchsuchen...", "en": "Browse..."},
    "p1_analyze": {"de": "Export analysieren", "en": "Analyze Export"},
    "p1_analyze_tooltip": {
        "de": "Scannt den Export und erkennt alle Projekte und GPTs.",
        "en": "Scans the export and detects all projects and GPTs.",
    },
    "p1_analyzing": {"de": "Analysiere Export...", "en": "Analyzing export..."},
    "p1_no_folder": {
        "de": "Bitte waehle zuerst einen gueltigen Ordner.",
        "en": "Please select a valid folder first.",
    },
    "p1_no_conversations": {
        "de": (
            "Keine conversations.json gefunden.\n\n"
            "Stelle sicher, dass der ChatGPT-Export vollstaendig entpackt wurde."
        ),
        "en": (
            "No conversations.json found.\n\n"
            "Make sure the ChatGPT export is fully unzipped."
        ),
    },
    "p1_done": {
        "de": "Fertig: {chats} Chats, {proj} Projekte, {gpt} Custom GPTs erkannt.\n"
              "Klicke 'Weiter' um die Ordnernamen zu konfigurieren.",
        "en": "Done: {chats} chats, {proj} projects, {gpt} Custom GPTs detected.\n"
              "Click 'Next' to configure folder names.",
    },

    # --- Page 2: Folders ---
    "p2_title": {"de": "Ordner konfigurieren", "en": "Configure Folders"},
    "p2_subtitle": {
        "de": (
            "Die Ordnernamen werden automatisch aus deinem ChatGPT-Export "
            "uebernommen.\nDu kannst sie optional anpassen. "
            "'Ueberordner' verschachtelt Ordner (z.B. 'Kunden'). Leer = Root."
        ),
        "en": (
            "Folder names are taken from your ChatGPT export automatically.\n"
            "You can optionally rename them. "
            "'Parent' nests folders (e.g. 'Clients'). Empty = top level."
        ),
    },
    "p2_col_folder": {"de": "Ordnername", "en": "Folder Name"},
    "p2_col_parent": {"de": "Ueberordner", "en": "Parent Folder"},
    "p2_col_chats": {"de": "Chats", "en": "Chats"},
    "p2_col_samples": {"de": "Beispiel-Titel", "en": "Sample Titles"},
    "p2_hint": {
        "de": (
            "Hinweis: ChatGPT exportiert Projekt-Hinweise nicht automatisch.\n"
            "Kopiere sie manuell: ChatGPT -> Projekteinstellungen -> Hinweise\n"
            "nach TypingMind -> Ordner -> Project context & instructions."
        ),
        "en": (
            "Note: ChatGPT does not export project instructions automatically.\n"
            "Copy them manually from ChatGPT project settings\n"
            "to TypingMind -> Folder -> Project context & instructions."
        ),
    },

    # --- Page 3: Image Hosting ---
    "p3_title": {"de": "Bild-Hosting (optional)", "en": "Image Hosting (optional)"},
    "p3_subtitle": {
        "de": (
            "Bilder koennen auf Cloudflare R2 (kostenlos bis 10 GB) "
            "hochgeladen werden,\ndamit sie in TypingMind sichtbar sind. "
            "Ohne Upload werden Bilder als Platzhalter-Text angezeigt."
        ),
        "en": (
            "Images can be uploaded to Cloudflare R2 (free up to 10 GB) "
            "so they are visible in TypingMind.\n"
            "Without upload, images will show as placeholder text."
        ),
    },
    "p3_enable": {
        "de": "Bilder auf Cloudflare R2 hochladen",
        "en": "Upload images to Cloudflare R2",
    },
    "p3_r2_help_btn": {
        "de": "R2 Einrichtungsanleitung",
        "en": "R2 Setup Guide",
    },
    "p3_upgrade": {
        "de": (
            "Bild-Hosting ist ein Pro-Feature.\n"
            "Ohne Pro werden Bilder als Platzhalter angezeigt."
        ),
        "en": (
            "Image hosting requires Pro.\n"
            "Without Pro, images show as placeholder text."
        ),
    },

    # --- Page 4: Migration ---
    "p4_title": {"de": "Migration starten", "en": "Run Migration"},
    "p4_subtitle": {
        "de": "Klicke 'Starten' um die Migration auszufuehren. Dies kann einige Minuten dauern.",
        "en": "Click 'Start' to run the migration. This may take a few minutes.",
    },
    "p4_start": {"de": "Migration starten", "en": "Start Migration"},
    "p4_open_folder": {"de": "Ausgabe-Ordner oeffnen", "en": "Open Output Folder"},
    "p4_no_export": {
        "de": "Kein Export analysiert.",
        "en": "No export analyzed.",
    },
    "p4_free_limit": {
        "de": "Free: {limit} von {total} Chats migriert. Upgrade auf Pro fuer alle Chats!",
        "en": "Free: {limit} of {total} chats migrated. Upgrade to Pro for all chats!",
    },

    # --- Page 4: Finish instructions ---
    "p4_finish_title": {
        "de": "WIE GEHT ES WEITER?",
        "en": "WHAT'S NEXT?",
    },
    "p4_step1_title": {
        "de": "SCHRITT 1: Import in TypingMind",
        "en": "STEP 1: Import into TypingMind",
    },
    "p4_step1": {
        "de": (
            "  1. Oeffne typingmind.com\n"
            "  2. Falls Cloud Sync aktiv: Settings ->\n"
            "     Cloud-Sync & Backup -> Konto & Einstellungen\n"
            "     -> Aus der Cloud ausloggen\n"
            "  3. Settings -> App-Daten & -Speicher -> Importieren\n"
            "  4. Dateifilter auf 'Alle Dateien (*.*)' aendern!\n"
            "  5. ZIP-Datei auswaehlen\n"
            "  6. Pruefen: Sind Chats und Ordner da?"
        ),
        "en": (
            "  1. Open typingmind.com\n"
            "  2. If Cloud Sync active: Settings ->\n"
            "     Cloud-Sync & Backup -> Account Settings\n"
            "     -> Log out from Cloud\n"
            "  3. Settings -> App Data & Storage -> Import\n"
            "  4. Change file filter to 'All files (*.*)'!\n"
            "  5. Select the ZIP file\n"
            "  6. Verify: Are chats and folders visible?"
        ),
    },
    "p4_step2_title": {
        "de": "SCHRITT 2: Cloud Sync",
        "en": "STEP 2: Cloud Sync",
    },
    "p4_step2": {
        "de": (
            "  1. Settings -> Cloud-Sync & Backup\n"
            "  2. In die Cloud einloggen\n\n"
            "  WICHTIG: Falls die Cloud die Chats loescht:\n"
            "  -> Cloud-Sync -> Zuletzt geloescht -> Chats\n"
            "  -> Alle auswaehlen + 'Wiederherstellen'\n"
            "  -> Ebenso fuer Ordner, Agents, Plugins\n"
            "  -> Danach synchronisiert die Cloud korrekt"
        ),
        "en": (
            "  1. Settings -> Cloud-Sync & Backup\n"
            "  2. Log into Cloud\n\n"
            "  IMPORTANT: If Cloud deletes imported chats:\n"
            "  -> Cloud-Sync -> Recently Deleted -> Chats\n"
            "  -> Select all + 'Restore'\n"
            "  -> Same for Folders, Agents, Plugins\n"
            "  -> After that, Cloud Sync works correctly"
        ),
    },
    "p4_tip_title": {
        "de": "TIPP: Projektbeschreibungen",
        "en": "TIP: Project Instructions",
    },
    "p4_tip": {
        "de": (
            "  ChatGPT exportiert Projekt-Hinweise nicht!\n"
            "  Kopiere sie manuell:\n"
            "  ChatGPT -> Projekteinstellungen -> Hinweise\n"
            "  nach TypingMind -> Ordner -> Project context\n"
            "  & instructions"
        ),
        "en": (
            "  ChatGPT does NOT export project instructions!\n"
            "  Copy manually:\n"
            "  ChatGPT -> Project Settings -> Instructions\n"
            "  to TypingMind -> Folder -> Project context\n"
            "  & instructions"
        ),
    },

    # --- Cloud Sync Warning (rich text) ---
    "p4_cloud_warning": {
        "de": (
            "<b>Wichtig: TypingMind Cloud Sync</b><br><br>"
            "Falls du TypingMind Cloud Sync nutzt, werden importierte Chats "
            "moeglicherweise von der leeren Cloud ueberschrieben.<br><br>"
            "<b>Loesung:</b><br>"
            "1. Importiere die ZIP-Datei (Settings &rarr; App-Daten &rarr; Importieren)<br>"
            "2. Logge dich in die Cloud ein (Settings &rarr; Cloud-Sync &rarr; Einloggen)<br>"
            "3. Falls Chats verschwinden: Gehe zu <b>Cloud-Sync &rarr; Zuletzt geloescht</b><br>"
            "4. Waehle <b>alle Chats, Ordner, Agents und Plugins</b> aus<br>"
            "5. Klicke <b>'Wiederherstellen'</b> fuer jede Kategorie<br>"
            "6. Danach synchronisiert die Cloud korrekt und die Daten bleiben erhalten."
        ),
        "en": (
            "<b>Important: TypingMind Cloud Sync</b><br><br>"
            "If you use TypingMind Cloud Sync, imported chats may be "
            "overwritten by the empty cloud state.<br><br>"
            "<b>Solution:</b><br>"
            "1. Import the ZIP file (Settings &rarr; App Data &rarr; Import)<br>"
            "2. Log into Cloud (Settings &rarr; Cloud-Sync &rarr; Log in)<br>"
            "3. If chats disappear: Go to <b>Cloud-Sync &rarr; Recently Deleted</b><br>"
            "4. Select <b>all Chats, Folders, Agents and Plugins</b><br>"
            "5. Click <b>'Restore'</b> for each category<br>"
            "6. After that, Cloud Sync works correctly and data persists."
        ),
    },

    # --- License Dialog ---
    "lic_title": {"de": "Lizenz", "en": "License"},
    "lic_pro_active": {
        "de": "Pro-Version aktiv\nE-Mail: {email}",
        "en": "Pro version active\nEmail: {email}",
    },
    "lic_free": {"de": "Free-Version", "en": "Free Edition"},
    "lic_key_label": {"de": "Lizenz-Key:", "en": "License Key:"},
    "lic_activate": {"de": "Aktivieren", "en": "Activate"},
    "lic_validating": {"de": "Validiere...", "en": "Validating..."},
    "lic_activated": {"de": "Aktiviert!", "en": "Activated!"},
    "lic_empty_key": {
        "de": "Bitte Key eingeben",
        "en": "Please enter a key",
    },
    "lic_buy": {
        "de": "Pro-Version kaufen",
        "en": "Buy Pro Version",
    },
    "lic_compare": {
        "de": "Free: 100 Chats, keine Bilder, kein Delta-Sync\n"
              "Pro: Unbegrenzte Chats, Cloudflare R2 Bilder, Delta-Sync",
        "en": "Free: 100 chats, no images, no delta-sync\n"
              "Pro: Unlimited chats, Cloudflare R2 images, delta-sync",
    },
    "lic_close": {"de": "Schliessen", "en": "Close"},

    # --- R2 Guide ---
    "r2_guide_title": {"de": "Cloudflare R2 Einrichtung", "en": "Cloudflare R2 Setup Guide"},
    # r2_guide wird unten nach Definition von R2_GUIDE_DE/EN gesetzt

    # --- Errors ---
    "err_r2_401": {
        "de": (
            "R2 Zugangsdaten ungueltig (401 Unauthorized).\n\n"
            "Pruefe Account ID, Access Key und Secret Key im Cloudflare Dashboard:\n"
            "R2 -> Manage R2 API Tokens"
        ),
        "en": (
            "R2 credentials invalid (401 Unauthorized).\n\n"
            "Check Account ID, Access Key and Secret Key in the Cloudflare Dashboard:\n"
            "R2 -> Manage R2 API Tokens"
        ),
    },
    "err_r2_403": {
        "de": (
            "Zugriff verweigert (403 Forbidden).\n\n"
            "Pruefe ob der API-Token Lese+Schreib-Rechte fuer den Bucket hat."
        ),
        "en": (
            "Access denied (403 Forbidden).\n\n"
            "Check if the API token has read+write permissions for the bucket."
        ),
    },
    "err_boto3": {
        "de": "boto3 ist nicht installiert.\n\nInstalliere es mit: pip install boto3",
        "en": "boto3 is not installed.\n\nInstall with: pip install boto3",
    },
}


# --- R2 Guide (lange Texte separat) ---

R2_GUIDE_DE = """<h2>Cloudflare R2 Einrichtung</h2>

<h3>1. Cloudflare-Konto erstellen</h3>
<p>Gehe zu <a href="https://dash.cloudflare.com/">dash.cloudflare.com</a> und erstelle ein kostenloses Konto.</p>

<h3>2. R2 Bucket erstellen</h3>
<ol>
<li>Im Dashboard: <b>R2 Object Storage</b> (linke Sidebar)</li>
<li>Klicke <b>"Create bucket"</b></li>
<li>Name: z.B. <code>typingmind-images</code></li>
<li>Region: <b>Automatic</b></li>
<li>Klicke <b>"Create bucket"</b></li>
</ol>

<h3>3. Public Access aktivieren</h3>
<ol>
<li>Oeffne deinen Bucket -> <b>Settings</b></li>
<li>Unter <b>"Oeffentliche Entwicklungs-URL"</b>: Klicke <b>"Allow Access"</b></li>
<li>Notiere die URL (z.B. <code>https://pub-XXXX.r2.dev</code>)</li>
</ol>

<h3>4. CORS-Richtlinie einrichten</h3>
<ol>
<li>Im gleichen Settings-Bereich: <b>CORS-Richtlinie</b> -> <b>"+ Hinzufuegen"</b></li>
<li>Fuege ein:</li>
</ol>
<pre>[{"AllowedOrigins": ["*"], "AllowedMethods": ["GET"]}]</pre>

<h3>5. API-Token erstellen</h3>
<ol>
<li>Gehe zu <b>R2</b> -> <b>"Manage R2 API Tokens"</b> (oben rechts)</li>
<li>Klicke <b>"Create API Token"</b></li>
<li>Berechtigungen: <b>Object Read & Write</b></li>
<li>Bucket: Waehle deinen Bucket aus</li>
<li>Notiere: <b>Access Key ID</b> und <b>Secret Access Key</b></li>
<li>Deine <b>Account ID</b> findest du in der URL: <code>dash.cloudflare.com/ACCOUNT_ID/...</code></li>
</ol>

<h3>6. In der App eintragen</h3>
<p>Trage die 5 Werte in die Felder auf dieser Seite ein:</p>
<ul>
<li><b>Account ID</b> — aus der Cloudflare URL</li>
<li><b>Access Key ID</b> — vom API-Token</li>
<li><b>Secret Access Key</b> — vom API-Token</li>
<li><b>Bucket-Name</b> — z.B. <code>typingmind-images</code></li>
<li><b>Oeffentliche URL</b> — z.B. <code>https://pub-XXXX.r2.dev</code></li>
</ul>
"""

R2_GUIDE_EN = """<h2>Cloudflare R2 Setup Guide</h2>

<h3>1. Create Cloudflare Account</h3>
<p>Go to <a href="https://dash.cloudflare.com/">dash.cloudflare.com</a> and create a free account.</p>

<h3>2. Create R2 Bucket</h3>
<ol>
<li>In the dashboard: <b>R2 Object Storage</b> (left sidebar)</li>
<li>Click <b>"Create bucket"</b></li>
<li>Name: e.g. <code>typingmind-images</code></li>
<li>Region: <b>Automatic</b></li>
<li>Click <b>"Create bucket"</b></li>
</ol>

<h3>3. Enable Public Access</h3>
<ol>
<li>Open your bucket -> <b>Settings</b></li>
<li>Under <b>"Public Development URL"</b>: Click <b>"Allow Access"</b></li>
<li>Note the URL (e.g. <code>https://pub-XXXX.r2.dev</code>)</li>
</ol>

<h3>4. Configure CORS Policy</h3>
<ol>
<li>In the same Settings area: <b>CORS Policy</b> -> <b>"+ Add"</b></li>
<li>Paste:</li>
</ol>
<pre>[{"AllowedOrigins": ["*"], "AllowedMethods": ["GET"]}]</pre>

<h3>5. Create API Token</h3>
<ol>
<li>Go to <b>R2</b> -> <b>"Manage R2 API Tokens"</b> (top right)</li>
<li>Click <b>"Create API Token"</b></li>
<li>Permissions: <b>Object Read & Write</b></li>
<li>Bucket: Select your bucket</li>
<li>Note: <b>Access Key ID</b> and <b>Secret Access Key</b></li>
<li>Your <b>Account ID</b> is in the URL: <code>dash.cloudflare.com/ACCOUNT_ID/...</code></li>
</ol>

<h3>6. Enter in the App</h3>
<p>Enter the 5 values in the fields on this page:</p>
<ul>
<li><b>Account ID</b> — from the Cloudflare URL</li>
<li><b>Access Key ID</b> — from the API token</li>
<li><b>Secret Access Key</b> — from the API token</li>
<li><b>Bucket Name</b> — e.g. <code>typingmind-images</code></li>
<li><b>Public URL</b> — e.g. <code>https://pub-XXXX.r2.dev</code></li>
</ul>
"""

# Fix: Forward reference — R2 Guide Strings muessen nach Definition gesetzt werden
STRINGS["r2_guide"] = {"de": R2_GUIDE_DE, "en": R2_GUIDE_EN}


def set_language(lang: str) -> None:
    global _current_lang
    if lang in LANGUAGES:
        _current_lang = lang


def get_language() -> str:
    return _current_lang


def tr(key: str, **kwargs) -> str:
    """Uebersetzt einen String-Key in die aktuelle Sprache."""
    entry = STRINGS.get(key)
    if not entry:
        return f"[{key}]"
    text = entry.get(_current_lang, entry.get("en", f"[{key}]"))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text
