#!/usr/bin/env python3
"""
gui.py — Windows GUI fuer ChatGPT -> TypingMind Migration

Wizard mit 4 Schritten:
  1. ChatGPT-Export waehlen
  2. Ordner konfigurieren
  3. Bild-Hosting (optional, Cloudflare R2)
  4. Migration ausfuehren
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWizard,
    QWizardPage,
)

# --- Eigene Module (gleicher Ordner) ---
SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from normalize_chatgpt_export import (
    build_canonical,
    find_file,
    load_json as norm_load_json,
    parse_memory,
    parse_projects,
)
from discover import generate_config, print_discovery_summary
from build_typingmind_export import (
    build_folder_structure,
    build_image_map,
    chatgpt_conv_to_tm,
    is_chatgpt_id,
    load_config,
    load_json,
    write_flat_json,
    write_json,
    write_zip,
    NOW,
)
from license import (
    FREE_CHAT_LIMIT,
    activate as license_activate,
    get_license_info,
    is_pro as license_is_pro,
)
from manifest import (
    get_imported_ids,
    load_manifest,
    save_manifest,
    compute_delta,
    update_manifest,
)


# ---------------------------------------------------------------------------
# Worker-Threads
# ---------------------------------------------------------------------------

class DiscoverWorker(QThread):
    """Fuehrt normalize + discover im Hintergrund aus."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)  # config dict
    error = pyqtSignal(str)

    def __init__(self, export_dir: Path):
        super().__init__()
        self.export_dir = export_dir

    def run(self):
        try:
            self.progress.emit("Lese ChatGPT-Export...")

            # Conversations laden (ein- oder mehrteilig)
            conv_single = find_file(self.export_dir, ["conversations.json", "chat.json"])
            conv_chunks = sorted(self.export_dir.glob("conversations-[0-9]*.json"))

            if not conv_single and not conv_chunks:
                self.error.emit(
                    "Keine conversations.json gefunden.\n\n"
                    "Stelle sicher, dass der ChatGPT-Export vollstaendig entpackt wurde."
                )
                return

            conversations_raw: list = []
            if conv_chunks:
                for cp in conv_chunks:
                    conversations_raw.extend(norm_load_json(cp))
                self.progress.emit(f"{len(conversations_raw)} Chats aus {len(conv_chunks)} Dateien geladen")
            else:
                conversations_raw = norm_load_json(conv_single)
                self.progress.emit(f"{len(conversations_raw)} Chats geladen")

            # Optionale Dateien
            projects_path = find_file(self.export_dir, ["projects.json"])
            projects_map = {}
            if projects_path:
                projects_map = parse_projects(norm_load_json(projects_path))

            memory_path = find_file(self.export_dir, ["memory.json", "memories.json"])
            memory_entries = []
            if memory_path:
                memory_entries = parse_memory(norm_load_json(memory_path))

            self.progress.emit("Normalisiere...")
            canonical = build_canonical(conversations_raw, projects_map, memory_entries, "chatgpt")

            self.progress.emit("Erkenne Projekte...")
            config = generate_config(canonical, None, projects_map or None)

            # Canonical speichern fuer spaetere Migration
            workspace_dir = self.export_dir.parent / "migration_workspace" / "canonical"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            canonical_path = workspace_dir / "canonical_workspace.json"
            canonical_path.write_text(
                json.dumps(canonical, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            config["_canonical_path"] = str(canonical_path)
            config["_export_dir"] = str(self.export_dir)
            config["_conversations_count"] = len(conversations_raw)

            self.finished.emit(config)

        except Exception as e:
            self.error.emit(f"Fehler: {e}\n\n{traceback.format_exc()}")


class MigrateWorker(QThread):
    """Fuehrt die Migration im Hintergrund aus."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)  # ZIP-Pfad
    error = pyqtSignal(str)

    def __init__(self, config: dict, export_dir: Path, canonical_path: Path, is_pro: bool = False):
        super().__init__()
        self.config = config
        self.export_dir = export_dir
        self.canonical_path = canonical_path
        self.is_pro = is_pro

    def run(self):
        try:
            canonical = load_json(self.canonical_path)
            folder_map = self.config.get("folder_map", {})
            project_instructions = {
                k: v for k, v in self.config.get("project_instructions", {}).items()
                if k != "_comment" and v
            }
            image_base_url = self.config.get("image_base_url", "")

            # Bild-Mapping
            self.progress.emit("Bild-Mapping erstellen...")
            image_map = build_image_map(self.export_dir, None)

            # Ordner aufbauen
            self.progress.emit("Ordner aufbauen...")
            folders, title_to_id = build_folder_structure([], folder_map, project_instructions)

            pid_to_folder_id = {}
            for pid, entry in folder_map.items():
                folder_title = entry.get("folder") or f"Projekt {pid[:12]}"
                pid_to_folder_id[pid] = title_to_id.get(folder_title)

            # Conversations laden
            conv_single = self.export_dir / "conversations.json"
            conv_chunks = sorted(self.export_dir.glob("conversations-[0-9]*.json"))
            raw_convs: list = []
            if conv_chunks:
                for cp in conv_chunks:
                    raw_convs.extend(load_json(cp))
            elif conv_single.is_file():
                raw_convs = load_json(conv_single)
            raw_by_id = {(c.get("id") or c.get("conversation_id") or ""): c for c in raw_convs}

            # Chats konvertieren
            chats = []
            total = len(canonical["conversations"])
            for i, conv in enumerate(canonical["conversations"], 1):
                if i % 50 == 0:
                    self.progress.emit(f"Konvertiere Chat {i}/{total}...")

                cid = conv["conversation_id"]
                raw = raw_by_id.get(cid)
                if not raw:
                    continue

                pid = conv.get("project_id")
                folder_id = pid_to_folder_id.get(pid) if pid else None
                tm_chat = chatgpt_conv_to_tm(raw, folder_id, image_map, image_base_url, self.export_dir)
                chats.append(tm_chat)

            # Chat-Limit fuer Free-Version
            if not self.is_pro and len(chats) > FREE_CHAT_LIMIT:
                total_found = len(chats)
                # Neueste Chats behalten (nach Erstelldatum sortiert)
                chats.sort(key=lambda c: c.get("createdAt", 0), reverse=True)
                chats = chats[:FREE_CHAT_LIMIT]
                self.progress.emit(
                    f"Free: {FREE_CHAT_LIMIT} von {total_found} Chats migriert. "
                    f"Upgrade auf Pro fuer alle Chats! / Upgrade to Pro for all chats!"
                )
            else:
                self.progress.emit(f"{len(chats)} Chats konvertiert. Schreibe Export...")

            # Output
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = self.export_dir.parent / "migration_output" / f"typingmind_import_{ts}"
            out_dir.mkdir(parents=True, exist_ok=True)

            export_data = {"data": {"chats": chats, "folders": folders}}

            flat_path = out_dir / "typingmind_import_FLAT.json"
            flat_path.write_text(
                json.dumps(export_data, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            zip_path = write_zip(out_dir, flat_path)

            self.progress.emit("Fertig!")
            self.finished.emit(str(zip_path))

        except Exception as e:
            self.error.emit(f"Fehler: {e}\n\n{traceback.format_exc()}")


class UploadWorker(QThread):
    """Laedt Bilder auf Cloudflare R2 hoch."""
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)  # Anzahl hochgeladener Bilder
    error = pyqtSignal(str)

    def __init__(self, export_dir: Path, account_id: str, access_key: str, secret_key: str, bucket: str):
        super().__init__()
        self.export_dir = export_dir
        self.account_id = account_id
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket

    def run(self):
        try:
            import boto3
            from botocore.exceptions import ClientError

            IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".dng"}
            CONTENT_TYPES = {
                ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp",
            }

            self.progress.emit("Sammle Bilddateien...")
            images = sorted([
                f for f in self.export_dir.rglob("*")
                if f.is_file() and f.suffix.lower() in IMG_EXTS
            ])

            # Deduplizieren nach Dateiname
            seen = {}
            deduped = []
            for img in images:
                if img.name not in seen:
                    seen[img.name] = img
                    deduped.append(img)
            images = deduped

            self.progress.emit(f"{len(images)} Bilder gefunden. Starte Upload...")

            endpoint = f"https://{self.account_id}.r2.cloudflarestorage.com"
            s3 = boto3.client(
                "s3",
                endpoint_url=endpoint,
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key,
                region_name="auto",
            )

            uploaded = 0
            skipped = 0
            for i, img in enumerate(images, 1):
                key = img.name
                ct = CONTENT_TYPES.get(img.suffix.lower(), "application/octet-stream")

                try:
                    head = s3.head_object(Bucket=self.bucket, Key=key)
                    if head["ContentLength"] == img.stat().st_size:
                        skipped += 1
                        if i % 100 == 0:
                            self.progress.emit(f"[{i}/{len(images)}] {skipped} uebersprungen, {uploaded} hochgeladen")
                        continue
                except ClientError as e:
                    if e.response["Error"]["Code"] != "404":
                        raise

                with open(img, "rb") as f:
                    s3.put_object(Bucket=self.bucket, Key=key, Body=f, ContentType=ct)
                uploaded += 1

                if i % 20 == 0 or i == len(images):
                    self.progress.emit(f"[{i}/{len(images)}] {uploaded} hochgeladen, {skipped} uebersprungen")

            self.progress.emit(f"Fertig: {uploaded} hochgeladen, {skipped} uebersprungen")
            self.finished.emit(uploaded)

        except ImportError:
            self.error.emit(
                "boto3 ist nicht installiert / boto3 is not installed.\n\n"
                "Installiere es mit / Install with: pip install boto3\n"
                "Oder ueberspringe den Bild-Upload / Or skip image upload."
            )
        except Exception as e:
            err_str = str(e)
            if "401" in err_str or "Unauthorized" in err_str:
                self.error.emit(
                    "R2 Zugangsdaten ungueltig / R2 credentials invalid (401 Unauthorized).\n\n"
                    "Pruefe Account ID, Access Key und Secret Key im Cloudflare Dashboard:\n"
                    "R2 -> Manage R2 API Tokens\n\n"
                    "Check Account ID, Access Key and Secret Key in the Cloudflare Dashboard."
                )
            elif "403" in err_str or "Forbidden" in err_str:
                self.error.emit(
                    "Zugriff verweigert / Access denied (403 Forbidden).\n\n"
                    "Pruefe ob der API-Token Lese+Schreib-Rechte fuer den Bucket hat.\n"
                    "Check if the API token has read+write permissions for the bucket."
                )
            else:
                self.error.emit(f"Upload-Fehler / Upload error: {e}\n\n{traceback.format_exc()}")


# ---------------------------------------------------------------------------
# Lizenz-Dialog
# ---------------------------------------------------------------------------

class LicenseActivateWorker(QThread):
    """Validiert einen Lizenz-Key im Hintergrund (blockiert UI nicht)."""
    finished = pyqtSignal(bool, str)  # (success, message)

    def __init__(self, key: str):
        super().__init__()
        self.key = key

    def run(self):
        success, msg = license_activate(self.key)
        self.finished.emit(success, msg)


class LicenseDialog(QDialog):
    """Modaler Dialog fuer Lizenz-Aktivierung."""
    license_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Lizenz / License")
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumWidth(500)
        self.setMinimumHeight(300)
        self._worker: Optional[LicenseActivateWorker] = None

        layout = QVBoxLayout()
        layout.setSpacing(12)

        # Status
        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        # Key-Eingabe
        layout.addWidget(QLabel("Lizenz-Key / License Key:"))
        key_layout = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
        key_layout.addWidget(self.key_edit)

        self.activate_btn = QPushButton("Aktivieren / Activate")
        self.activate_btn.clicked.connect(self._activate)
        key_layout.addWidget(self.activate_btn)
        layout.addLayout(key_layout)

        # Ergebnis
        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        # Kauf-Link
        buy_label = QLabel(
            '<a href="https://workbenchdigital.gumroad.com/l/oemkn">'
            'Pro-Version kaufen / Buy Pro Version</a>'
        )
        buy_label.setOpenExternalLinks(True)
        layout.addWidget(buy_label)

        # Free vs Pro Vergleich
        compare = QLabel(
            "Free: 100 Chats, keine Bilder, kein Delta-Sync\n"
            "Pro: Unbegrenzte Chats, Cloudflare R2 Bilder, Delta-Sync"
        )
        compare.setStyleSheet("color: #888;")
        layout.addWidget(compare)

        layout.addStretch()

        close_btn = QPushButton("Schliessen / Close")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

        self.setLayout(layout)
        self._update_status()

    def _update_status(self):
        info = get_license_info()
        if info:
            email = info.get("email", "?")
            self.status_label.setText(f"Pro-Version aktiv / Pro activated\nE-Mail: {email}")
            self.status_label.setStyleSheet(
                "color: #008800; font-weight: bold; font-size: 13px; padding: 6px;"
            )
        else:
            self.status_label.setText("Free-Version / Free Edition")
            self.status_label.setStyleSheet(
                "color: #cc6600; font-weight: bold; font-size: 13px; padding: 6px;"
            )

    def _activate(self):
        key = self.key_edit.text().strip()
        if not key:
            self.result_label.setText("Bitte Key eingeben / Please enter key")
            self.result_label.setStyleSheet("color: #cc0000;")
            return

        self.activate_btn.setEnabled(False)
        self.result_label.setText("Validiere... / Validating...")
        self.result_label.setStyleSheet("color: #0066cc;")

        # Fix #2: Netzwerk-Call im Hintergrund statt UI-Freeze
        self._worker = LicenseActivateWorker(key)
        self._worker.finished.connect(self._on_activate_result)
        self._worker.start()

    def _on_activate_result(self, success: bool, msg: str):
        self.activate_btn.setEnabled(True)
        if success:
            self.result_label.setText(f"Aktiviert! / Activated! ({msg})")
            self.result_label.setStyleSheet("color: #008800;")
            self._update_status()
            self.license_changed.emit(True)
        else:
            self.result_label.setText(f"Fehler / Error: {msg}")
            self.result_label.setStyleSheet("color: #cc0000;")


# ---------------------------------------------------------------------------
# Wizard-Seiten
# ---------------------------------------------------------------------------

class ExportSelectPage(QWizardPage):
    """Schritt 1: ChatGPT-Export waehlen."""

    def __init__(self):
        super().__init__()
        self.setTitle("ChatGPT-Export waehlen / Select ChatGPT Export")
        self.setSubTitle(
            "Waehle den ENTPACKTEN Ordner deines ChatGPT-Datenexports (nicht die ZIP-Datei!).\n"
            "So bekommst du den Export: ChatGPT -> Einstellungen -> Datenkontrolle -> Meine Daten exportieren\n\n"
            "Select the UNZIPPED folder of your ChatGPT data export (not the ZIP file!).\n"
            "How to get it: ChatGPT -> Settings -> Data Controls -> Export my data"
        )

        layout = QVBoxLayout()

        # Ordner-Auswahl
        path_layout = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Pfad zum entpackten ChatGPT-Export-Ordner / Path to unzipped ChatGPT export folder...")
        path_layout.addWidget(self.path_edit)

        browse_btn = QPushButton("Durchsuchen...")
        browse_btn.clicked.connect(self._browse)
        path_layout.addWidget(browse_btn)

        layout.addLayout(path_layout)

        # Analyse-Button
        self.analyze_btn = QPushButton("Export analysieren / Analyze Export")
        self.analyze_btn.setMinimumHeight(36)
        self.analyze_btn.setStyleSheet("font-size: 13px; font-weight: bold;")
        self.analyze_btn.setToolTip("Scannt den Export und erkennt alle Projekte und GPTs.\nThis may take a moment for large exports.")
        self.analyze_btn.clicked.connect(self._analyze)
        layout.addWidget(self.analyze_btn)

        # Status
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addStretch()
        self.setLayout(layout)

        self._config: Optional[dict] = None
        self._worker: Optional[DiscoverWorker] = None

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, "ChatGPT-Export-Ordner waehlen")
        if folder:
            self.path_edit.setText(folder)

    def isComplete(self):
        return self._config is not None

    def _analyze(self):
        export_dir = Path(self.path_edit.text().strip())
        if not export_dir.is_dir():
            QMessageBox.warning(self, "Fehler", "Bitte waehle zuerst einen gueltigen Ordner.")
            return

        self.analyze_btn.setEnabled(False)
        self.status_label.setText("Analysiere Export...")
        self.status_label.setStyleSheet("color: #0066cc;")

        self._worker = DiscoverWorker(export_dir)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, msg: str):
        self.status_label.setText(msg)

    def _on_finished(self, config: dict):
        self._config = config
        n_proj = sum(1 for v in config.get("folder_map", {}).values() if v.get("type") == "project")
        n_gpt = sum(1 for v in config.get("folder_map", {}).values() if v.get("type") == "gpt")
        n_chats = config.get("_conversations_count", 0)
        self.status_label.setText(
            f"Fertig: {n_chats} Chats, {n_proj} Projekte, {n_gpt} Custom GPTs erkannt.\n"
            "Klicke 'Next' um die Ordnernamen zu konfigurieren."
        )
        self.status_label.setStyleSheet("color: #008800;")
        self.analyze_btn.setEnabled(True)
        self.completeChanged.emit()

    def _on_error(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #cc0000;")
        self.analyze_btn.setEnabled(True)


class FolderConfigPage(QWizardPage):
    """Schritt 2: Ordnernamen konfigurieren."""

    def __init__(self):
        super().__init__()
        self.setTitle("Ordner konfigurieren / Configure Folders")
        self.setSubTitle(
            "Die Ordnernamen werden automatisch aus deinem ChatGPT-Export uebernommen.\n"
            "Du kannst sie optional anpassen. 'Ueberordner' verschachtelt Ordner (z.B. 'Kunden'). Leer = Root.\n\n"
            "Folder names are taken from your ChatGPT export automatically.\n"
            "You can optionally rename them. 'Parent' nests folders. Empty = top level."
        )

        layout = QVBoxLayout()

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Ordnername / Folder", "Ueberordner / Parent", "Chats", "Beispiel / Sample Titles"])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.table)

        # Hinweis zu Projektbeschreibungen
        hint = QLabel(
            "Hinweis / Note: ChatGPT exportiert Projekt-Hinweise nicht automatisch.\n"
            "Kopiere sie manuell: ChatGPT -> Projekteinstellungen -> Hinweise\n"
            "nach TypingMind -> Ordner -> Project context & instructions.\n\n"
            "ChatGPT does not export project instructions automatically.\n"
            "Copy them manually from ChatGPT project settings to TypingMind folder settings."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #887700; padding: 8px; background: #fef9e7; border-radius: 4px;")
        layout.addWidget(hint)

        self.setLayout(layout)

    def initializePage(self):
        page1: ExportSelectPage = self.wizard().page(0)
        config = page1._config
        if not config:
            return

        folder_map = config.get("folder_map", {})
        self.table.setRowCount(len(folder_map))
        self._pid_order = list(folder_map.keys())

        for row, pid in enumerate(self._pid_order):
            entry = folder_map[pid]

            # Ordnername (editierbar)
            name_item = QTableWidgetItem(entry.get("folder", ""))
            self.table.setItem(row, 0, name_item)

            # Ueberordner (editierbar)
            parent_item = QTableWidgetItem(entry.get("parent") or "")
            self.table.setItem(row, 1, parent_item)

            # Chats (read-only)
            count_item = QTableWidgetItem(str(entry.get("conversations", 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, count_item)

            # Beispiel-Titel (read-only)
            samples = entry.get("sample_titles", [])
            sample_text = ", ".join(samples[:3])
            if len(samples) > 3:
                sample_text += f" (+{len(samples)-3})"
            sample_item = QTableWidgetItem(sample_text)
            sample_item.setFlags(sample_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, sample_item)

    def get_folder_map(self) -> Dict[str, Dict]:
        """Liest die aktualisierten Ordnernamen aus der Tabelle."""
        page1: ExportSelectPage = self.wizard().page(0)
        config = page1._config
        folder_map = dict(config.get("folder_map", {}))

        for row, pid in enumerate(self._pid_order):
            name = self.table.item(row, 0).text().strip()
            parent = self.table.item(row, 1).text().strip() or None

            if pid in folder_map:
                folder_map[pid]["folder"] = name
                folder_map[pid]["parent"] = parent

        return folder_map


class ImageHostingPage(QWizardPage):
    """Schritt 3: Bild-Hosting (optional)."""

    def __init__(self):
        super().__init__()
        self.setTitle("Bild-Hosting (optional) / Image Hosting")
        self.setSubTitle(
            "Bilder koennen auf Cloudflare R2 (kostenlos bis 10 GB) hochgeladen werden,\n"
            "damit sie in TypingMind sichtbar sind. Ohne Upload werden Bilder als Platzhalter-Text angezeigt.\n\n"
            "Images can be uploaded to Cloudflare R2 (free up to 10 GB) so they are visible in TypingMind.\n"
            "Without upload, images will show as placeholder text."
        )

        layout = QVBoxLayout()

        self.enable_check = QCheckBox("Bilder auf Cloudflare R2 hochladen / Upload images to Cloudflare R2")
        self.enable_check.toggled.connect(self._toggle_fields)
        layout.addWidget(self.enable_check)

        # R2-Felder
        self.r2_group = QGroupBox("Cloudflare R2 Einstellungen")
        r2_layout = QVBoxLayout()

        info = QLabel(
            "So richtest du R2 ein / How to set up R2:\n"
            "1. dash.cloudflare.com -> R2 Object Storage -> Bucket erstellen / Create bucket\n"
            "2. Settings -> Public Access -> URL aktivieren / Enable public URL\n"
            "3. Settings -> CORS -> AllowedOrigins: [\"*\"], AllowedMethods: [\"GET\"]\n"
            "4. R2 -> Manage R2 API Tokens -> Token erstellen / Create token"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #555; margin-bottom: 10px;")
        r2_layout.addWidget(info)

        self.account_id = QLineEdit()
        self.account_id.setPlaceholderText("Account ID")
        r2_layout.addWidget(QLabel("Account ID:"))
        r2_layout.addWidget(self.account_id)

        self.access_key = QLineEdit()
        self.access_key.setPlaceholderText("Access Key ID")
        r2_layout.addWidget(QLabel("Access Key ID:"))
        r2_layout.addWidget(self.access_key)

        self.secret_key = QLineEdit()
        self.secret_key.setPlaceholderText("Secret Access Key")
        self.secret_key.setEchoMode(QLineEdit.EchoMode.Password)
        r2_layout.addWidget(QLabel("Secret Access Key:"))
        r2_layout.addWidget(self.secret_key)

        self.bucket = QLineEdit()
        self.bucket.setPlaceholderText("Bucket-Name (z.B. typingmind-images)")
        r2_layout.addWidget(QLabel("Bucket-Name:"))
        r2_layout.addWidget(self.bucket)

        self.public_url = QLineEdit()
        self.public_url.setPlaceholderText("https://pub-XXXX.r2.dev")
        r2_layout.addWidget(QLabel("Oeffentliche URL:"))
        r2_layout.addWidget(self.public_url)

        self.r2_group.setLayout(r2_layout)
        self.r2_group.setVisible(False)
        layout.addWidget(self.r2_group)

        layout.addStretch()
        self.setLayout(layout)

        self._upgrade_label_added = False

    def initializePage(self):
        is_pro = getattr(self.wizard(), "_is_pro", False)
        if not is_pro and not self._upgrade_label_added:
            self.enable_check.setEnabled(False)
            self.enable_check.setChecked(False)
            self.r2_group.setVisible(False)
            upgrade_label = QLabel(
                "Bild-Hosting ist ein Pro-Feature. / Image hosting requires Pro.\n"
                "Ohne Pro werden Bilder als Platzhalter angezeigt.\n"
                "Without Pro, images show as placeholder text."
            )
            upgrade_label.setWordWrap(True)
            upgrade_label.setStyleSheet("color: #cc6600; padding: 8px; background: #fff3e0; border-radius: 4px;")
            self.layout().insertWidget(1, upgrade_label)
            self._upgrade_label_added = True
        elif is_pro:
            self.enable_check.setEnabled(True)

    def _toggle_fields(self, checked: bool):
        self.r2_group.setVisible(checked)


class MigrationPage(QWizardPage):
    """Schritt 4: Migration ausfuehren."""

    def __init__(self):
        super().__init__()
        self.setTitle("Migration starten / Run Migration")
        self.setSubTitle(
            "Klicke 'Starten' um die Migration auszufuehren. Dies kann einige Minuten dauern.\n"
            "Click 'Start' to run the migration. This may take a few minutes."
        )

        layout = QVBoxLayout()

        self.start_btn = QPushButton("Migration starten / Start Migration")
        self.start_btn.setMinimumHeight(40)
        self.start_btn.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.start_btn.clicked.connect(self._start)
        layout.addWidget(self.start_btn)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # Indeterminate
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        log_font = QFont("Consolas")
        if not log_font.exactMatch():
            log_font = QFont("Courier New")
        log_font.setPointSize(9)
        self.log.setFont(log_font)
        layout.addWidget(self.log)

        self.open_btn = QPushButton("Ausgabe-Ordner oeffnen / Open Output Folder")
        self.open_btn.setVisible(False)
        self.open_btn.clicked.connect(self._open_output)
        layout.addWidget(self.open_btn)

        self.setLayout(layout)
        self._zip_path: Optional[str] = None
        self._upload_worker: Optional[UploadWorker] = None
        self._migrate_worker: Optional[MigrateWorker] = None

    def _log(self, msg: str):
        self.log.append(msg)

    def _start(self):
        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log.clear()

        # Fix #4: Alle Daten VOR Worker-Start kopieren (Thread-Safety)
        wizard = self.wizard()
        page1: ExportSelectPage = wizard.page(0)
        page2: FolderConfigPage = wizard.page(1)
        page3: ImageHostingPage = wizard.page(2)

        if not page1 or not hasattr(page1, "_config") or not page1._config:
            self._on_error("Kein Export analysiert / No export analyzed")
            return

        config = json.loads(json.dumps(page1._config))  # Deep copy
        config["folder_map"] = page2.get_folder_map()
        export_dir = Path(config["_export_dir"])

        # R2-Daten snapshot (bevor User etwas aendert)
        r2_enabled = page3.enable_check.isChecked()
        r2_account = page3.account_id.text().strip() if r2_enabled else ""
        r2_access = page3.access_key.text().strip() if r2_enabled else ""
        r2_secret = page3.secret_key.text().strip() if r2_enabled else ""
        r2_bucket = page3.bucket.text().strip() if r2_enabled else ""
        r2_url = page3.public_url.text().strip() if r2_enabled else ""

        if r2_enabled:
            config["image_base_url"] = r2_url
            self._log("=== Bild-Upload ===")
            self._upload_worker = UploadWorker(
                export_dir, r2_account, r2_access, r2_secret, r2_bucket,
            )
            self._upload_worker.progress.connect(self._log)
            self._upload_worker.finished.connect(lambda count: self._start_migration(config, export_dir))
            self._upload_worker.error.connect(self._on_error)
            self._upload_worker.start()
        else:
            self._start_migration(config, export_dir)

    def _start_migration(self, config: dict, export_dir: Path):
        self._log("\n=== Migration ===")
        canonical_path = Path(config["_canonical_path"])

        is_pro = getattr(self.wizard(), "_is_pro", False)
        self._migrate_worker = MigrateWorker(config, export_dir, canonical_path, is_pro)
        self._migrate_worker.progress.connect(self._log)
        self._migrate_worker.finished.connect(self._on_finished)
        self._migrate_worker.error.connect(self._on_error)
        self._migrate_worker.start()

    def _on_finished(self, zip_path: str):
        self._zip_path = zip_path
        self.progress_bar.setVisible(False)
        self._log(f"\nZIP erstellt / ZIP created: {zip_path}")
        self._log("\n" + "=" * 55)
        self._log("  WIE GEHT ES WEITER? / WHAT'S NEXT?")
        self._log("=" * 55)
        self._log("")
        self._log("SCHRITT 1 / STEP 1: Import in TypingMind")
        self._log("-" * 45)
        self._log("  1. Oeffne typingmind.com / Open typingmind.com")
        self._log("  2. Falls Cloud Sync aktiv: Settings ->")
        self._log("     Cloud-Sync & Backup -> Account ->")
        self._log("     Aus der Cloud ausloggen / Log out from Cloud")
        self._log("  3. Settings -> App-Daten & -Speicher /")
        self._log("     App Data & Storage -> Importieren / Import")
        self._log("  4. Dateifilter auf 'Alle Dateien (*.*)' aendern!")
        self._log("     Change file filter to 'All files (*.*)'!")
        self._log("  5. ZIP-Datei auswaehlen / Select ZIP file")
        self._log("  6. Pruefen: Sind Chats und Ordner da?")
        self._log("     Verify: Are chats and folders visible?")
        self._log("")
        self._log("SCHRITT 2 / STEP 2: Cloud Sync")
        self._log("-" * 45)
        self._log("  1. Settings -> Cloud-Sync & Backup")
        self._log("  2. In die Cloud einloggen / Log into Cloud")
        self._log("")
        self._log("  WICHTIG / IMPORTANT:")
        self._log("  Falls die Cloud die Chats loescht /")
        self._log("  If Cloud deletes imported chats:")
        self._log("  -> Cloud-Sync -> Zuletzt geloescht /")
        self._log("     Recently Deleted -> Chats")
        self._log("  -> Alle auswaehlen + 'Wiederherstellen' /")
        self._log("     Select all + 'Restore'")
        self._log("  -> Ebenso fuer Ordner, Agents, Plugins /")
        self._log("     Same for Folders, Agents, Plugins")
        self._log("  -> Danach synchronisiert die Cloud korrekt /")
        self._log("     After that, Cloud Sync works correctly")
        self._log("")
        self._log("TIPP / TIP: Projektbeschreibungen")
        self._log("-" * 45)
        self._log("  ChatGPT exportiert Projekt-Hinweise nicht!")
        self._log("  Kopiere sie manuell:")
        self._log("  ChatGPT -> Projekteinstellungen -> Hinweise")
        self._log("  nach TypingMind -> Ordner -> Project context")
        self._log("  & instructions")
        self._log("")
        self._log("  ChatGPT does NOT export project instructions!")
        self._log("  Copy manually from ChatGPT project settings")
        self._log("  to TypingMind folder settings.")
        self._log("")
        self.open_btn.setVisible(True)

    def _on_error(self, msg: str):
        self.progress_bar.setVisible(False)
        self._log(f"\nFEHLER: {msg}")
        self.start_btn.setEnabled(True)

    def _open_output(self):
        if self._zip_path:
            folder = str(Path(self._zip_path).parent)
            os.startfile(folder)


# ---------------------------------------------------------------------------
# Wizard
# ---------------------------------------------------------------------------

class MigrationWizard(QWizard):
    def __init__(self):
        super().__init__()
        self._is_pro = license_is_pro()
        self._update_title()
        self.setMinimumSize(850, 650)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        # Deutsche Button-Beschriftungen
        self.setButtonText(QWizard.WizardButton.NextButton, "Weiter >")
        self.setButtonText(QWizard.WizardButton.BackButton, "< Zurueck")
        self.setButtonText(QWizard.WizardButton.CancelButton, "Abbrechen")
        self.setButtonText(QWizard.WizardButton.FinishButton, "Schliessen")

        # Lizenz-Button
        license_btn = QPushButton("Lizenz / License")
        license_btn.clicked.connect(self._show_license)
        self.setButton(QWizard.WizardButton.CustomButton1, license_btn)
        self.setOption(QWizard.WizardOption.HaveCustomButton1, True)

        self.addPage(ExportSelectPage())
        self.addPage(FolderConfigPage())
        self.addPage(ImageHostingPage())
        self.addPage(MigrationPage())

    def _update_title(self):
        edition = "PRO" if self._is_pro else "FREE"
        self.setWindowTitle(f"ChatGPT -> TypingMind Migration [{edition}]")

    def _show_license(self):
        dlg = LicenseDialog(self)
        dlg.license_changed.connect(self._on_license_changed)
        dlg.exec()  # Modal: blockiert Wizard bis Dialog geschlossen

    def _on_license_changed(self, is_pro: bool):
        self._is_pro = is_pro
        self._update_title()


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    wizard = MigrationWizard()
    wizard.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
