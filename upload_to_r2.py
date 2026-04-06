"""
upload_to_r2.py — Lädt alle ChatGPT-Export-Bilder in einen Cloudflare R2 Bucket.

Voraussetzungen:
  pip install boto3
  Cloudflare R2-Bucket muss existieren und Public Access aktiviert sein.

Nutzung:
  python upload_to_r2.py --account-id DEIN_ACCOUNT_ID \
                          --access-key-id DEIN_ACCESS_KEY_ID \
                          --secret-access-key DEIN_SECRET_KEY \
                          --bucket typingmind-images

  Optional:
    --images-dir   Pfad zum Bilder-Ordner oder ChatGPT-Export-Ordner
                   (Standard: ../migration_workspace/images)
                   Wird rekursiv durchsucht (inkl. user-*, dalle-generations)
    --prefix       Unterpfad im Bucket (Standard: leer = Root)
    --dry-run      Zeigt nur, was hochgeladen würde, ohne zu uploaden
"""

import argparse
import os
import sys
import boto3
from botocore.exceptions import ClientError
from pathlib import Path

SKIP_FILES = {"_image_mapping.json"}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".heic", ".dng"}

CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".heic": "image/heic",
    ".dng": "image/x-adobe-dng",
}


def get_content_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    return CONTENT_TYPES.get(ext, "application/octet-stream")


def upload_images(
    account_id: str,
    access_key_id: str,
    secret_access_key: str,
    bucket: str,
    images_dir: Path,
    prefix: str = "",
    dry_run: bool = False,
):
    endpoint = f"https://{account_id}.r2.cloudflarestorage.com"

    s3 = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key_id,
        aws_secret_access_key=secret_access_key,
        region_name="auto",
    )

    # Rekursiv alle Bilddateien sammeln (inkl. user-*, dalle-generations)
    images = sorted([
        f for f in images_dir.rglob("*")
        if f.is_file()
        and f.name not in SKIP_FILES
        and f.suffix.lower() in IMAGE_EXTENSIONS
        and not f.name.endswith(".json")
    ])

    total = len(images)
    total_size = sum(f.stat().st_size for f in images)
    print(f"[DIR] Bilder-Ordner: {images_dir}")
    print(f"[BUCKET] Bucket: {bucket}")
    print(f"[INFO] {total} Dateien, {total_size / 1024 / 1024:.1f} MB gesamt")

    # Duplikat-Erkennung: bei gleichen Dateinamen aus versch. Ordnern nur den ersten nehmen
    seen_names: dict = {}
    deduped = []
    for img in images:
        if img.name not in seen_names:
            seen_names[img.name] = img
            deduped.append(img)
    if len(images) != len(deduped):
        print(f"  [INFO]  {len(images) - len(deduped)} Duplikate (gleicher Dateiname) übersprungen")
        images = deduped
        total = len(images)
        total_size = sum(f.stat().st_size for f in images)

    if dry_run:
        print(f"\n[WARN]  DRY RUN — kein Upload\n")
        for img in images[:10]:
            key = f"{prefix}{img.name}" if prefix else img.name
            print(f"  -> {key}  ({img.stat().st_size / 1024:.0f} KB)")
        if total > 10:
            print(f"  ... und {total - 10} weitere")
        return

    print("\n[UP]  Starte Upload...\n")
    uploaded = 0
    skipped = 0
    failed = 0

    for i, img in enumerate(images, 1):
        key = f"{prefix}{img.name}" if prefix else img.name
        content_type = get_content_type(img.name)

        try:
            # Prüfen ob bereits vorhanden (Skip wenn gleiche Größe)
            try:
                head = s3.head_object(Bucket=bucket, Key=key)
                if head["ContentLength"] == img.stat().st_size:
                    skipped += 1
                    if i % 50 == 0 or i == total:
                        print(f"  [{i}/{total}] [SKIP]  {img.name} (bereits vorhanden)")
                    continue
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise

            with open(img, "rb") as f:
                s3.put_object(
                    Bucket=bucket,
                    Key=key,
                    Body=f,
                    ContentType=content_type,
                )
            uploaded += 1

            if i % 10 == 0 or i == total:
                print(f"  [{i}/{total}] [OK] {img.name}")

        except Exception as e:
            failed += 1
            print(f"  [{i}/{total}] [ERR] {img.name}: {e}", file=sys.stderr)

    print(f"\n[OK] Fertig: {uploaded} hochgeladen, {skipped} übersprungen, {failed} Fehler")
    if failed == 0:
        print(f"\n[URL] Deine Bilder sind erreichbar unter:")
        example = images[0].name if images else "bild.jpg"
        key_example = f"{prefix}{example}" if prefix else example
        print(f"   https://pub-XXXX.r2.dev/{key_example}")
        print(f"\n[TIP] Ersetze 'pub-XXXX' mit deiner tatsächlichen R2 Public-URL aus dem Dashboard")


def main():
    script_dir = Path(__file__).parent
    default_images = script_dir.parent / "migration_workspace" / "images"

    parser = argparse.ArgumentParser(description="ChatGPT-Bilder in Cloudflare R2 hochladen")
    parser.add_argument("--account-id", required=True, help="Cloudflare Account ID (aus R2-Dashboard)")
    parser.add_argument("--access-key-id", required=True, help="R2 Access Key ID")
    parser.add_argument("--secret-access-key", required=True, help="R2 Secret Access Key")
    parser.add_argument("--bucket", required=True, help="R2 Bucket-Name")
    parser.add_argument("--images-dir", type=Path, default=default_images, help=f"Bilder-Ordner (Standard: {default_images})")
    parser.add_argument("--prefix", default="", help="Optionaler Pfad-Prefix im Bucket (z.B. 'images/')")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nicht hochladen")
    args = parser.parse_args()

    if not args.images_dir.is_dir():
        print(f"[ERR] Bilder-Ordner nicht gefunden: {args.images_dir}", file=sys.stderr)
        sys.exit(1)

    upload_images(
        account_id=args.account_id,
        access_key_id=args.access_key_id,
        secret_access_key=args.secret_access_key,
        bucket=args.bucket,
        images_dir=args.images_dir,
        prefix=args.prefix,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
