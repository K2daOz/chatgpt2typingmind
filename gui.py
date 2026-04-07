#!/usr/bin/env python3
"""
gui.py — Windows GUI fuer ChatGPT -> TypingMind Migration
Wizard mit 4 Schritten, zweisprachig (DE/EN), Freemium-Lizenzierung.
"""

from __future__ import annotations

import json
import os
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QUrl
from PyQt6.QtGui import QFont, QDesktopServices
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QMessageBox, QProgressBar,
    QPushButton, QTableWidget, QTableWidgetItem, QTextBrowser, QTextEdit,
    QVBoxLayout, QWizard, QWizardPage,
)

SCRIPT_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPT_DIR))

from normalize_chatgpt_export import (
    build_canonical, find_file, load_json as norm_load_json,
    parse_memory, parse_projects,
)
from discover import generate_config, print_discovery_summary
from build_typingmind_export import (
    build_folder_structure, build_image_map, chatgpt_conv_to_tm,
    is_chatgpt_id, load_config, load_json, write_flat_json, write_json,
    write_zip, NOW,
)
from license import (
    FREE_CHAT_LIMIT, activate as license_activate, get_license_info,
    is_pro as license_is_pro,
)
from manifest import (
    get_imported_ids, load_manifest, save_manifest, compute_delta,
    update_manifest,
)
from translations import tr, set_language, get_language, R2_GUIDE_DE, R2_GUIDE_EN


# ===================================================================
# Worker Threads
# ===================================================================

class DiscoverWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(dict)
    error = pyqtSignal(str)

    def __init__(self, export_dir: Path):
        super().__init__()
        self.export_dir = export_dir

    def run(self):
        try:
            self.progress.emit(tr("p1_analyzing"))
            conv_single = find_file(self.export_dir, ["conversations.json", "chat.json"])
            conv_chunks = sorted(self.export_dir.glob("conversations-[0-9]*.json"))

            if not conv_single and not conv_chunks:
                self.error.emit(tr("p1_no_conversations"))
                return

            conversations_raw: list = []
            if conv_chunks:
                for cp in conv_chunks:
                    conversations_raw.extend(norm_load_json(cp))
            else:
                conversations_raw = norm_load_json(conv_single)

            projects_path = find_file(self.export_dir, ["projects.json"])
            projects_map = parse_projects(norm_load_json(projects_path)) if projects_path else {}

            memory_path = find_file(self.export_dir, ["memory.json", "memories.json"])
            memory_entries = parse_memory(norm_load_json(memory_path)) if memory_path else []

            canonical = build_canonical(conversations_raw, projects_map, memory_entries, "chatgpt")
            config = generate_config(canonical, None, projects_map or None)

            workspace_dir = self.export_dir.parent / "migration_workspace" / "canonical"
            workspace_dir.mkdir(parents=True, exist_ok=True)
            canonical_path = workspace_dir / "canonical_workspace.json"
            canonical_path.write_text(
                json.dumps(canonical, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
            )
            if not conversations_raw:
                self.error.emit(tr("p1_no_conversations"))
                return

            config["_canonical_path"] = str(canonical_path)
            config["_export_dir"] = str(self.export_dir)
            config["_conversations_count"] = len(conversations_raw)
            self.finished.emit(config)
        except Exception as e:
            self.error.emit(str(e))


class MigrateWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, config: dict, export_dir: Path, canonical_path: Path, is_pro: bool = False):
        super().__init__()
        self.config, self.export_dir = config, export_dir
        self.canonical_path, self.is_pro = canonical_path, is_pro

    def run(self):
        try:
            canonical = load_json(self.canonical_path)
            folder_map = self.config.get("folder_map", {})
            project_instructions = {
                k: v for k, v in self.config.get("project_instructions", {}).items()
                if k != "_comment" and v
            }
            image_base_url = self.config.get("image_base_url", "")

            self.progress.emit("Building image map...")
            image_map = build_image_map(self.export_dir, None)

            self.progress.emit("Building folders...")
            folders, title_to_id = build_folder_structure([], folder_map, project_instructions)

            pid_to_folder_id = {}
            for pid, entry in folder_map.items():
                folder_title = entry.get("folder") or f"Projekt {pid[:12]}"
                pid_to_folder_id[pid] = title_to_id.get(folder_title)

            conv_single = self.export_dir / "conversations.json"
            conv_chunks = sorted(self.export_dir.glob("conversations-[0-9]*.json"))
            raw_convs: list = []
            if conv_chunks:
                for cp in conv_chunks:
                    raw_convs.extend(load_json(cp))
            elif conv_single.is_file():
                raw_convs = load_json(conv_single)
            raw_by_id = {(c.get("id") or c.get("conversation_id") or ""): c for c in raw_convs}

            chats = []
            total = len(canonical["conversations"])
            for i, conv in enumerate(canonical["conversations"], 1):
                if i % 50 == 0:
                    self.progress.emit(f"Converting chat {i}/{total}...")
                cid = conv["conversation_id"]
                raw = raw_by_id.get(cid)
                if not raw:
                    continue
                pid = conv.get("project_id")
                folder_id = pid_to_folder_id.get(pid) if pid else None
                tm_chat = chatgpt_conv_to_tm(raw, folder_id, image_map, image_base_url, self.export_dir)
                chats.append(tm_chat)

            if not self.is_pro and len(chats) > FREE_CHAT_LIMIT:
                total_found = len(chats)
                chats.sort(key=lambda c: c.get("createdAt", 0), reverse=True)
                chats = chats[:FREE_CHAT_LIMIT]
                self.progress.emit(tr("p4_free_limit", limit=FREE_CHAT_LIMIT, total=total_found))

            if not chats:
                self.error.emit(
                    "No chats converted. The export may be empty or corrupted.\n"
                    "Keine Chats konvertiert. Der Export ist moeglicherweise leer oder beschaedigt."
                )
                return

            self.progress.emit(f"{len(chats)} chats converted. Writing export...")
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_dir = self.export_dir.parent / "migration_output" / f"typingmind_import_{ts}"
            out_dir.mkdir(parents=True, exist_ok=True)
            export_data = {"data": {"chats": chats, "folders": folders}}
            flat_path = out_dir / "typingmind_import_FLAT.json"
            flat_path.write_text(json.dumps(export_data, ensure_ascii=False) + "\n", encoding="utf-8")
            zip_path = write_zip(out_dir, flat_path)

            self.finished.emit(str(zip_path))
        except Exception as e:
            self.error.emit(str(e))


class UploadWorker(QThread):
    progress = pyqtSignal(str)
    finished = pyqtSignal(int)
    error = pyqtSignal(str)

    def __init__(self, export_dir: Path, account_id: str, access_key: str, secret_key: str, bucket: str):
        super().__init__()
        self.export_dir, self.account_id = export_dir, account_id
        self.access_key, self.secret_key, self.bucket = access_key, secret_key, bucket

    def run(self):
        try:
            import boto3
            from botocore.exceptions import ClientError
            IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".dng"}
            CT = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                  ".gif": "image/gif", ".webp": "image/webp"}

            images = sorted(f for f in self.export_dir.rglob("*")
                            if f.is_file() and f.suffix.lower() in IMG_EXTS)
            seen, deduped = {}, []
            for img in images:
                if img.name not in seen:
                    seen[img.name] = img
                    deduped.append(img)
            images = deduped

            self.progress.emit(f"{len(images)} images found. Starting upload...")
            s3 = boto3.client("s3",
                endpoint_url=f"https://{self.account_id}.r2.cloudflarestorage.com",
                aws_access_key_id=self.access_key,
                aws_secret_access_key=self.secret_key, region_name="auto")

            uploaded, skipped = 0, 0
            for i, img in enumerate(images, 1):
                key = img.name
                try:
                    head = s3.head_object(Bucket=self.bucket, Key=key)
                    if head["ContentLength"] == img.stat().st_size:
                        skipped += 1
                        if i % 100 == 0:
                            self.progress.emit(f"[{i}/{len(images)}] {skipped} skipped, {uploaded} uploaded")
                        continue
                except ClientError as e:
                    if e.response["Error"]["Code"] != "404":
                        raise
                with open(img, "rb") as f:
                    s3.put_object(Bucket=self.bucket, Key=key, Body=f,
                                  ContentType=CT.get(img.suffix.lower(), "application/octet-stream"))
                uploaded += 1
                if i % 20 == 0 or i == len(images):
                    self.progress.emit(f"[{i}/{len(images)}] {uploaded} uploaded, {skipped} skipped")

            self.progress.emit(f"Done: {uploaded} uploaded, {skipped} skipped")
            self.finished.emit(uploaded)
        except ImportError:
            self.error.emit(tr("err_boto3"))
        except Exception as e:
            err = str(e)
            if "401" in err or "Unauthorized" in err:
                self.error.emit(tr("err_r2_401"))
            elif "403" in err or "Forbidden" in err:
                self.error.emit(tr("err_r2_403"))
            else:
                self.error.emit(f"Upload error: {e}")


class LicenseActivateWorker(QThread):
    finished = pyqtSignal(bool, str)
    def __init__(self, key: str):
        super().__init__()
        self.key = key
    def run(self):
        success, msg = license_activate(self.key)
        self.finished.emit(success, msg)


# ===================================================================
# R2 Setup Guide Dialog
# ===================================================================

class R2GuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("r2_guide_title"))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(650, 550)
        layout = QVBoxLayout()
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        html = R2_GUIDE_DE if get_language() == "de" else R2_GUIDE_EN
        browser.setHtml(html)
        layout.addWidget(browser)
        close_btn = QPushButton(tr("lic_close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)


# ===================================================================
# License Dialog
# ===================================================================

class LicenseDialog(QDialog):
    license_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("lic_title"))
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setMinimumSize(500, 320)
        self._worker: Optional[LicenseActivateWorker] = None

        layout = QVBoxLayout()
        layout.setSpacing(12)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        layout.addWidget(QLabel(tr("lic_key_label")))
        key_layout = QHBoxLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX")
        key_layout.addWidget(self.key_edit)
        self.activate_btn = QPushButton(tr("lic_activate"))
        self.activate_btn.clicked.connect(self._activate)
        key_layout.addWidget(self.activate_btn)
        layout.addLayout(key_layout)

        self.result_label = QLabel("")
        self.result_label.setWordWrap(True)
        layout.addWidget(self.result_label)

        buy_label = QLabel(
            f'<a href="https://workbenchdigital.gumroad.com/l/oemkn">{tr("lic_buy")}</a>'
        )
        buy_label.setOpenExternalLinks(True)
        layout.addWidget(buy_label)

        compare = QLabel(tr("lic_compare"))
        compare.setStyleSheet("color: #888;")
        layout.addWidget(compare)

        layout.addStretch()
        close_btn = QPushButton(tr("lic_close"))
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)
        self.setLayout(layout)
        self._update_status()

    def _update_status(self):
        info = get_license_info()
        if info:
            self.status_label.setText(tr("lic_pro_active", email=info.get("email", "?")))
            self.status_label.setStyleSheet("color: #008800; font-weight: bold; font-size: 13px; padding: 6px;")
        else:
            self.status_label.setText(tr("lic_free"))
            self.status_label.setStyleSheet("color: #cc6600; font-weight: bold; font-size: 13px; padding: 6px;")

    def _activate(self):
        key = self.key_edit.text().strip()
        if not key:
            self.result_label.setText(tr("lic_empty_key"))
            self.result_label.setStyleSheet("color: #cc0000;")
            return
        self.activate_btn.setEnabled(False)
        self.result_label.setText(tr("lic_validating"))
        self.result_label.setStyleSheet("color: #0066cc;")
        self._worker = LicenseActivateWorker(key)
        self._worker.finished.connect(self._on_result)
        self._worker.start()

    def _on_result(self, success: bool, msg: str):
        self.activate_btn.setEnabled(True)
        if success:
            self.result_label.setText(f"{tr('lic_activated')} ({msg})")
            self.result_label.setStyleSheet("color: #008800;")
            self._update_status()
            self.license_changed.emit(True)
        else:
            self.result_label.setText(f"Error: {msg}")
            self.result_label.setStyleSheet("color: #cc0000;")


# ===================================================================
# Wizard Pages
# ===================================================================

class ExportSelectPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self._config: Optional[dict] = None
        self._worker: Optional[DiscoverWorker] = None

    def initializePage(self):
        self.setTitle(tr("p1_title"))
        self.setSubTitle(tr("p1_subtitle"))

        if not self.layout():
            layout = QVBoxLayout()
            path_layout = QHBoxLayout()
            self.path_edit = QLineEdit()
            path_layout.addWidget(self.path_edit)
            self.browse_btn = QPushButton()
            self.browse_btn.clicked.connect(self._browse)
            path_layout.addWidget(self.browse_btn)
            layout.addLayout(path_layout)

            self.analyze_btn = QPushButton()
            self.analyze_btn.setMinimumHeight(36)
            self.analyze_btn.setStyleSheet("font-weight: bold;")
            self.analyze_btn.clicked.connect(self._analyze)
            layout.addWidget(self.analyze_btn)

            self.status_label = QLabel("")
            self.status_label.setWordWrap(True)
            layout.addWidget(self.status_label)
            layout.addStretch()
            self.setLayout(layout)

        # Texte aktualisieren (bei jedem Sprachwechsel)
        self.path_edit.setPlaceholderText(tr("p1_placeholder"))
        self.browse_btn.setText(tr("p1_browse"))
        self.analyze_btn.setText(tr("p1_analyze"))
        self.analyze_btn.setToolTip(tr("p1_analyze_tooltip"))
        # Status-Text aktualisieren wenn bereits analysiert
        if self._config:
            fm = self._config.get("folder_map", {})
            n_proj = sum(1 for v in fm.values() if v.get("type") == "project")
            n_gpt = sum(1 for v in fm.values() if v.get("type") == "gpt")
            self.status_label.setText(tr("p1_done",
                chats=self._config.get("_conversations_count", 0), proj=n_proj, gpt=n_gpt))

    def _browse(self):
        folder = QFileDialog.getExistingDirectory(self, tr("p1_browse"))
        if folder:
            self.path_edit.setText(folder)

    def isComplete(self):
        return self._config is not None

    def _analyze(self):
        export_dir = Path(self.path_edit.text().strip())
        if not export_dir.is_dir():
            QMessageBox.warning(self, "Error", tr("p1_no_folder"))
            return
        self.analyze_btn.setEnabled(False)
        self.status_label.setText(tr("p1_analyzing"))
        self.status_label.setStyleSheet("color: #0066cc;")
        self._worker = DiscoverWorker(export_dir)
        self._worker.progress.connect(lambda m: self.status_label.setText(m))
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_finished(self, config: dict):
        self._config = config
        fm = config.get("folder_map", {})
        n_proj = sum(1 for v in fm.values() if v.get("type") == "project")
        n_gpt = sum(1 for v in fm.values() if v.get("type") == "gpt")
        self.status_label.setText(tr("p1_done",
            chats=config.get("_conversations_count", 0), proj=n_proj, gpt=n_gpt))
        self.status_label.setStyleSheet("color: #008800;")
        self.analyze_btn.setEnabled(True)
        self.completeChanged.emit()

    def _on_error(self, msg: str):
        self.status_label.setText(msg)
        self.status_label.setStyleSheet("color: #cc0000;")
        self.analyze_btn.setEnabled(True)


class FolderConfigPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self._pid_order: list = []
        self._built = False

    def initializePage(self):
        self.setTitle(tr("p2_title"))
        self.setSubTitle(tr("p2_subtitle"))

        if not self._built:
            layout = QVBoxLayout()
            self.table = QTableWidget()
            self.table.setColumnCount(4)
            layout.addWidget(self.table)

            self.hint_label = QLabel()
            self.hint_label.setWordWrap(True)
            self.hint_label.setStyleSheet("color: #887700; padding: 8px; background: #fef9e7; border-radius: 4px;")
            layout.addWidget(self.hint_label)
            self.setLayout(layout)
            self._built = True

        self.hint_label.setText(tr("p2_hint"))
        self.table.setHorizontalHeaderLabels([
            tr("p2_col_folder"), tr("p2_col_parent"), tr("p2_col_chats"), tr("p2_col_samples")
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)

        page1: ExportSelectPage = self.wizard().page(0)
        if not page1 or not hasattr(page1, "_config") or not page1._config:
            return
        config = page1._config
        folder_map = config.get("folder_map", {})
        self.table.setRowCount(len(folder_map))
        self._pid_order = list(folder_map.keys())

        for row, pid in enumerate(self._pid_order):
            entry = folder_map[pid]
            self.table.setItem(row, 0, QTableWidgetItem(entry.get("folder", "")))
            self.table.setItem(row, 1, QTableWidgetItem(entry.get("parent") or ""))
            count_item = QTableWidgetItem(str(entry.get("conversations", 0)))
            count_item.setFlags(count_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 2, count_item)
            samples = entry.get("sample_titles", [])
            sample_text = ", ".join(samples[:3])
            if len(samples) > 3:
                sample_text += f" (+{len(samples)-3})"
            sample_item = QTableWidgetItem(sample_text)
            sample_item.setFlags(sample_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 3, sample_item)

    def get_folder_map(self) -> Dict[str, Dict]:
        page1: ExportSelectPage = self.wizard().page(0)
        if not page1 or not page1._config:
            return {}
        folder_map = dict(page1._config.get("folder_map", {}))
        for row, pid in enumerate(self._pid_order):
            if pid in folder_map:
                folder_map[pid]["folder"] = self.table.item(row, 0).text().strip()
                folder_map[pid]["parent"] = self.table.item(row, 1).text().strip() or None
        return folder_map


class ImageHostingPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self._built = False
        self._upgrade_added = False

    def initializePage(self):
        self.setTitle(tr("p3_title"))
        self.setSubTitle(tr("p3_subtitle"))

        if not self._built:
            layout = QVBoxLayout()
            self.enable_check = QCheckBox()
            self.enable_check.toggled.connect(self._toggle_fields)
            layout.addWidget(self.enable_check)

            # R2 Guide Button
            self.guide_btn = QPushButton()
            self.guide_btn.clicked.connect(self._show_r2_guide)
            layout.addWidget(self.guide_btn)

            self.r2_group = QGroupBox("Cloudflare R2")
            r2_layout = QVBoxLayout()
            self.account_id = QLineEdit(); self.account_id.setPlaceholderText("Account ID")
            r2_layout.addWidget(QLabel("Account ID:")); r2_layout.addWidget(self.account_id)
            self.access_key = QLineEdit(); self.access_key.setPlaceholderText("Access Key ID")
            r2_layout.addWidget(QLabel("Access Key ID:")); r2_layout.addWidget(self.access_key)
            self.secret_key = QLineEdit(); self.secret_key.setPlaceholderText("Secret Access Key")
            self.secret_key.setEchoMode(QLineEdit.EchoMode.Password)
            r2_layout.addWidget(QLabel("Secret Access Key:")); r2_layout.addWidget(self.secret_key)
            self.bucket = QLineEdit(); self.bucket.setPlaceholderText("typingmind-images")
            r2_layout.addWidget(QLabel("Bucket Name:")); r2_layout.addWidget(self.bucket)
            self.public_url = QLineEdit(); self.public_url.setPlaceholderText("https://pub-XXXX.r2.dev")
            r2_layout.addWidget(QLabel("Public URL:")); r2_layout.addWidget(self.public_url)
            self.r2_group.setLayout(r2_layout)
            self.r2_group.setVisible(False)
            layout.addWidget(self.r2_group)
            layout.addStretch()
            self.setLayout(layout)
            self._built = True

        # Texte aktualisieren
        self.enable_check.setText(tr("p3_enable"))
        self.guide_btn.setText(tr("p3_r2_help_btn"))

        is_pro = getattr(self.wizard(), "_is_pro", False)
        if not is_pro and not self._upgrade_added:
            self.enable_check.setEnabled(False)
            upgrade = QLabel(tr("p3_upgrade"))
            upgrade.setWordWrap(True)
            upgrade.setStyleSheet("color: #cc6600; padding: 8px; background: #fff3e0; border-radius: 4px;")
            self.layout().insertWidget(1, upgrade)
            self._upgrade_added = True
        elif is_pro:
            self.enable_check.setEnabled(True)

    def _toggle_fields(self, checked: bool):
        self.r2_group.setVisible(checked)

    def _show_r2_guide(self):
        R2GuideDialog(self).exec()


class MigrationPage(QWizardPage):
    def __init__(self):
        super().__init__()
        self._built = False
        self._zip_path: Optional[str] = None
        self._timeout_timer: Optional[QTimer] = None
        self._WORKER_TIMEOUT_MS = 10 * 60 * 1000  # 10 Minuten

    def initializePage(self):
        self.setTitle(tr("p4_title"))
        self.setSubTitle(tr("p4_subtitle"))

        if not self._built:
            layout = QVBoxLayout()
            self.start_btn = QPushButton()
            self.start_btn.setMinimumHeight(40)
            self.start_btn.setStyleSheet("font-weight: bold;")
            self.start_btn.clicked.connect(self._start)
            layout.addWidget(self.start_btn)

            self.progress_bar = QProgressBar()
            self.progress_bar.setRange(0, 0)
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

            self.open_btn = QPushButton()
            self.open_btn.setVisible(False)
            self.open_btn.clicked.connect(self._open_output)
            layout.addWidget(self.open_btn)
            self.setLayout(layout)
            self._built = True

        # Texte aktualisieren
        self.start_btn.setText(tr("p4_start"))
        self.open_btn.setText(tr("p4_open_folder"))

    def _log(self, msg: str):
        self.log.append(msg)

    def _start(self):
        self.start_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.log.clear()

        # Timeout-Timer starten
        self._timeout_timer = QTimer()
        self._timeout_timer.setSingleShot(True)
        self._timeout_timer.timeout.connect(self._on_timeout)
        self._timeout_timer.start(self._WORKER_TIMEOUT_MS)

        wizard = self.wizard()
        page1: ExportSelectPage = wizard.page(0)
        page2: FolderConfigPage = wizard.page(1)
        page3: ImageHostingPage = wizard.page(2)

        if not page1 or not hasattr(page1, "_config") or not page1._config:
            self._on_error(tr("p4_no_export"))
            return

        config = json.loads(json.dumps(page1._config))
        config["folder_map"] = page2.get_folder_map()
        export_dir = Path(config["_export_dir"])

        r2_enabled = page3.enable_check.isChecked()
        if r2_enabled:
            config["image_base_url"] = page3.public_url.text().strip()
            self._log("=== Image Upload ===")
            self._upload_worker = UploadWorker(
                export_dir,
                page3.account_id.text().strip(),
                page3.access_key.text().strip(),
                page3.secret_key.text().strip(),
                page3.bucket.text().strip(),
            )
            self._upload_worker.progress.connect(self._log)
            self._upload_worker.finished.connect(lambda c: self._start_migration(config, export_dir))
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
        self._stop_timeout()
        self._zip_path = zip_path
        self.progress_bar.setVisible(False)

        # Log-Output mit Anleitung
        self._log(f"\nZIP: {zip_path}")
        self._log("\n" + "=" * 55)
        self._log(f"  {tr('p4_finish_title')}")
        self._log("=" * 55)
        self._log("")
        self._log(tr("p4_step1_title"))
        self._log("-" * 45)
        self._log(tr("p4_step1"))
        self._log("")
        self._log(tr("p4_step2_title"))
        self._log("-" * 45)
        self._log(tr("p4_step2"))
        self._log("")
        self._log(tr("p4_tip_title"))
        self._log("-" * 45)
        self._log(tr("p4_tip"))
        self._log("")

        # Auffaelliger Cloud-Sync Hinweis als separates UI-Element
        cloud_hint = QLabel(tr("p4_cloud_warning"))
        cloud_hint.setWordWrap(True)
        cloud_hint.setTextFormat(Qt.TextFormat.RichText)
        cloud_hint.setStyleSheet(
            "padding: 12px; background: #fff3e0; border: 2px solid #ff9800; "
            "border-radius: 6px; color: #333; font-size: 12px;"
        )
        self.layout().insertWidget(self.layout().indexOf(self.open_btn), cloud_hint)

        self.open_btn.setVisible(True)

    def _stop_timeout(self):
        if self._timeout_timer and self._timeout_timer.isActive():
            self._timeout_timer.stop()

    def _on_timeout(self):
        self.progress_bar.setVisible(False)
        self._log(
            "\nTIMEOUT: Operation took longer than 10 minutes and was stopped.\n"
            "TIMEOUT: Die Operation hat laenger als 10 Minuten gedauert und wurde gestoppt."
        )
        self.start_btn.setEnabled(True)

    def _on_error(self, msg: str):
        self._stop_timeout()
        self.progress_bar.setVisible(False)
        self._log(f"\nERROR: {msg}")
        self.start_btn.setEnabled(True)

    def _open_output(self):
        if self._zip_path:
            os.startfile(str(Path(self._zip_path).parent))


# ===================================================================
# Wizard
# ===================================================================

class MigrationWizard(QWizard):
    def __init__(self):
        super().__init__()
        self._is_pro = license_is_pro()
        self._update_title()
        self.setMinimumSize(850, 650)
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)

        self._update_buttons()

        # Language Toggle Button
        self._lang_btn = QPushButton("DE / EN")
        self._lang_btn.setFixedWidth(80)
        self._lang_btn.clicked.connect(self._toggle_language)
        self._update_lang_btn()

        # License Button
        license_btn = QPushButton(tr("btn_license"))
        license_btn.clicked.connect(self._show_license)

        self.setButton(QWizard.WizardButton.CustomButton1, license_btn)
        self.setOption(QWizard.WizardOption.HaveCustomButton1, True)
        self.setButton(QWizard.WizardButton.CustomButton2, self._lang_btn)
        self.setOption(QWizard.WizardOption.HaveCustomButton2, True)

        self.addPage(ExportSelectPage())
        self.addPage(FolderConfigPage())
        self.addPage(ImageHostingPage())
        self.addPage(MigrationPage())

    def _update_title(self):
        key = "wizard_title_pro" if self._is_pro else "wizard_title_free"
        self.setWindowTitle(tr(key))

    def _update_buttons(self):
        self.setButtonText(QWizard.WizardButton.NextButton, tr("btn_next"))
        self.setButtonText(QWizard.WizardButton.BackButton, tr("btn_back"))
        self.setButtonText(QWizard.WizardButton.CancelButton, tr("btn_cancel"))
        self.setButtonText(QWizard.WizardButton.FinishButton, tr("btn_finish"))

    def _update_lang_btn(self):
        lang = get_language()
        self._lang_btn.setText("Deutsch" if lang == "en" else "English")
        self._lang_btn.setToolTip("Sprache wechseln" if lang == "de" else "Switch language")

    def _toggle_language(self):
        new_lang = "de" if get_language() == "en" else "en"
        set_language(new_lang)
        self._update_title()
        self._update_buttons()
        self._update_lang_btn()
        current = self.currentPage()
        if current:
            current.initializePage()

    def _show_license(self):
        dlg = LicenseDialog(self)
        dlg.license_changed.connect(self._on_license_changed)
        dlg.exec()

    def _on_license_changed(self, is_pro: bool):
        self._is_pro = is_pro
        self._update_title()


# ===================================================================
# Main
# ===================================================================

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    set_language("en")  # Default English
    wizard = MigrationWizard()
    wizard.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
