# MetaClean

**MetaClean** is a localhost-only metadata inspection and sanitization dashboard designed for Android devices running [Termux](https://termux.dev/).

It inventories accessible shared storage, reports metadata found in supported files, and creates sanitized copies by default. Originals are left in place unless the operator explicitly chooses replacement or deletion.

## Quick start (Termux)

1. Download the repository ZIP from GitHub and extract it.
2. Open Termux and change into the extracted `metaclean/` directory.
3. Run:

   ```bash
   bash setup.sh
   ```

4. Grant Android storage permission when prompted.
5. Start the dashboard from any directory:

   ```bash
   metaclean
   ```

Open **http://127.0.0.1:5000** in the device browser. The launcher also attempts to open it automatically.

Useful commands:

```bash
metaclean          # start the service
metaclean open     # start and open the dashboard
metaclean status   # show service state
metaclean stop     # stop the service
metaclean restart  # restart the service
metaclean logs     # follow the service log
```

To update an installation after modifying the source, rerun `bash setup.sh` from the updated project directory.

## Features

- Recursive inventory of accessible regular files under `~/storage/shared`, including unsupported extensions.
- Metadata inspection using ExifTool and MAT2 when available.
- Image and video thumbnails, file filtering, progress tracking, and batch jobs.
- **RUN ALL** scans storage and sanitizes supported originals into adjacent `.cleaned` copies.
- Optional monitoring detects new or changed supported files and sanitizes them into copies while the MetaClean service is running.
- Optional replacement mode retains a backup before replacing an original.
- Explicitly confirmed deletion; Termux:API notifications when the matching package and Android app are installed.
- Local web server bound to `127.0.0.1`, with a per-process API token and Host-header validation.

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

The runnable project is in `metaclean/`. The self-contained source bundle is also provided as `MetaClean-Termux.tar.xz`. A GitHub Actions workflow expands the archive into the browsable source directory after the initial bundle upload.

## License

No license has been added yet. Until a license is chosen, standard copyright restrictions apply; do not assume the code is licensed for redistribution or modification.
