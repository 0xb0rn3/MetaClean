# MetaClean

**MetaClean** is a localhost-only metadata inspection and sanitization dashboard for Android devices running [Termux](https://termux.dev/).

It inventories accessible shared storage, reports metadata found in supported files, and creates sanitized copies by default. Originals remain untouched unless the operator explicitly chooses replacement or deletion.

## Installation options (Termux)

Choose any one of the following methods. All three install the same application.

### Option 1 — Git clone (recommended for updates)

Install Git, clone the repository, then run the setup script:

```bash
pkg update -y
pkg install git -y
git clone https://github.com/0xb0rn3/MetaClean.git
cd MetaClean/metaclean
bash setup.sh
```

### Option 2 — Direct curl (no Git required)

This downloads the current `main` branch archive directly from GitHub, extracts only the runnable `metaclean/` project into `~/MetaClean`, and runs setup:

```bash
pkg update -y
pkg install curl tar -y
mkdir -p "$HOME/MetaClean"
cd "$HOME/MetaClean"
curl -fL https://github.com/0xb0rn3/MetaClean/archive/refs/heads/main.tar.gz -o metaclean.tar.gz
tar -xzf metaclean.tar.gz --strip-components=2 MetaClean-main/metaclean
rm metaclean.tar.gz
bash setup.sh
```

### Option 3 — GitHub ZIP download

1. Open [MetaClean on GitHub](https://github.com/0xb0rn3/MetaClean).
2. Select **Code → Download ZIP**, then extract the archive in Termux.
3. Enter the extracted `MetaClean-main/metaclean/` directory.
4. Run:

   ```bash
   bash setup.sh
   ```

### Finish setup

During installation, Android may ask for shared-storage permission. Tap **Allow**. The setup script installs the required Termux packages and Python dependencies, then installs a global `metaclean` launcher.

Start the dashboard from any directory:

```bash
metaclean
```

Open **http://127.0.0.1:5000** in the device browser. The launcher attempts to open it automatically.

Useful commands:

```bash
metaclean          # start the service
metaclean open     # start and open the dashboard
metaclean status   # show service state
metaclean stop     # stop the service
metaclean restart  # restart the service
metaclean logs     # follow the service log
metaclean-setup    # rerun the installer/updater
```

### Updating

For a Git clone installation:

```bash
cd ~/MetaClean
git pull
cd metaclean
bash setup.sh
```

For a direct-curl or ZIP installation, download and extract the newest archive again, then rerun `bash setup.sh` from the updated project directory. The installer refreshes the global copy under `~/.local/share/metaclean`.

## Features

- Recursive inventory of accessible regular files under `~/storage/shared`, including unsupported extensions.
- Metadata inspection using ExifTool and MAT2 when available.
- Image and video thumbnails, file filtering, progress tracking, and batch jobs.
- **RUN ALL** scans storage and sanitizes supported originals into adjacent `.cleaned` copies.
- Optional monitoring detects new or changed supported files and sanitizes them into copies while the MetaClean service is running.
- Optional replacement mode retains a backup before replacing an original.
- Explicitly confirmed deletion; Termux:API notifications when the matching package and Android app are installed.
- Local web server bound to `127.0.0.1`, with a per-process API token and Host-header validation.

## Smarter file discovery

The main **Media & docs** view prioritises recognised user content instead of filling the dashboard with miscellaneous app and system files. Detection covers common photos and camera RAW formats, video containers, audio formats, and office/document formats, including formats that are view-only.

- **Other files** remains available as a separate tab for unrecognised file types.
- Obvious clutter is excluded from inventory: cache/thumbnail/temp folders, `.nomedia`, OS housekeeping files, and incomplete download/temp/lock/log files.
- Detection is broader than cleaning support. Files labelled **view only** can be browsed but cannot be selected for batch cleaning unless a safe cleaner is registered.
- RUN ALL and automatic monitoring still operate only on the existing safe-cleaner registry. Detecting a file does not make it eligible for cleaning.

## Supported formats

| Kind | Extensions |
|---|---|
| Images | JPG, JPEG, PNG, WebP, HEIC |
| Video | MP4, MKV, MOV |
| Audio | MP3, FLAC |
| Documents | PDF, DOCX, XLSX, PPTX |

Actual cleaning coverage depends on installed tools and each format's support. Unsupported file types remain visible in the inventory and are not sent to a generic destructive fallback.

## Storage and privacy notes

- Android's protected `Android/data` and `Android/obb` directories are excluded; ordinary Termux shared-storage permission does not grant access to them.
- The server listens only on loopback. Do not change the bind address to expose it to an untrusted network.
- Automatic cleaning uses copy mode. Review outputs before sharing or deleting originals.
- Metadata removal is format-specific. A clean verification scan is not proof that every possible embedded provenance structure has been removed.
- MetaClean is **not** a secure-erasure tool. Flash storage wear levelling, snapshots, caches, and cloud backups prevent reliable forensic erasure through ordinary file deletion.
- Keep independent backups of important files. Use replace and delete actions carefully.

## Project layout

The runnable project is in `metaclean/`. The self-contained source bundle is also provided as `MetaClean-Termux.tar.xz`.

## License

No license has been added yet. Until a license is chosen, standard copyright restrictions apply; do not assume the code is licensed for redistribution or modification.
