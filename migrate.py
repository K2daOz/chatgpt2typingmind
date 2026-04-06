#!/usr/bin/env python3
"""
migrate.py — ChatGPT -> TypingMind Migration CLI

Einzelner Einstiegspunkt fuer die gesamte Pipeline:
  1. ChatGPT-Export normalisieren -> canonical_workspace.json
  2. TypingMind-Import erzeugen (mit Bildern, Projektanweisungen, Ordnern)
  3. Manifest aktualisieren (fuer Delta-Sync)

Modi:
  full   - Alles verarbeiten (Standard beim ersten Run)
  delta  - Nur neue Chats seit letztem Run

Verwendung:
    # Erster Run (vollstaendig)
    python migrate.py --chatgpt-export ./chatgpt_export_dir --mode full

    # Folgende Runs (nur neue Chats)
    python migrate.py --chatgpt-export ./chatgpt_export_dir --mode delta

    # Ohne Bilder einzubetten (schneller, kleiner)
    python migrate.py --chatgpt-export ./chatgpt_export_dir --no-embed-images
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

# Eigene Module
from normalize_chatgpt_export import build_canonical, parse_projects, parse_memory, load_json as norm_load_json, find_file
from build_typingmind_export import (
    build_export,
    load_json,
    write_json,
    build_image_map,
    build_folder_structure,
    chatgpt_conv_to_tm,
    is_chatgpt_id,
    write_flat_json,
    write_zip,
    load_config,
    NOW,
)
from discover import generate_config, print_discovery_summary
from license import is_pro as license_is_pro, activate as license_activate, FREE_CHAT_LIMIT
from manifest import (
    load_manifest,
    save_manifest,
    compute_delta,
    update_manifest,
    get_imported_ids,
)


# ---------------------------------------------------------------------------
# Konfiguration und Pfade
# ---------------------------------------------------------------------------

# Standard-Pfade (relativ zum Projektroot)
DEFAULT_CONFIG = "Projektinformationen/config.json"
DEFAULT_MANIFEST = "Projektinformationen/manifest.json"
DEFAULT_CANONICAL_DIR = "migration_workspace/canonical"
DEFAULT_OUTPUT_DIR = "migration_workspace/rehydration"


def resolve_paths(args) -> Dict[str, Path]:
    """Loest alle Pfade relativ zum Projektroot auf."""
    project_root = Path(args.project_root) if args.project_root else Path.cwd()

    paths = {
        "project_root": project_root,
        "chatgpt_export": Path(args.chatgpt_export),
        "config": Path(args.config) if args.config else project_root / DEFAULT_CONFIG,
        "manifest": Path(args.manifest) if args.manifest else project_root / DEFAULT_MANIFEST,
        "canonical_dir": project_root / DEFAULT_CANONICAL_DIR,
        "output_dir": Path(args.output) if args.output else project_root / DEFAULT_OUTPUT_DIR / f"typingmind_import_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    }

    # TM-Export: entweder explizit angegeben oder automatisch suchen
    if args.tm_export:
        paths["tm_export"] = Path(args.tm_export)
    else:
        # Suche nach *_typingmind_export-Ordner im Projekt
        candidates = sorted(project_root.glob("*_typingmind_export"), reverse=True)
        if candidates:
            paths["tm_export"] = candidates[0]
            print(f"  TM-Export automatisch gefunden: {candidates[0].name}")
        else:
            print("FEHLER: Kein TypingMind-Export gefunden. Bitte --tm-export angeben.")
            sys.exit(1)

    return paths


# ---------------------------------------------------------------------------
# Phase 1: Normalisierung
# ---------------------------------------------------------------------------

def run_normalize(chatgpt_dir: Path, canonical_dir: Path) -> Path:
    """Fuehrt normalize_chatgpt_export durch -> canonical_workspace.json"""
    print("\n" + "=" * 50)
    print("PHASE 1: ChatGPT-Export normalisieren")
    print("=" * 50)

    conv_path = find_file(chatgpt_dir, ["conversations.json", "chat.json"])
    conv_chunk_paths = sorted(chatgpt_dir.glob("conversations-[0-9]*.json"))

    if not conv_path and not conv_chunk_paths:
        print(f"FEHLER: conversations.json nicht in {chatgpt_dir} gefunden!")
        sys.exit(1)

    conversations_raw: list = []
    if conv_chunk_paths:
        for cp in conv_chunk_paths:
            chunk = norm_load_json(cp)
            if isinstance(chunk, list):
                conversations_raw.extend(chunk)
        print(f"  Konversationen geladen: {len(conversations_raw)} (aus {len(conv_chunk_paths)} Dateien)")
    else:
        conversations_raw = norm_load_json(conv_path)
        if not isinstance(conversations_raw, list):
            print(f"FEHLER: {conv_path.name} ist kein JSON-Array.")
            sys.exit(1)
        print(f"  Konversationen geladen: {len(conversations_raw)}")

    # Optionale Dateien
    projects_path = find_file(chatgpt_dir, ["projects.json"])
    projects_map = {}
    if projects_path:
        projects_map = parse_projects(norm_load_json(projects_path))
        print(f"  Projekte geladen: {len(projects_map)}")

    memory_path = find_file(chatgpt_dir, ["memory.json", "memories.json"])
    memory_entries = []
    if memory_path:
        memory_entries = parse_memory(norm_load_json(memory_path))
        print(f"  Memory-Eintraege: {len(memory_entries)}")

    canonical = build_canonical(conversations_raw, projects_map, memory_entries, source_label="chatgpt")

    canonical_out = canonical_dir / "canonical_workspace.json"
    canonical_dir.mkdir(parents=True, exist_ok=True)
    write_json(canonical_out, canonical)

    print(f"  Canonical gespeichert: {canonical_out}")
    print(f"  {len(canonical['conversations'])} Konversationen, {len(canonical['projects'])} Projekte")

    return canonical_out


# ---------------------------------------------------------------------------
# Phase 2: TypingMind-Import erzeugen
# ---------------------------------------------------------------------------

def run_build(
    paths: Dict[str, Path],
    canonical_path: Path,
    mode: str,
) -> None:
    """Fuehrt build_typingmind_export durch -> ZIP-Import"""
    print("\n" + "=" * 50)
    print(f"PHASE 2: TypingMind-Import erzeugen (Modus: {mode})")
    print("=" * 50)

    cfg = load_config(paths["config"])

    # Manifest laden
    manifest = load_manifest(paths["manifest"])
    already_imported = get_imported_ids(manifest)
    print(f"  Manifest: {len(already_imported)} Chat-IDs bereits importiert")

    image_base_url = cfg.get("image_base_url", "")

    project_instructions = {
        k: v for k, v in cfg.get("project_instructions", {}).items()
        if k != "_comment" and v
    }

    # Daten laden
    print("\n  Lade Daten...")
    images_dir = paths["project_root"] / "migration_workspace" / "images"
    image_mapping_path = images_dir / "_image_mapping.json" if images_dir.exists() else None
    image_map = build_image_map(paths["chatgpt_export"], image_mapping_path)

    tm_data = load_json(paths["tm_export"] / "data.json")
    existing_folders = tm_data["data"]["folders"]

    existing_chats = []
    for chunk_ref in tm_data["data"]["chats"]["chunks"]:
        chunk_path = paths["tm_export"] / chunk_ref
        existing_chats.extend(load_json(chunk_path))

    tm_native = [c for c in existing_chats
                 if not is_chatgpt_id(c.get("id") or c.get("chatID") or "")]
    print(f"  TM-nativ: {len(tm_native)}")

    canonical = load_json(canonical_path)
    # Rohe Konversationen laden (ein- oder mehrteilig)
    conv_single = paths["chatgpt_export"] / "conversations.json"
    conv_chunks = sorted(paths["chatgpt_export"].glob("conversations-[0-9]*.json"))
    raw_convs: list = []
    if conv_chunks:
        for cp in conv_chunks:
            raw_convs.extend(load_json(cp))
    elif conv_single.is_file():
        raw_convs = load_json(conv_single)
    raw_by_id = {(c.get("id") or c.get("conversation_id") or ""): c for c in raw_convs}

    # Konversation-ID -> Projekt-ID
    conv_to_pid = {c["conversation_id"]: c.get("project_id") for c in canonical["conversations"]}
    all_canonical_ids = [c["conversation_id"] for c in canonical["conversations"]]

    # Delta berechnen
    if mode == "delta" and already_imported:
        new_ids = compute_delta(all_canonical_ids, manifest)
        print(f"  Delta: {len(new_ids)} neue Chats (von {len(all_canonical_ids)} gesamt)")
        if not new_ids:
            print("\n  Keine neuen Chats gefunden. Nichts zu tun.")
            return
        process_ids = set(new_ids)
    else:
        process_ids = set(all_canonical_ids)
        print(f"  Full-Modus: alle {len(process_ids)} Chats verarbeiten")

    # Ordnerstruktur aufbauen (config-driven)
    folder_map = cfg.get("folder_map", {})
    if not folder_map:
        print("\n  WARNUNG: Keine folder_map in config.json!")
        print("  Fuehre zuerst --discover aus um Projekte zu erkennen.")

    print("\n  Ordner aufbauen...")
    updated_folders, title_to_id = build_folder_structure(
        existing_folders, folder_map, project_instructions
    )

    pid_to_folder_id = {}
    for pid, entry in folder_map.items():
        folder_title = entry.get("folder") or f"Projekt {pid[:12]}"
        pid_to_folder_id[pid] = title_to_id.get(folder_title)

    # Chats konvertieren
    img_mode = f"URL: {image_base_url}" if image_base_url else "Platzhalter"
    print(f"\n  Konvertiere Chats (Bilder: {img_mode})...")
    chatgpt_chats = []
    total = len(process_ids)
    count = 0
    export_dir = paths["chatgpt_export"]

    for conv in canonical["conversations"]:
        cid = conv["conversation_id"]
        if cid not in process_ids:
            continue

        raw = raw_by_id.get(cid)
        if not raw:
            continue

        count += 1
        if count % 100 == 0:
            print(f"    ... {count}/{total}")

        pid = conv.get("project_id")
        folder_id = pid_to_folder_id.get(pid) if pid else None
        tm_chat = chatgpt_conv_to_tm(raw, folder_id, image_map, image_base_url, export_dir)
        chatgpt_chats.append(tm_chat)

    print(f"  Konvertiert: {len(chatgpt_chats)} Chats")

    # Finale Chat-Liste
    all_chats = tm_native + chatgpt_chats
    print(f"  Gesamt im Export: {len(all_chats)}")

    # Output
    out_dir = paths["output_dir"]
    out_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Output: {out_dir}")

    flat_path = write_flat_json(out_dir, all_chats, updated_folders)
    zip_path = write_zip(out_dir, flat_path)

    # Manifest aktualisieren
    imported_ids = [c.get("id") or c.get("chatID") for c in chatgpt_chats]
    tm_native_ids_list = [c.get("id") or c.get("chatID") for c in tm_native]

    manifest = update_manifest(
        manifest,
        imported_ids=imported_ids,
        tm_native_ids=tm_native_ids_list,
        mode=mode,
        chatgpt_count=len(chatgpt_chats),
    )
    save_manifest(paths["manifest"], manifest)

    # Zusammenfassung
    print("\n" + "=" * 50)
    print("FERTIG")
    print("=" * 50)
    print(f"  Modus:           {mode}")
    print(f"  Ordner:          {len(updated_folders)}")
    print(f"  TM-native Chats: {len(tm_native)}")
    print(f"  ChatGPT-Chats:   {len(chatgpt_chats)}")
    print(f"  Gesamt:          {len(all_chats)}")
    print(f"  Bilder:          {len(image_map)} mapped, {img_mode}")
    print(f"  ZIP:             {zip_path}")
    print(f"  Manifest:        {paths['manifest']}")
    print()
    print("  Naechster Schritt:")
    print(f"  TypingMind -> Settings -> Import -> {zip_path.name}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="ChatGPT -> TypingMind Migration CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Beispiele:
  # Erster Run
  python migrate.py --chatgpt-export ./chatgptexport2023-02-16

  # Delta-Sync (nur neue Chats)
  python migrate.py --chatgpt-export ./chatgpt_export_2026-07 --mode delta

  # Ohne Bilder (schnell)
  python migrate.py --chatgpt-export ./chatgpt_export --no-embed-images
        """,
    )
    p.add_argument("--chatgpt-export", required=True, metavar="DIR",
                   help="ChatGPT-Export-Ordner (mit conversations.json)")
    p.add_argument("--tm-export", metavar="DIR",
                   help="TypingMind-Export-Ordner (wird auto-erkannt wenn nicht angegeben)")
    p.add_argument("--mode", choices=["full", "delta"], default="full",
                   help="full = alles, delta = nur neue Chats (default: full)")
    p.add_argument("--config", metavar="FILE",
                   help=f"Config-Datei (default: {DEFAULT_CONFIG})")
    p.add_argument("--manifest", metavar="FILE",
                   help=f"Manifest-Datei (default: {DEFAULT_MANIFEST})")
    p.add_argument("--output", metavar="DIR",
                   help="Ausgabe-Ordner (default: auto mit Timestamp)")
    p.add_argument("--project-root", metavar="DIR",
                   help="Projektstammverzeichnis (default: CWD)")
    p.add_argument("--skip-normalize", action="store_true",
                   help="Phase 1 ueberspringen (canonical_workspace.json existiert bereits)")
    p.add_argument("--discover", action="store_true",
                   help="Projekte erkennen und config.json generieren (ohne Migration)")
    p.add_argument("--license-key", metavar="KEY",
                   help="Pro-Lizenzschluessel aktivieren (unbegrenzte Chats, Delta-Sync)")
    return p.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    start = time.time()

    # Lizenz-Aktivierung (optional)
    if args.license_key:
        success, msg = license_activate(args.license_key)
        if success:
            print(f"Pro-Lizenz aktiviert! E-Mail: {msg}")
        else:
            print(f"Lizenz-Fehler: {msg}")

    pro = license_is_pro()
    edition = "PRO" if pro else f"FREE (max {FREE_CHAT_LIMIT} Chats)"

    print("=" * 50)
    print(f"ChatGPT -> TypingMind Migration [{edition}]")
    print(f"Modus: {args.mode}")
    print("=" * 50)

    # Delta-Sync nur fuer Pro
    if args.mode == "delta" and not pro:
        print("\nFEHLER: Delta-Sync ist ein Pro-Feature.")
        print("Aktiviere mit: --license-key DEIN_KEY")
        sys.exit(1)

    paths = resolve_paths(args)

    # Phase 1: Normalisierung
    canonical_path = paths["canonical_dir"] / "canonical_workspace.json"
    if not args.skip_normalize:
        canonical_path = run_normalize(paths["chatgpt_export"], paths["canonical_dir"])
    else:
        if not canonical_path.exists():
            print(f"FEHLER: --skip-normalize gesetzt, aber {canonical_path} existiert nicht!")
            sys.exit(1)
        print(f"\nPhase 1 uebersprungen. Canonical: {canonical_path}")

    if args.discover:
        # Discovery-Modus: Projekte erkennen, config.json generieren
        run_discover(paths, canonical_path)
    else:
        # Phase 2: Build
        run_build(paths, canonical_path, args.mode)

    elapsed = time.time() - start
    print(f"\nLaufzeit: {elapsed:.1f}s")


def run_discover(paths: Dict, canonical_path: Path) -> None:
    """Erkennt Projekte und generiert/aktualisiert config.json."""
    print("\n" + "=" * 50)
    print("DISCOVER: Projekte erkennen")
    print("=" * 50)

    canonical = load_json(canonical_path)
    print(f"  {len(canonical['conversations'])} Konversationen geladen")

    # Bestehende config laden (falls vorhanden)
    existing_config = None
    config_path = paths["config"]
    if config_path.exists():
        try:
            existing_config = load_json(config_path)
            print(f"  Bestehende config.json geladen: {config_path}")
        except Exception:
            pass

    # projects.json aus Export laden (falls vorhanden)
    projects_json_map = None
    projects_path = find_file(paths["chatgpt_export"], ["projects.json"])
    if projects_path:
        from normalize_chatgpt_export import parse_projects
        projects_json_map = parse_projects(norm_load_json(projects_path))
        print(f"  projects.json gefunden: {len(projects_json_map)} Projekte")

    # Config generieren
    config = generate_config(canonical, existing_config, projects_json_map)

    # Speichern
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"\n  config.json gespeichert: {config_path}")
    print()
    print_discovery_summary(config)
    print()
    print("  Naechste Schritte:")
    print("  1. config.json pruefen und Ordnernamen anpassen")
    print("     - 'folder': Ordnername in TypingMind")
    print("     - 'parent': Uebergeordneter Ordner (null = Root)")
    print("  2. Optional: 'project_instructions' befuellen")
    print("  3. Optional: 'image_base_url' setzen (Cloudflare R2 URL)")
    print(f"  4. Migration starten:")
    print(f"     python migrate.py --chatgpt-export {paths['chatgpt_export']}")


if __name__ == "__main__":
    main()
