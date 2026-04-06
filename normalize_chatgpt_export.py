#!/usr/bin/env python3
"""
Normalizer: ChatGPT-Export → Kanonisches Zwischenmodell

Liest conversations.json (sowie optional projects.json und memory.json) aus einem
entpackten ChatGPT-Export und erzeugt canonical_workspace.json gemäß
canonical_migration_schema.json.

Verwendung:
    python normalize_chatgpt_export.py \\
        --export-dir ./migration_workspace/source_export/my-export \\
        --out ./migration_workspace/canonical/canonical_workspace.json

Explizite Annahmen (Stand: OpenAI-Export-Format 2024/2025):
  - conversations.json: JSON-Array von Konversations-Objekten mit mapping-Baum
  - projects.json: JSON-Array von Projekten (Feld "id" oder "project_id")
    oder Dict { project_id: {...} } — falls nicht vorhanden, wird project_id
    aus der Konversation als Titel-Fallback genutzt.
  - memory.json: JSON-Array von Memory-Einträgen (Strings oder Objekte mit "text")
  - message.content ist entweder ein Dict mit content_type + parts
    oder in seltenen Fällen ein reiner String (Legacy-Format).
  - Projektzugehörigkeit einer Konversation steckt in "project_id"
    (neuere Exporte) oder "conversation_template_id" (ältere Exporte).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Zeithelfer
# ---------------------------------------------------------------------------

def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ts_to_iso(ts: Optional[float]) -> Optional[str]:
    """Unix-Timestamp (float/int) → ISO-8601 UTC-String. Gibt None zurück bei Fehler."""
    if ts is None:
        return None
    try:
        return (
            datetime.fromtimestamp(float(ts), tz=timezone.utc)
            .replace(microsecond=0)
            .isoformat()
        )
    except (ValueError, OSError, OverflowError):
        return None


# ---------------------------------------------------------------------------
# Message-Content-Extraktion
# ---------------------------------------------------------------------------

def extract_message_text(content: Any) -> str:
    """
    Konvertiert das ChatGPT message.content-Objekt in lesbaren Text.

    Behandelte content_types:
      text              ->parts[] zusammenführen
      code              ->Fenced Code Block
      tether_quote      ->Link + Text (Web-Suche-Zitat)
      multimodal_text   ->Text-Parts + Platzhalter für Medien
      system_error      ->[System-Fehler: ...]
      <unbekannt>       ->JSON-Fallback
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, dict):
        return str(content)

    ct = content.get("content_type", "")

    if ct == "text":
        parts = content.get("parts") or []
        return "\n".join(
            (p if isinstance(p, str) else _serialize(p))
            for p in parts
            if p is not None and p != ""
        )

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
                chunks.append(part)
            elif isinstance(part, dict):
                sub_ct = part.get("content_type") or ""
                if sub_ct == "image_asset_pointer":
                    chunks.append(f"[Bild: {part.get('asset_pointer', '')}]")
                elif sub_ct in {"audio_asset_pointer", "video_asset_pointer"}:
                    chunks.append(
                        f"[{sub_ct.replace('_', ' ')}: {part.get('asset_pointer', '')}]"
                    )
                else:
                    chunks.append(_serialize(part))
        return "\n".join(chunks)

    if ct == "system_error":
        return f"[System-Fehler: {content.get('text', '')}]"

    if ct == "tether_browsing_display":
        # Nur in Browser-Sessions, nicht für Weiterarbeit relevant
        return f"[Web-Suchergebnis: {content.get('result', '')}]"

    # Fallback
    return _serialize(content)


def _serialize(obj: Any) -> str:
    try:
        return json.dumps(obj, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(obj)


# ---------------------------------------------------------------------------
# Nachrichtenbaum traversieren
# ---------------------------------------------------------------------------

def traverse_conversation(mapping: Dict[str, Any]) -> List[Dict]:
    """
    Rekonstruiert die lineare Nachrichtenfolge aus dem ChatGPT-Mapping-Baum.

    Das Mapping ist ein Dict { node_id: { message, parent, children } }.
    Wir suchen den Wurzelknoten (nicht in irgendeinem children-Set enthalten)
    und folgen dem Hauptpfad (letztes Kind = aktuell sichtbarer Gesprächszweig).

    Zurückgegeben werden nur Nachrichten mit nicht-leerem Inhalt oder
    nicht-trivialem Role (kein leerer system-Platzhalter).
    """
    if not mapping:
        return []

    # Wurzel: Knoten, der nirgendwo als Kind auftaucht
    all_children: set = set()
    for node in mapping.values():
        all_children.update(node.get("children") or [])

    root_id: Optional[str] = None
    for node_id in mapping:
        if node_id not in all_children:
            root_id = node_id
            break
    if root_id is None:
        root_id = next(iter(mapping))  # Fallback

    messages: List[Dict] = []
    visited: set = set()
    queue = [root_id]

    while queue:
        node_id = queue.pop(0)
        if node_id in visited or node_id not in mapping:
            continue
        visited.add(node_id)

        node = mapping[node_id]
        raw_msg = node.get("message")
        children = node.get("children") or []

        if raw_msg:
            role_raw = (raw_msg.get("author") or {}).get("role") or "unknown"
            role = _normalize_role(role_raw)
            content = extract_message_text(raw_msg.get("content"))

            # Leere System-Platzhalter weglassen
            skip = (not content.strip()) and role == "system"
            if not skip:
                messages.append({
                    "message_id": raw_msg.get("id") or node_id,
                    "role": role,
                    "content": content,
                    "created_at": ts_to_iso(raw_msg.get("create_time")),
                    "model": (raw_msg.get("metadata") or {}).get("model_slug"),
                    "attachment_ids": [],
                    "metadata": {
                        "status": raw_msg.get("status"),
                        "end_turn": raw_msg.get("end_turn"),
                        "author_name": (raw_msg.get("author") or {}).get("name"),
                    },
                })

        queue.extend(children)

    return messages


def _normalize_role(role: str) -> str:
    return {"user": "user", "assistant": "assistant", "system": "system",
            "tool": "tool", "developer": "developer"}.get(role, "assistant")


# ---------------------------------------------------------------------------
# Slug-Helfer
# ---------------------------------------------------------------------------

def make_slug(text: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", text.lower())
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:max_len] or "projekt"


# ---------------------------------------------------------------------------
# Export-Datei suchen
# ---------------------------------------------------------------------------

def find_file(root: Path, names: List[str]) -> Optional[Path]:
    """Sucht eine Datei in root und eine Ebene tiefer."""
    for name in names:
        p = root / name
        if p.is_file():
            return p
    for name in names:
        for p in root.glob(f"*/{name}"):
            return p
    return None


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"Warnung: {path} nicht lesbar: {exc}", file=sys.stderr)
        return None


# ---------------------------------------------------------------------------
# Rohdaten parsen
# ---------------------------------------------------------------------------

def parse_projects(data: Any) -> Dict[str, Dict]:
    """
    Gibt { project_id: {title, instructions, description} } zurück.
    Unterstützt Array- und Dict-Format.
    """
    if not data:
        return {}
    items = data if isinstance(data, list) else list(data.values())
    result: Dict[str, Dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id") or item.get("project_id") or "")
        if not pid:
            continue
        result[pid] = {
            "title": item.get("title") or item.get("name") or f"Projekt {pid[:8]}",
            "description": item.get("description") or "",
            "instructions": (
                item.get("instructions")
                or item.get("system_prompt")
                or item.get("custom_instructions")
                or ""
            ),
        }
    return result


def parse_memory(data: Any) -> List[str]:
    """
    Gibt eine Liste von Memory-Einträgen als Strings zurück.
    Unterstützt Array of strings und Array of objects.
    """
    if not data:
        return []
    items = data if isinstance(data, list) else []
    entries = []
    for item in items:
        if isinstance(item, str):
            entries.append(item.strip())
        elif isinstance(item, dict):
            text = (
                item.get("text")
                or item.get("content")
                or item.get("memory")
                or item.get("value")
            )
            if text:
                entries.append(str(text).strip())
    return [e for e in entries if e]


# ---------------------------------------------------------------------------
# Kanonisches Modell aufbauen
# ---------------------------------------------------------------------------

def build_canonical(
    conversations_raw: List[Dict],
    projects_map: Dict[str, Dict],
    memory_entries: List[str],
    source_label: str,
) -> Dict:
    canonical_projects: Dict[str, Dict] = {}
    canonical_conversations: List[Dict] = []
    attachments: Dict[str, Dict] = {}
    att_counter = 0

    for conv in conversations_raw:
        conv_id = str(conv.get("id") or conv.get("conversation_id") or "")
        if not conv_id:
            continue

        # Projektzugehörigkeit: "project_id" (neu) oder "conversation_template_id" (alt)
        project_id: Optional[str] = (
            conv.get("project_id")
            or conv.get("conversation_template_id")
        )
        if project_id:
            project_id = str(project_id)

        title = (conv.get("title") or "Ohne Titel").strip()
        created_at = ts_to_iso(conv.get("create_time"))
        updated_at = ts_to_iso(conv.get("update_time"))

        mapping = conv.get("mapping") or {}
        messages = traverse_conversation(mapping)

        # Attachment-Platzhalter aus Nachrichten extrahieren
        for msg in messages:
            att_ids = []
            for match in re.finditer(r"\[(?:Bild|audio\s+asset\s+pointer|video\s+asset\s+pointer):\s*([^\]]+)\]", msg["content"]):
                att_counter += 1
                att_id = f"att-{att_counter:06d}"
                att_ids.append(att_id)
                attachments[att_id] = {
                    "attachment_id": att_id,
                    "project_id": project_id,
                    "conversation_id": conv_id,
                    "message_id": msg["message_id"],
                    "file_name": Path(match.group(1)).name or match.group(1),
                    "mime_type": None,
                    "size_bytes": 0,
                    "local_path": match.group(1),
                    "source_reference": match.group(1),
                    "storage_mode": "local_only",
                    "target_object_key": None,
                    "hash_sha256": None,
                }
            msg["attachment_ids"] = att_ids

        canonical_conversations.append({
            "conversation_id": conv_id,
            "project_id": project_id,
            "title": title,
            "source_reference": f"conversations.json#{conv_id}",
            "created_at": created_at,
            "updated_at": updated_at,
            "status": "active",
            "messages": messages,
        })

        # Projekt anlegen oder Konversation eintragen
        if project_id:
            if project_id not in canonical_projects:
                info = projects_map.get(project_id, {})
                proj_title = info.get("title") or f"Projekt {project_id[:8]}"
                slug = make_slug(proj_title)
                canonical_projects[project_id] = {
                    "project_id": project_id,
                    "title": proj_title,
                    "source_type": "chatgpt_project",
                    "source_reference": f"projects.json#{project_id}",
                    "project_instruction": info.get("instructions") or "",
                    "memory_note": {
                        "summary": info.get("description") or "",
                        "facts": [],
                        "open_threads": [],
                    },
                    "tags": [slug],
                    "attachment_ids": [],
                    "conversation_ids": [],
                    "knowledge_document_ids": [],
                    "typingmind_rehydration": {
                        "folder_name": proj_title,
                        "agent_name": proj_title,
                        "kb_tag": slug,
                        "system_prompt_template": info.get("instructions") or "",
                    },
                }
            canonical_projects[project_id]["conversation_ids"].append(conv_id)

    # Memory als workspace-globales Knowledge Document
    knowledge_docs: List[Dict] = []
    if memory_entries:
        kb_content = "\n\n".join(f"- {e}" for e in memory_entries)
        knowledge_docs.append({
            "knowledge_document_id": "kb-memory-000001",
            "project_id": None,
            "title": "ChatGPT Memory (exportiert)",
            "document_type": "memory_note",
            "local_path": None,
            "kb_tag": "chatgpt-memory",
            "content_excerpt": kb_content[:4000],
        })

    run_id = f"run-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
    n_proj = len(canonical_projects)
    n_conv = len(canonical_conversations)
    n_att = len(attachments)

    return {
        "workspace": {
            "workspace_id": "chatgpt-to-typingmind-workspace",
            "source_system": "chatgpt",
            "target_system": "typingmind",
            "export_collected_at": utc_now_iso(),
            "migration_strategy": "single_cutover_local",
            "notes": (
                f"Normalisiert aus: {source_label}. "
                f"{n_conv} Konversationen, {n_proj} Projekte, "
                f"{len(memory_entries)} Memory-Einträge, {n_att} Anhang-Platzhalter."
            ),
        },
        "projects": list(canonical_projects.values()),
        "conversations": canonical_conversations,
        "attachments": list(attachments.values()),
        "knowledge_documents": knowledge_docs,
        "migration_runs": [
            {
                "run_id": run_id,
                "started_at": utc_now_iso(),
                "finished_at": utc_now_iso(),
                "mode": "normalize",
                "status": "completed",
                "stats": {
                    "projects_detected": n_proj,
                    "conversations_detected": n_conv,
                    "attachments_detected": n_att,
                    "validation_errors": 0,
                },
            }
        ],
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Normalizer: ChatGPT-Export → kanonisches Zwischenmodell"
    )
    p.add_argument(
        "--export-dir",
        required=True,
        metavar="DIR",
        help="Entpacktes ChatGPT-Export-Verzeichnis (enthält conversations.json)",
    )
    p.add_argument(
        "--out",
        required=True,
        metavar="FILE",
        help="Ausgabedatei (z.B. canonical/canonical_workspace.json)",
    )
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    export_dir = Path(args.export_dir).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve()

    if not export_dir.is_dir():
        print(f"Fehler: Verzeichnis nicht gefunden: {export_dir}", file=sys.stderr)
        return 2

    # conversations.json oder conversations-NNN.json — Pflicht
    conv_path = find_file(export_dir, ["conversations.json", "chat.json"])
    conv_chunk_paths = sorted(export_dir.glob("conversations-[0-9]*.json"))

    if not conv_path and not conv_chunk_paths:
        print(
            "Fehler: conversations.json nicht im Export-Verzeichnis gefunden.\n"
            "Erwarteter Pfad: <export-dir>/conversations.json oder conversations-NNN.json\n"
            "Stelle sicher, dass der ChatGPT-Export vollständig entpackt wurde.",
            file=sys.stderr,
        )
        return 2

    conversations_raw: list = []
    if conv_chunk_paths:
        # Neues Format: conversations-000.json, conversations-001.json, ...
        print(f"Lese Konversationen ({len(conv_chunk_paths)} Dateien):")
        for cp in conv_chunk_paths:
            chunk = load_json(cp)
            if isinstance(chunk, list):
                conversations_raw.extend(chunk)
                print(f"  {cp.name}: {len(chunk)} Konversationen")
            else:
                print(f"  {cp.name}: Übersprungen (kein Array)", file=sys.stderr)
    else:
        print(f"Lese Konversationen: {conv_path}")
        conversations_raw = load_json(conv_path)
        if not isinstance(conversations_raw, list):
            print(
                f"Fehler: {conv_path.name} ist kein JSON-Array. "
                "Prüfe das Export-Format.",
                file=sys.stderr,
            )
            return 2

    print(f"  -> Gesamt: {len(conversations_raw)} Konversationen")

    # projects.json — optional
    projects_path = find_file(export_dir, ["projects.json"])
    projects_map: Dict[str, Dict] = {}
    if projects_path:
        print(f"Lese Projekte: {projects_path}")
        projects_map = parse_projects(load_json(projects_path))
        print(f"  ->{len(projects_map)} Projekte")
    else:
        print("Hinweis: projects.json nicht gefunden — Projekttitel aus project_id abgeleitet.")

    # memory.json — optional
    memory_path = find_file(export_dir, ["memory.json", "memories.json"])
    memory_entries: List[str] = []
    if memory_path:
        print(f"Lese Memory: {memory_path}")
        memory_entries = parse_memory(load_json(memory_path))
        print(f"  ->{len(memory_entries)} Memory-Einträge")
    else:
        print("Hinweis: memory.json nicht gefunden — Memory-Rekonstruktion übersprungen.")

    print("\nNormalisiere...")
    workspace = build_canonical(
        conversations_raw=conversations_raw,
        projects_map=projects_map,
        memory_entries=memory_entries,
        source_label=str(conv_path),
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(workspace, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    stats = workspace["migration_runs"][0]["stats"]
    print(f"\nNormalisierung abgeschlossen:")
    print(f"  Projekte:       {stats['projects_detected']}")
    print(f"  Konversationen: {stats['conversations_detected']}")
    print(f"  Anhänge:        {stats['attachments_detected']}")
    print(f"  Ausgabe:        {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
