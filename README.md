# MetaClean

**MetaClean** is a cross-platform metadata inspection and sanitization toolkit for Android/Termux, Linux distributions and Windows. It includes a local dashboard and an optional private-LAN upload host.

It inventories accessible files, reports metadata in supported formats, and creates cleaned copies by default. Original files are preserved unless the operator explicitly enables replacement or the separate **Delete original after successful cleanup** option.

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

## Linux installation

Supported package-manager families: APT, DNF, Pacman, Zypper, APK and XBPS. The installer provisions Python, ExifTool, FFmpeg, qpdf, a virtual environment and the global `metaclean` command. MAT2 is optional on Linux.

Run from a cloned repository:

```bash
bash install-linux.sh
```

Or install directly without cloning:

```bash
curl -fsSL https://raw.githubusercontent.com/0xb0rn3/MetaClean/main/install-linux.sh | bash
```

Start with `metaclean`. The default file root is `~/MetaClean/Files`.

## Automatic Termux/Linux installer

A single Unix bootstrapper detects Termux or a standard Linux distribution and starts the matching setup:

```bash
curl -fsSL https://raw.githubusercontent.com/0xb0rn3/MetaClean/main/install.sh | bash
```

Use the Windows PowerShell command in the Windows section above on Windows.

## Windows installation

Windows 10/11 with [Windows Package Manager (winget)](https://learn.microsoft.com/windows/package-manager/winget/) is required. Open PowerShell and run:

```powershell
irm https://raw.githubusercontent.com/0xb0rn3/MetaClean/main/install.ps1 | iex
```

The bootstrapper installs Python 3.12, FFmpeg, ExifTool and qpdf, creates a virtual environment, installs Python requirements, and adds `metaclean` to the user's PATH. Open a new PowerShell window and run:

```powershell
metaclean
```

The default file root is `%USERPROFILE%\MetaClean\Files`.

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
- Metadata inspection using ExifTool and MAT2 when available. Termux deliberately skips MAT2 and uses ExifTool, FFmpeg and built-in document fallbacks.
- Image and video thumbnails, file filtering, progress tracking, and batch jobs.
- **Duplicate finder** scans all accessible file types for byte-identical copies using SHA-256 hashes, groups matching files regardless of names, and estimates reclaimable space. It is read-only until removal is explicitly confirmed; choose one keeper per group and MetaClean rechecks the files before deleting extra copies.
- **RUN ALL** scans storage and sanitizes supported originals into adjacent `.cleaned` copies.
- Optional **Delete original after successful cleanup** removes a source only after its cleaned copy has been created successfully. It applies to manually selected cleaning and **RUN ALL**, is off by default, works only in copy mode, and is not secure erasure.
- Optional **Host for devices on your local network** turns the computer or Termux device into a processing server. Another device opens a generated link, uploads supported files, and downloads a ZIP cleaned by the host's CPU and installed tools.
- Termux uses the same all-interface server listener, token-protected upload portal and temporary-file processing path as Linux and Windows. While Termux Host mode is enabled, MetaClean requests an Android wake lock through Termux:API and releases it when hosting is stopped.
- Remote uploads and outputs use a temporary host directory and are removed when the download response closes. Remote source files are never written into the host's normal inventory and the source on the uploading device is not changed.
- Optional monitoring detects new or changed supported files and sanitizes them into copies while the MetaClean service is running.
- Optional replacement mode retains a backup before replacing an original.
- Explicitly confirmed deletion; Termux:API notifications when the matching package and Android app are installed.
- Local dashboard protected by a per-process API token. LAN uploads are disabled until the host explicitly enables them and shares the generated access link.

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
- The server's network listener is guarded: the normal dashboard and API remain loopback-only; the separate upload portal accepts private-LAN clients only while Host mode is enabled and only with its generated bearer link.
- Host mode is intended for a trusted Wi-Fi/LAN. Do not port-forward TCP 5000 or expose the host to the public internet. Stop hosting to revoke the current link.
- On Termux, install the separate Termux:API Android app from the same source as the Termux app; the `termux-api` package alone does not install that Android companion. Host mode displays whether the wake-lock request succeeded. The lock uses additional battery power, and Android vendor battery controls or Wi-Fi changes can still interrupt service. Keep the phone on the same Wi-Fi network as clients and stop hosting when finished.
- A remote upload is temporarily written to the host's system temp directory for processing and download. Normal completion removes the temporary workspace when the response closes; an abrupt power loss or process kill can interrupt that cleanup.
- Automatic cleaning uses copy mode. Review outputs before sharing or deleting originals.
- Duplicate detection is exact-content matching, not visual similarity: resized, recompressed or edited photos are not duplicates unless their bytes are identical. Duplicate scan includes all accessible regular files, including formats MetaClean cannot clean. Keep at least one copy in every group; deletion is ordinary filesystem deletion.
- Metadata removal is format-specific. A clean verification scan is not proof that every possible embedded provenance structure has been removed.
- MetaClean is **not** a secure-erasure tool. Flash storage wear levelling, snapshots, caches, and cloud backups prevent reliable forensic erasure through ordinary file deletion.
- Keep independent backups of important files. Use replace and delete actions carefully.

## Project layout

The runnable project is in `metaclean/`. The self-contained source bundle is also provided as `MetaClean-Termux.tar.xz`.

## License and original-author attribution

MetaClean is licensed under the **Apache License 2.0**. See [LICENSE](LICENSE).

The accompanying [NOTICE](NOTICE) identifies the original project author and repository owner as **@0xb0rn3** and links to the original repository: https://github.com/0xb0rn3/MetaClean.

Apache License 2.0 Section 4(c) and (d) require downstream distributors of source or derivative works to retain applicable original attribution notices and, because this project includes a NOTICE file, to carry a readable copy of its applicable attribution in the NOTICE file, source, accompanying documentation, or the derivative application's normal notices display. The MetaClean dashboard and remote upload portal also show the original-author credit.

You may modify and redistribute the project under the Apache 2.0 terms. Mark modified files clearly and do not imply that the original author endorses a fork. See the full license for the exact conditions.
