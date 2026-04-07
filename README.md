# ChatGPT 2 TypingMind

**Migrate all your ChatGPT chats, projects & images to TypingMind** — with a simple Windows app.

No Python, no Terminal, no technical knowledge needed. Just download, run, and import.

---

## Why this tool?

TypingMind has a built-in "Import from OpenAI" feature, but it's limited:

| Feature | TypingMind Built-in Import | ChatGPT2TypingMind |
|---------|---------------------------|-------------------|
| Basic chat import | yes | yes |
| Nested folder hierarchy | no | **yes** |
| Image support | no | **yes** (via Cloudflare R2) |
| Automatic project detection | no | **yes** |
| Custom GPT recognition | no | **yes** |
| Incremental sync (delta) | no | **yes** |
| Folder renaming | no | **yes** |
| Bilingual UI (EN/DE) | - | **yes** |

---

## Free vs Pro

| Feature | Free | Pro |
|---------|:----:|:---:|
| Chat migration | up to 100 | unlimited |
| Folder hierarchy (nested) | yes | yes |
| Automatic project & GPT detection | yes | yes |
| Custom folder names | yes | yes |
| Image hosting (Cloudflare R2) | - | yes |
| Delta-Sync (only new chats) | - | yes |
| Windows GUI (.exe) | yes | yes |
| Language toggle (EN/DE) | yes | yes |
| Price | **free** | **one-time purchase** |

**[Download Free Version](https://github.com/K2daOz/chatgpt2typingmind/releases/latest)** | **[Buy Pro Version](https://workbenchdigital.gumroad.com/l/oemkn)**

---

## Quick Start

### Step 1: Export your ChatGPT data

1. Open [ChatGPT](https://chat.openai.com)
2. Click your profile icon (bottom left) -> **Settings**
3. **Data Controls** -> **Export my data** -> **Confirm export**
4. Wait for the email from OpenAI (usually a few minutes to hours)
5. Download the ZIP file and **unzip it** into a folder

### Step 2: Download & run the tool

**Option A: Download the .exe (recommended)**

1. Go to [Releases](https://github.com/K2daOz/chatgpt2typingmind/releases/latest)
2. Download `ChatGPT2TypingMind.exe`
3. Run it — no installation needed, fully portable

> **Note:** Windows SmartScreen may show a warning because the .exe is not code-signed. Click "More info" -> "Run anyway". The source code is fully open and auditable.

**Option B: Run from source (Python 3.10+)**

```bash
git clone https://github.com/K2daOz/chatgpt2typingmind.git
cd chatgpt2typingmind
pip install -r requirements.txt
python gui.py
```

### Step 3: Use the wizard

The app guides you through 4 steps:

**1. Select Export** — Browse to your unzipped ChatGPT export folder and click "Analyze Export". The tool auto-detects all your projects and Custom GPTs.

**2. Configure Folders** — Review the detected folder names. You can optionally rename them or set parent folders to create a nested hierarchy (e.g. put "Project Alpha" and "Project Beta" under a "Clients" parent folder).

**3. Image Hosting (Pro)** — Optionally upload all images to Cloudflare R2 so they are visible in TypingMind. Without this, images appear as placeholder text. See [Image Hosting Setup](#image-hosting-pro-only) below.

**4. Start Migration** — Click "Start Migration" and wait. The tool creates a ZIP file ready for import.

### Step 4: Import into TypingMind

1. Open [typingmind.com](https://typingmind.com)
2. If Cloud Sync is active: go to **Settings -> Cloud-Sync & Backup -> Account** and **log out** first
3. Go to **Settings -> App Data & Storage -> Import**
4. **Important:** Change the file filter (bottom right of the file picker) to **"All files (\*.\*)"**
5. Select the generated ZIP file
6. Verify that your chats and folders are visible

### Step 5: Re-enable Cloud Sync

1. Go to **Settings -> Cloud-Sync & Backup**
2. Log back into your Cloud account

> **Important:** If Cloud Sync deletes your imported chats (shows 0 Bytes):
> 1. Go to **Cloud-Sync & Backup -> Recently Deleted -> Chats**
> 2. Select all and click **"Restore"**
> 3. Do the same for **Folders**, **Agents**, and **Plugins**
> 4. After restoring, Cloud Sync will work correctly

---

## Image Hosting (Pro only)

Pro users can upload images to Cloudflare R2 (free up to 10 GB) so they are visible directly in TypingMind chats. The tool handles the upload automatically — including incremental uploads (only new images are uploaded on subsequent runs).

### Cloudflare R2 Setup

1. **Create a free Cloudflare account** at [dash.cloudflare.com](https://dash.cloudflare.com)

2. **Create an R2 bucket**
   - Dashboard -> **R2 Object Storage** (left sidebar)
   - Click **"Create bucket"**
   - Name: e.g. `my-typingmind-images`
   - Region: Automatic
   - Click **"Create bucket"**

3. **Enable Public Access**
   - Open your bucket -> **Settings**
   - Under **"Public Development URL"**: Click **"Allow Access"**
   - Note the URL (e.g. `https://pub-XXXX.r2.dev`)

4. **Configure CORS Policy**
   - In the same Settings area: **CORS Policy** -> **"+ Add"**
   - Paste:
   ```json
   [{"AllowedOrigins": ["*"], "AllowedMethods": ["GET"]}]
   ```

5. **Create an API Token**
   - Go to **R2** -> **"Manage R2 API Tokens"** (top right)
   - Click **"Create API Token"**
   - Permissions: **Object Read & Write**
   - Bucket: Select your bucket
   - Note the **Access Key ID** and **Secret Access Key**
   - Your **Account ID** is in the URL: `dash.cloudflare.com/ACCOUNT_ID/...`

6. **Enter credentials in the app** (Step 3 of the wizard)
   - Account ID
   - Access Key ID
   - Secret Access Key
   - Bucket Name
   - Public URL

> **Tip:** The R2 Setup Guide is also available inside the app — click the "R2 Setup Guide" button on the Image Hosting page.

---

## Activate Pro License

1. [Purchase on Gumroad](https://workbenchdigital.gumroad.com/l/oemkn) (one-time payment, no subscription)
2. You'll receive a license key via email (format: `XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX`)
3. In the app: click **"License"** (bottom left) -> paste your key -> click **"Activate"**
4. The key is saved locally — you only need to enter it once
5. Works offline after first activation

---

## Project Instructions

ChatGPT does **not** export your project "Instructions" (the custom instructions you set per project). This is a limitation of the ChatGPT export format.

**Workaround:** Copy them manually:
1. In ChatGPT: Open each project -> **Project Settings** -> copy the "Instructions" text
2. In TypingMind: Open the corresponding folder -> **Project context & instructions** -> paste

---

## CLI Usage (advanced)

For power users who prefer the command line:

```bash
# Step 1: Discover projects and generate config
python migrate.py --chatgpt-export ./my-export --discover

# Step 2: Review and edit config.json (folder names, parents, instructions)

# Step 3: Run full migration
python migrate.py --chatgpt-export ./my-export --mode full

# Step 4: Delta sync — only new chats (Pro only)
python migrate.py --chatgpt-export ./my-new-export --mode delta --license-key YOUR-KEY

# Upload images to R2 (Pro only)
python upload_to_r2.py \
  --account-id YOUR_ACCOUNT_ID \
  --access-key-id YOUR_KEY \
  --secret-access-key YOUR_SECRET \
  --bucket my-typingmind-images \
  --images-dir ./my-export
```

### CLI Options

```
--chatgpt-export DIR   ChatGPT export folder (required)
--discover             Detect projects and generate config.json
--mode full|delta      Full migration or only new chats (default: full)
--license-key KEY      Activate Pro license
--config FILE          Custom config file path
--skip-normalize       Skip normalization (if canonical already exists)
--tm-export DIR        Existing TypingMind export (auto-detected)
```

---

## Architecture

```
ChatGPT Export              Cloudflare R2           TypingMind
--------------              -------------           ----------
conversations-*.json
  |
  +-> normalize ---------> canonical.json
  |                              |
  +-> discover ----------> config.json
  |                         (user edits)
  |                              |
  +-> migrate -----------> import.zip ----------> Import
  |
images (file-*.jpg) -----> upload_to_r2 -----> R2 Bucket
                                                  |
                              image URLs <--------+
```

### File Structure

```
chatgpt2typingmind/
|-- gui.py                      # Windows GUI (PyQt6 wizard)
|-- migrate.py                  # CLI entry point
|-- discover.py                 # Project auto-detection
|-- build_typingmind_export.py  # TypingMind format converter
|-- normalize_chatgpt_export.py # ChatGPT export parser
|-- upload_to_r2.py             # Cloudflare R2 image uploader
|-- license.py                  # Gumroad license validation
|-- translations.py             # Bilingual string system (EN/DE)
|-- manifest.py                 # Delta-sync state tracker
|-- config.template.json        # Empty config template
|-- requirements.txt            # Python dependencies
```

---

## Known Limitations

- **Project instructions not exported** — ChatGPT does not include project "Instructions" in the data export. Copy them manually (see [Project Instructions](#project-instructions)).
- **Cloud Sync may delete imports** — TypingMind Cloud Sync sometimes overwrites imported data with empty cloud state. Use the "Recently Deleted -> Restore" workaround (see [Step 5](#step-5-re-enable-cloud-sync)).
- **Images in user messages** — TypingMind renders markdown images (`![](url)`) only in assistant messages. User-uploaded images appear as text links.
- **Chats over 10 MB** — TypingMind Cloud Sync skips chats larger than 10 MB.
- **Windows only** — The .exe is built for Windows. Mac/Linux users can run from source with Python.

---

## FAQ

**Q: Is my data sent to any server?**
A: No. All processing happens locally on your computer. The only network calls are: (1) license key verification via Gumroad API, and (2) image upload to YOUR Cloudflare R2 bucket (Pro only, optional).

**Q: Can I migrate to TypingMind Self-Hosted?**
A: Yes. The generated ZIP file works with both typingmind.com and self-hosted instances.

**Q: What ChatGPT export formats are supported?**
A: Both the old format (`conversations.json`) and the new chunked format (`conversations-000.json` through `conversations-NNN.json`).

**Q: What happens if I export again later?**
A: Pro users can use Delta-Sync (`--mode delta`) to only import new chats. Free users need to do a full migration each time.

**Q: Can I get a refund?**
A: Yes. Contact support within 30 days of purchase.

---

## Contributing

Issues and pull requests are welcome. Please open an issue first to discuss larger changes.

## License

MIT License — see [LICENSE](LICENSE)

---

Made by [workbench digital](https://workbenchdigital.de)
