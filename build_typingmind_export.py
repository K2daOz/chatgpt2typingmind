#!/usr/bin/env python3
"""
build_typingmind_export.py

Erzeugt einen vollstaendigen TypingMind-Import aus:
  - bestehendem TypingMind-Export (Ordner + TM-native Chats erhalten)
  - canonical_workspace.json (ChatGPT-Chats mit Projektzuordnungen)
  - Original conversations.json (Rohformat fuer Nachrichten)
  - config.json (Projektanweisungen, Output-Einstellungen)

Strategie:
  - TM-native Chats (kurze alphanumerische IDs) bleiben unveraendert
  - ChatGPT-Chats (UUID-Format) werden aus canonical_workspace gebaut
    und erhalten korrekte folderID gemaess PROJECT_FOLDER_MAP
  - Fehlende Ordner werden automatisch angelegt
  - Ordner erhalten systemMessage aus config.json (Project context & instructions)
  - Verfuegbare Bilder aus dem Export werden als base64 eingebettet
  - Nicht verfuegbare sediment://-Referenzen werden als Platzhalter ausgegeben
  - Output: chunked Export + flat JSON + ZIP (konfigurierbar)

Verwendung:
    python build_typingmind_export.py \
        --tm-export   ./20260331_200345_typingmind_export \
        --canonical   ./migration_workspace/canonical/canonical_workspace.json \
        --chatgpt-raw ./chatgptexport2023-02-16/conversations.json \
        --export-dir  ./chatgptexport2023-02-16 \
        --out         ./migration_workspace/rehydration/typingmind_import_final \
        --config      ./Projektinformationen/config.json
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
import os
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote as url_quote


# ---------------------------------------------------------------------------
# Mapping: ChatGPT Projekt-ID -> (TM-Ordner-Titel, Eltern-Ordner-Titel|None)
# ---------------------------------------------------------------------------

# PROJECT_FOLDER_MAP wird dynamisch aus config.json geladen (siehe discover.py)

# UUID-Muster = aus ChatGPT importiert
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)
SEDIMENT_RE = re.compile(r"sediment://file_([0-9a-f]+)")
FILESERVICE_RE = re.compile(r"file-service://file-([A-Za-z0-9]+)")

NOW = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
CHUNK_SIZE = 500  # Chats pro Chunk-Datei


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def new_folder_id() -> str:
    return f"fo-{uuid.uuid4()}"


def is_chatgpt_id(chat_id: str) -> bool:
    return bool(UUID_RE.match(chat_id or ""))


def load_config(config_path: Optional[Path]) -> Dict:
    """Laedt config.json, gibt leeres Dict zurueck wenn nicht vorhanden."""
    if config_path and config_path.exists():
        try:
            cfg = load_json(config_path)
            print(f"  Config geladen: {config_path}")
            return cfg
        except Exception as e:
            print(f"  Warnung: config.json konnte nicht geladen werden: {e}")
    return {}


# ---------------------------------------------------------------------------
# Bild-Lookup aus ChatGPT-Export aufbauen
# ---------------------------------------------------------------------------

def build_image_map(
    export_dir: Optional[Path],
    image_mapping_path: Optional[Path] = None,
) -> Dict[str, str]:
    """
    Baut eine Lookup-Tabelle fuer Bild-Referenzen.
    Gibt Dict {referenz_key -> clean_filename} zurueck.

    Wenn image_mapping_path angegeben: laedt _image_mapping.json.
    Sonst: baut Map direkt aus Export-Ordner.

    Referenz-Keys:
      - "sediment:HEX" fuer sediment://file_HEX
      - "fileservice:ID" fuer file-service://file-ID
    """
    image_map: Dict[str, str] = {}

    # Bevorzugt: vorbereitete _image_mapping.json
    if image_mapping_path and image_mapping_path.exists():
        try:
            image_map = json.loads(image_mapping_path.read_text(encoding="utf-8"))
            print(f"  Bild-Mapping geladen: {len(image_map)} Eintraege")
            return image_map
        except Exception as e:
            print(f"  Warnung: Bild-Mapping nicht lesbar: {e}")

    if not export_dir or not export_dir.exists():
        return {}

    # Fallback: direkt aus Export-Ordner bauen (inkl. Unterordner)
    scan_dirs = [export_dir]
    # User-Unterordner (user-XXXX) und dalle-generations durchsuchen
    for subdir in export_dir.iterdir():
        if subdir.is_dir() and (subdir.name.startswith("user-") or subdir.name == "dalle-generations"):
            scan_dirs.append(subdir)

    for scan_dir in scan_dirs:
        for fname in os.listdir(scan_dir):
            fpath = scan_dir / fname
            if not fpath.is_file():
                continue
            # Nur Dateinamen speichern (kein Pfad) — muss mit R2-Key uebereinstimmen
            if "-sanitized." in fname and fname.startswith("file_"):
                hex_part = fname.split("-sanitized.")[0].replace("file_", "")
                image_map[f"sediment:{hex_part}"] = fname
            elif fname.startswith("file-") or fname.startswith("file_"):
                parts = fname.split("-", 1)
                if len(parts) > 1 and fname.startswith("file-"):
                    id_part = parts[1].split("-")[0]
                    image_map[f"fileservice:{id_part}"] = fname
                elif fname.startswith("file_") and "-sanitized." not in fname:
                    hex_part = fname.split("-")[0].replace("file_", "")
                    if f"sediment:{hex_part}" not in image_map:
                        image_map[f"sediment:{hex_part}"] = fname

    print(f"  Bilder im Export: {len(image_map)} Dateien indiziert")
    return image_map


def image_to_data_uri(file_path: Path) -> str:
    """Konvertiert Bilddatei zu base64 data URI."""
    mime, _ = mimetypes.guess_type(str(file_path))
    if not mime:
        mime = "image/png"
    data = file_path.read_bytes()
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# Ordnerstruktur aufbauen
# ---------------------------------------------------------------------------

def build_folder_structure(
    existing_folders: List[Dict],
    folder_map: Dict[str, Dict],
    project_instructions: Dict[str, str],
) -> Tuple[List[Dict], Dict[str, str]]:
    """
    Gibt (erweiterte Ordnerliste, {ordner_titel -> folder_id}) zurueck.
    Legt fehlende Ordner an, bestehende bleiben unveraendert (ausser systemMessage).

    folder_map: Dict aus config.json, Format:
      { project_id: { "folder": "Name", "parent": "Eltern-Name" | null, ... } }
    """
    folders = [dict(f) for f in existing_folders]
    title_to_id: Dict[str, str] = {f["title"]: f["id"] for f in folders}

    # Welche Ordner werden benoetigt?
    needed: Dict[str, Optional[str]] = {}  # titel -> elterntitel
    for pid, entry in folder_map.items():
        title = entry.get("folder") or f"Projekt {pid[:12]}"
        parent = entry.get("parent")
        needed[title] = parent

    def _ensure_folder(title: str, parent_title: Optional[str]) -> str:
        """Legt einen Ordner an (und ggf. dessen Eltern), gibt die ID zurueck."""
        if title in title_to_id:
            return title_to_id[title]

        # Eltern-Ordner zuerst sicherstellen
        parent_id: Optional[str] = None
        parent_depth = 0
        if parent_title:
            parent_id = _ensure_folder(parent_title, None)
            parent_obj = next((f for f in folders if f["id"] == parent_id), None)
            parent_depth = parent_obj.get("depth", 0) if parent_obj else 0

        new_id = new_folder_id()
        new_folder: Dict[str, Any] = {
            "id": new_id,
            "depth": parent_depth + 1 if parent_id else 0,
            "order": len(folders),
            "title": title,
            "children": [],
            "childrenCount": 0,
            "createdAt": NOW,
            "updatedAt": NOW,
            "syncedAt": NOW,
            "deletedAt": None,
        }
        if parent_id:
            new_folder["parentID"] = parent_id

        folders.append(new_folder)
        title_to_id[title] = new_id
        print(f"  + Neuer Ordner: '{title}'"
              + (f" (unter '{parent_title}')" if parent_title else ""))
        return new_id

    # Fehlende anlegen (Eltern werden automatisch miterstellt)
    for title, parent_title in needed.items():
        _ensure_folder(title, parent_title)

    # Tiefe normalisieren: parentID vorhanden aber depth=0 korrigieren
    id_to_folder = {f["id"]: f for f in folders}

    def _compute_depth(folder_id: str, visited: set) -> int:
        if folder_id in visited:
            return 0  # Zyklus-Schutz
        visited.add(folder_id)
        fo = id_to_folder.get(folder_id)
        if not fo:
            return 0
        pid = fo.get("parentID")
        if not pid:
            return 0
        return _compute_depth(pid, visited) + 1

    for fo in folders:
        correct_depth = _compute_depth(fo["id"], set())
        if fo.get("depth") != correct_depth:
            fo["depth"] = correct_depth

    # systemMessage aus config in Ordner-settings schreiben
    instructions_set = 0
    for folder in folders:
        title = folder.get("title", "")
        instruction = project_instructions.get(title, "")
        if instruction:
            if not isinstance(folder.get("settings"), dict):
                folder["settings"] = {}
            existing_msg = folder["settings"].get("systemMessage", "")
            if not existing_msg:
                folder["settings"]["systemMessage"] = instruction
                instructions_set += 1
                print(f"  -> systemMessage gesetzt: '{title}' ({len(instruction)} Zeichen)")

    if instructions_set:
        print(f"  Projektanweisungen gesetzt: {instructions_set} Ordner")

    return folders, title_to_id


# ---------------------------------------------------------------------------
# ChatGPT-Nachrichten -> TypingMind-Format konvertieren
# ---------------------------------------------------------------------------

def extract_message_text(
    content: Any,
    image_map: Dict[str, str],
    image_base_url: str,
    export_dir: Optional[Path],
) -> str:
    """
    Reduziert ChatGPT-Content auf lesbaren String.
    Bild-Referenzen werden aufgeloest:
      - Mit image_base_url: als ![Bild](url/filename) (externe URL)
      - Ohne: als [Bild: dateiname] (nur Platzhalter)
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return _resolve_image_refs(content, image_map, image_base_url, export_dir)
    if not isinstance(content, dict):
        return str(content)

    ct = content.get("content_type", "")

    if ct == "text":
        parts = content.get("parts") or []
        text = "\n".join(p for p in parts if isinstance(p, str) and p)
        return _resolve_image_refs(text, image_map, image_base_url, export_dir)

    if ct == "code":
        lang = content.get("language") or ""
        text = content.get("text") or ""
        return f"```{lang}\n{text}\n```"

    if ct == "tether_quote":
        title = content.get("title") or ""
        url = content.get("url") or ""
        text = content.get("text") or ""
        header = f"[{title}]({url})" if url else title
        return f"{header}\n{text}".strip()

    if ct in {"multimodal_text", "real_time_user_audio_video_asset_pointer"}:
        parts = content.get("parts") or []
        chunks = []
        for part in parts:
            if isinstance(part, str):
                chunks.append(_resolve_image_refs(part, image_map, image_base_url, export_dir))
            elif isinstance(part, dict):
                sub_ct = part.get("content_type", "")
                if sub_ct == "image_asset_pointer":
                    ptr = part.get("asset_pointer", "")
                    chunks.append(_resolve_image_pointer(ptr, image_map, image_base_url, export_dir))
                else:
                    chunks.append(f"[{sub_ct}]")
        return "\n".join(chunks)

    if ct == "system_error":
        return f"[System-Fehler: {content.get('text', '')}]"

    # Fallback
    try:
        return json.dumps(content, ensure_ascii=False)
    except Exception:
        return str(content)


def _make_image_tag(filename: str, image_base_url: str, export_dir: Optional[Path]) -> str:
    """
    Erzeugt Bilddarstellung fuer eine Bilddatei.

    Prioritaet:
      1. image_base_url gesetzt  -> ![Bild](url/filename)  (externe URL, z.B. CDN)
      2. Bilddatei lokal vorhanden -> ![Bild](data:image/...;base64,...)  (eingebettet)
      3. Fallback               -> [Bild: filename]  (Platzhalter)
    """
    if image_base_url:
        url = f"{image_base_url.rstrip('/')}/{url_quote(filename, safe='/')}"
        return f"![Bild]({url})"

    # Base64-Einbettung aus migration_workspace/images/
    if export_dir:
        images_dir = export_dir.parent / "migration_workspace" / "images"
        img_path = images_dir / filename
        if img_path.exists():
            try:
                return f"![Bild]({image_to_data_uri(img_path)})"
            except Exception:
                pass

    return f"[Bild: {filename}]"


def _resolve_image_pointer(
    ptr: str,
    image_map: Dict[str, str],
    image_base_url: str,
    export_dir: Optional[Path],
) -> str:
    """Loest einen asset_pointer auf (sediment:// oder file-service://)."""
    if not ptr:
        return "[Bild: kein Verweis]"

    # sediment://file_HEX
    m = SEDIMENT_RE.search(ptr)
    if m:
        hex_id = m.group(1)
        key = f"sediment:{hex_id}"
        if key in image_map:
            return _make_image_tag(image_map[key], image_base_url, export_dir)
        return "[Bild: nicht im Export enthalten]"

    # file-service://file-XXX
    m = FILESERVICE_RE.search(ptr)
    if m:
        fs_id = m.group(1)
        key = f"fileservice:{fs_id}"
        if key in image_map:
            return _make_image_tag(image_map[key], image_base_url, export_dir)
        return "[Bild: nicht im Export enthalten]"

    return f"[Bild: {ptr}]"


def _resolve_image_refs(
    text: str,
    image_map: Dict[str, str],
    image_base_url: str,
    export_dir: Optional[Path],
) -> str:
    """Ersetzt sediment:// und file-service:// Referenzen im Freitext."""
    if "sediment://" not in text and "file-service://" not in text:
        return text

    def sed_replacer(m: re.Match) -> str:
        hex_id = m.group(1)
        key = f"sediment:{hex_id}"
        if key in image_map:
            return _make_image_tag(image_map[key], image_base_url, export_dir)
        return "[Bild: nicht im Export enthalten]"

    def fs_replacer(m: re.Match) -> str:
        fs_id = m.group(1)
        key = f"fileservice:{fs_id}"
        if key in image_map:
            return _make_image_tag(image_map[key], image_base_url, export_dir)
        return "[Bild: nicht im Export enthalten]"

    text = SEDIMENT_RE.sub(sed_replacer, text)
    text = FILESERVICE_RE.sub(fs_replacer, text)
    return text


def traverse_mapping(
    mapping: Dict[str, Any],
    image_map: Dict[str, str],
    image_base_url: str,
    export_dir: Optional[Path],
) -> List[Dict]:
    """Linearisiert den ChatGPT-Nachrichtenbaum."""
    if not mapping:
        return []

    all_children: set = set()
    for node in mapping.values():
        all_children.update(node.get("children") or [])

    root_id: Optional[str] = None
    for nid in mapping:
        if nid not in all_children:
            root_id = nid
            break
    if root_id is None:
        root_id = next(iter(mapping))

    messages: List[Dict] = []
    visited: set = set()
    queue = [root_id]

    while queue:
        nid = queue.pop(0)
        if nid in visited or nid not in mapping:
            continue
        visited.add(nid)
        node = mapping[nid]
        raw = node.get("message")
        children = node.get("children") or []

        if raw:
            role_raw = (raw.get("author") or {}).get("role", "unknown")
            role = {"user": "user", "assistant": "assistant",
                    "system": "system", "tool": "tool"}.get(role_raw, "assistant")
            content = extract_message_text(raw.get("content"), image_map, image_base_url, export_dir)

            # Leere System-Platzhalter weglassen
            if not (role == "system" and not content.strip()):
                ts = raw.get("create_time")
                try:
                    iso_ts = (
                        datetime.fromtimestamp(float(ts), tz=timezone.utc)
                        .replace(microsecond=0).isoformat()
                    ) if ts else NOW
                except (OSError, ValueError, OverflowError):
                    iso_ts = NOW

                msg: Dict[str, Any] = {
                    "id": raw.get("id") or str(uuid.uuid4()),
                    "uuid": raw.get("id") or str(uuid.uuid4()),
                    "role": role,
                    "content": content,
                    "createdAt": iso_ts,
                    "updatedAt": iso_ts,
                }
                model = (raw.get("metadata") or {}).get("model_slug")
                if model and role == "assistant":
                    msg["model"] = model
                messages.append(msg)

        queue.extend(children)

    return messages


def chatgpt_conv_to_tm(
    raw_conv: Dict,
    folder_id: Optional[str],
    image_map: Dict[str, str],
    image_base_url: str,
    export_dir: Optional[Path],
) -> Dict:
    """Konvertiert eine ChatGPT-Konversation in ein TypingMind-Chat-Objekt."""
    cid = raw_conv.get("id") or raw_conv.get("conversation_id") or str(uuid.uuid4())
    # Chat-Titel 1:1 aus ChatGPT uebernehmen (keine Transformation)
    title = raw_conv.get("title") or "Untitled"

    mapping = raw_conv.get("mapping") or {}
    messages = traverse_mapping(mapping, image_map, image_base_url, export_dir)

    created_ts = raw_conv.get("create_time")
    updated_ts = raw_conv.get("update_time")

    def ts_iso(ts: Any) -> str:
        if ts:
            try:
                return (datetime.fromtimestamp(float(ts), tz=timezone.utc)
                        .replace(microsecond=0).isoformat())
            except Exception:
                pass
        return NOW

    chat: Dict[str, Any] = {
        "id": cid,
        "chatID": cid,
        "chatTitle": title,
        "messages": messages,
        "createdAt": ts_iso(created_ts),
        "updatedAt": ts_iso(updated_ts),
        "syncedAt": NOW,
        "deletedAt": None,
    }

    if messages:
        first_content = messages[0]["content"]
        preview_text = first_content if isinstance(first_content, str) else ""
        chat["preview"] = preview_text[:200].replace("\n", " ")
        chat["lastMessageCreatedAt"] = messages[-1]["createdAt"]

    if folder_id:
        chat["folderID"] = folder_id

    # ChatGPT-Metadata als TypingMind-Tags uebernehmen
    tags: List[str] = []
    if raw_conv.get("is_starred"):
        tags.append("starred")
    if raw_conv.get("is_pinned"):
        tags.append("pinned")
    if raw_conv.get("is_archived"):
        tags.append("archived")
    if tags:
        chat["tags"] = tags

    return chat


# ---------------------------------------------------------------------------
# Output schreiben
# ---------------------------------------------------------------------------

def write_flat_json(out_dir: Path, all_chats: List[Dict], all_folders: List[Dict]) -> Path:
    """Schreibt einen einzelnen flachen JSON fuer den Browser-Import."""
    flat = {
        "data": {
            "chats": all_chats,
            "folders": all_folders,
        }
    }
    flat_path = out_dir / "typingmind_import_FLAT.json"
    flat_path.write_text(
        json.dumps(flat, ensure_ascii=False),
        encoding="utf-8",
    )
    size_mb = flat_path.stat().st_size / 1024 / 1024
    print(f"  Flat JSON:   {flat_path.name} ({size_mb:.1f} MB)")
    return flat_path


def write_zip(out_dir: Path, flat_path: Path) -> Path:
    """Packt den flachen JSON als ZIP. Intern als data.json (TypingMind erwartet das)."""
    zip_path = out_dir / flat_path.name.replace(".json", ".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.write(flat_path, "data.json")
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  ZIP:         {zip_path.name} ({size_mb:.1f} MB)")
    return zip_path


# ---------------------------------------------------------------------------
# Hauptlogik
# ---------------------------------------------------------------------------

def build_export(
    tm_export_dir: Path,
    canonical_path: Path,
    chatgpt_raw_path: Path,
    export_dir: Optional[Path],
    out_dir: Path,
    config_path: Optional[Path],
) -> None:

    print("Lade Konfiguration und Daten...")
    cfg = load_config(config_path)

    folder_map: Dict[str, Dict] = cfg.get("folder_map", {})
    if not isinstance(folder_map, dict):
        print("  WARNUNG: folder_map in config.json ist ungueltig, verwende leeres Mapping")
        folder_map = {}
    # Malformed Eintraege filtern
    folder_map = {
        pid: entry for pid, entry in folder_map.items()
        if isinstance(entry, dict) and entry.get("folder")
    }
    project_instructions: Dict[str, str] = {
        k: v for k, v in cfg.get("project_instructions", {}).items()
        if k != "_comment" and v
    }
    image_base_url: str = cfg.get("image_base_url", "")
    output_cfg: Dict = cfg.get("output", {"zip": True, "flat_json": True, "chunked": True})

    print(f"  Projektanweisungen in config: {len(project_instructions)}")
    print(f"  image_base_url: {image_base_url or '(nicht gesetzt - Platzhalter-Modus)'}")

    # Bild-Lookup aufbauen
    print("\nBild-Lookup aufbauen...")
    images_dir = (export_dir.parent / "migration_workspace" / "images") if export_dir else None
    image_mapping_path = images_dir / "_image_mapping.json" if images_dir and images_dir.exists() else None
    image_map = build_image_map(export_dir, image_mapping_path)

    # Bestehender TM-Export
    print("\nLade TM-Export...")
    tm_data = load_json(tm_export_dir / "data.json")
    existing_folders: List[Dict] = tm_data["data"]["folders"]

    existing_chats: List[Dict] = []
    for chunk_ref in tm_data["data"]["chats"]["chunks"]:
        chunk_path = tm_export_dir / chunk_ref
        existing_chats.extend(load_json(chunk_path))

    print(f"  TM-Chats gesamt: {len(existing_chats)}")
    print(f"  TM-Ordner: {len(existing_folders)}")

    tm_native = [c for c in existing_chats
                 if not is_chatgpt_id(c.get("id") or c.get("chatID") or "")]
    chatgpt_existing = {
        c.get("id") or c.get("chatID")
        for c in existing_chats
        if is_chatgpt_id(c.get("id") or c.get("chatID") or "")
    }
    print(f"  TM-nativ (bleiben unveraendert): {len(tm_native)}")
    print(f"  ChatGPT-Chats in TM (werden ersetzt): {len(chatgpt_existing)}")

    # Canonical und Raw-Export
    print("\nLade Canonical und ChatGPT-Raw...")
    canonical = load_json(canonical_path)
    raw_convs_list = load_json(chatgpt_raw_path)
    raw_by_id: Dict[str, Dict] = {}
    for c in raw_convs_list:
        cid = c.get("id") or c.get("conversation_id") or ""
        if cid:
            raw_by_id[cid] = c

    print(f"  Canonical: {len(canonical['conversations'])} Konversationen, "
          f"{len(canonical['projects'])} Projekte")

    # Konversation-ID -> Projekt-ID
    conv_to_pid: Dict[str, Optional[str]] = {}
    for c in canonical["conversations"]:
        conv_to_pid[c["conversation_id"]] = c.get("project_id")

    # Ordnerstruktur aufbauen
    print("\nOrdner aufbauen...")
    updated_folders, title_to_id = build_folder_structure(
        existing_folders, folder_map, project_instructions
    )

    # Projekt-ID -> Folder-ID
    pid_to_folder_id: Dict[str, Optional[str]] = {}
    for pid, entry in folder_map.items():
        folder_title = entry.get("folder") or f"Projekt {pid[:12]}"
        pid_to_folder_id[pid] = title_to_id.get(folder_title)

    # ChatGPT-Chats konvertieren
    img_mode = f"URL: {image_base_url}" if image_base_url else "Platzhalter"
    print(f"\nKonvertiere ChatGPT-Chats (Bilder: {img_mode})...")
    chatgpt_chats: List[Dict] = []
    no_raw = 0
    folder_assigned = 0
    folder_none = 0

    total = len(canonical["conversations"])
    for i, conv in enumerate(canonical["conversations"], 1):
        if i % 100 == 0:
            print(f"  ... {i}/{total}")

        cid = conv["conversation_id"]
        raw = raw_by_id.get(cid)
        if not raw:
            no_raw += 1
            continue

        pid = conv.get("project_id")
        folder_id = pid_to_folder_id.get(pid) if pid else None

        if folder_id:
            folder_assigned += 1
        else:
            folder_none += 1

        tm_chat = chatgpt_conv_to_tm(raw, folder_id, image_map, image_base_url, export_dir)
        chatgpt_chats.append(tm_chat)

    print(f"  Konvertiert: {len(chatgpt_chats)}")
    print(f"  Mit Ordner:  {folder_assigned}")
    print(f"  Ohne Ordner (Standalone): {folder_none}")
    if no_raw:
        print(f"  Kein Raw-Eintrag gefunden: {no_raw}")

    # Finale Chat-Liste
    all_chats = tm_native + chatgpt_chats
    print(f"\nGesamte Chats im neuen Export: {len(all_chats)}")

    # Output schreiben
    print(f"\nSchreibe Output nach: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) Chunked Export (fuer TypingMind direkten Import falls unterstuetzt)
    if output_cfg.get("chunked", True):
        chunks: List[Tuple[str, List[Dict]]] = []
        for i in range(0, len(all_chats), CHUNK_SIZE):
            chunk = all_chats[i:i + CHUNK_SIZE]
            chunk_name = f"chunks/chats_part_{len(chunks) + 1}.json"
            chunks.append((chunk_name, chunk))

        metadata: Dict[str, Any] = {}
        for chunk_name, chunk_data in chunks:
            chunk_path = out_dir / chunk_name
            write_json(chunk_path, chunk_data)
            chunk_bytes = chunk_path.stat().st_size
            metadata[chunk_name] = {
                "type": "text/plain",
                "size": chunk_bytes,
                "lastModified": int(datetime.now(timezone.utc).timestamp() * 1000),
            }
            print(f"  {chunk_name}: {len(chunk_data)} Chats ({chunk_bytes / 1024:.0f} KB)")

        data_json: Dict[str, Any] = {
            "data": {
                "chats": {"chunks": [name for name, _ in chunks]},
                "folders": updated_folders,
            }
        }
        data_path = out_dir / "data.json"
        write_json(data_path, data_json)
        metadata["data.json"] = {
            "type": "text/plain",
            "size": data_path.stat().st_size,
            "lastModified": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        write_json(out_dir / "metadata.json", metadata)

    # 2) Flat JSON (ein einzelner File fuer Browser-Import)
    flat_path: Optional[Path] = None
    if output_cfg.get("flat_json", True):
        print("\nErstelle Flat-JSON...")
        flat_path = write_flat_json(out_dir, all_chats, updated_folders)

    # 3) ZIP des Flat-JSON
    if output_cfg.get("zip", True) and flat_path:
        print("Erstelle ZIP...")
        zip_path = write_zip(out_dir, flat_path)

    # Zusammenfassung
    print("\n" + "=" * 50)
    print("FERTIG")
    print("=" * 50)
    print(f"Ordner gesamt:       {len(updated_folders)} ({len(updated_folders) - len(existing_folders)} neu)")
    print(f"Projektanweisungen:  {len(project_instructions)} Ordner konfiguriert")
    print(f"TM-native Chats:     {len(tm_native)}")
    print(f"ChatGPT-Chats:       {len(chatgpt_chats)}")
    print(f"Chats gesamt:        {len(all_chats)}")
    print(f"Bilder:              {len(image_map)} mapped, Modus={img_mode}")
    print()
    print(f"Import-Datei (ZIP):  {out_dir / 'typingmind_import_FLAT.zip'}")
    print()
    print("Import in TypingMind:")
    print("  Settings -> App data and storage -> Import -> ZIP-Datei auswaehlen")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(description="TypingMind Export Builder")
    p.add_argument("--tm-export",   required=True, metavar="DIR",
                   help="Verzeichnis des bestehenden TypingMind-Exports")
    p.add_argument("--canonical",   required=True, metavar="FILE",
                   help="canonical_workspace.json")
    p.add_argument("--chatgpt-raw", required=True, metavar="FILE",
                   help="conversations.json aus ChatGPT-Export")
    p.add_argument("--export-dir",  required=False, metavar="DIR",
                   help="ChatGPT-Export-Ordner (fuer Bild-Dateien)")
    p.add_argument("--out",         required=True, metavar="DIR",
                   help="Ausgabe-Verzeichnis")
    p.add_argument("--config",      required=False, metavar="FILE",
                   help="config.json (Projektanweisungen, Output-Einstellungen)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    build_export(
        tm_export_dir   = Path(args.tm_export),
        canonical_path  = Path(args.canonical),
        chatgpt_raw_path= Path(args.chatgpt_raw),
        export_dir      = Path(args.export_dir) if args.export_dir else None,
        out_dir         = Path(args.out),
        config_path     = Path(args.config) if args.config else None,
    )


if __name__ == "__main__":
    main()
