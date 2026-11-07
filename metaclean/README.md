# MetaClean for Termux

MetaClean is a Flask dashboard and optional private-LAN processing server for Android/Termux. It inventories shared Android storage, inspects metadata, and cleans supported files into separate `.cleaned` copies. When Host mode is enabled, the Termux device can receive uploads from other phones and computers and process them locally.

## Installation options

Run these commands inside **Termux**. Choose one method.

### Option 1 — Git clone (recommended)

```bash
pkg update -y
pkg install git -y
git clone https://github.com/0xb0rn3/MetaClean.git
cd MetaClean/metaclean
bash setup.sh
```

### Option 2 — Direct curl (no Git required)

Downloads the current main-branch archive, extracts the runnable application files to `~/MetaClean`, and installs:

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

### Option 3 — GitHub ZIP

1. Download the ZIP from [github.com/0xb0rn3/MetaClean](https://github.com/0xb0rn3/MetaClean) using **Code → Download ZIP**.
2. Extract it in Termux.
3. Enter the extracted `MetaClean-main/metaclean/` directory.
4. Run `bash setup.sh`.

## Complete setup

Grant shared-storage permission when Android prompts you. Setup installs required packages and Python dependencies and creates the global `metaclean` command.

Start from any directory:

```bash
metaclean
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

Commands: `metaclean`, `metaclean open`, `metaclean status`, `metaclean stop`, `metaclean restart`, and `metaclean logs`. Run `metaclean-setup` to rerun the installer/updater.

## Termux MAT2 policy

MAT2 is deliberately skipped on Termux. MetaClean does not probe or select it there, even if a copy happens to exist in the environment. This avoids Termux compatibility problems. Linux desktops and servers may use MAT2 when available; Windows uses the native ExifTool, FFmpeg and qpdf tools.

## Host mode for iPhone and other LAN devices

Open the dashboard's **Cleaning options → Host for devices on your local network**, then select **Start hosting**. Copy one of the generated links and open it on a device connected to the same private Wi-Fi/LAN. The remote upload page accepts up to 25 files per batch (maximum 1 GB request) and returns a ZIP of cleaned copies processed by the Termux device.

Termux is a real LAN host in this mode, not just a client: MetaClean listens on the network interface, discovers the phone's active private IPv4 addresses, and runs the same authenticated upload-and-clean pipeline used by Linux and Windows. While hosting is enabled it requests `termux-wake-lock`; stopping Host mode releases the lock. This improves reliability while the screen is off, but uses more battery and cannot override every Android manufacturer power-management restriction. For this feature, install both the `termux-api` package and the separate Termux:API Android app from the same installation source as Termux. The dashboard shows a warning if the wake-lock request fails.

The upload portal is separate from the personal-storage dashboard. Remote clients cannot browse the host's shared storage. Uploaded sources and cleaned outputs are kept in a temporary host directory only during processing and download, then removed when the response closes. Original files on the uploading phone/computer are not modified. Stop hosting to revoke the current link. Do not port-forward the host or expose it to the public internet.

## Delete original after successful cleanup

The cleaning options include **Delete original after successful cleanup**. It is off by default and applies to manually selected cleaning and **RUN ALL** in copy mode. MetaClean first writes the cleaned copy; it deletes the original only after the copy operation succeeds. If cleaning fails, the original is retained. This is normal file deletion, not secure erasure.
## Updating

For Git clone installations:

```bash
cd ~/MetaClean
git pull
cd metaclean
bash setup.sh
```

For curl or ZIP installations, extract the latest project files again and rerun `bash setup.sh` from the updated project directory.

## Smarter file discovery

The dashboard's **Media & docs** view prioritises recognised user content rather than filling the main view with miscellaneous app and system files. Detection covers common photos and camera RAW formats, video containers, audio formats, and office/document formats, including formats that are view-only.

- **Other files** remains available as a separate tab for unrecognised file types.
- Obvious clutter is excluded from inventory: cache/thumbnail/temp folders, `.nomedia`, OS housekeeping files, and incomplete download/temp/lock/log files.
- Detection is broader than cleaning support. Files labelled **view only** can be browsed but cannot be selected for batch cleaning unless a safe cleaner is registered.
- RUN ALL and automatic monitoring still operate only on the existing safe-cleaner registry. Detecting a file does not make it eligible for cleaning.

## Workflow

- **Scan** inventories all accessible regular files under `~/storage/shared`, including unknown extensions. Android's protected `Android/data` and `Android/obb` trees are excluded because ordinary Termux storage permission does not grant access to them.
- **RUN ALL** inventories storage and cleans every supported original using copy mode. Unsupported files remain visible and are never sent through an arbitrary cleaner.
- **Automatic monitoring** watches supported file signatures while MetaClean's server process is running. It cleans new or changed supported files into adjacent `.cleaned` copies. The preference persists and resumes the next time the service starts.
- Individual inspection and cleaning remain available from file cards. Manual replace mode must be used cautiously; the backend retains a backup before replacing an original.

## License and attribution

This project is licensed under the **Apache License 2.0**; see [LICENSE](LICENSE). The accompanying [NOTICE](NOTICE) identifies the original project author and repository owner as **@0xb0rn3** and links to https://github.com/0xb0rn3/MetaClean.

Under Apache 2.0 Section 4(c) and (d), distributors of source or derivative works must retain applicable attribution notices and carry a readable copy of the applicable NOTICE attribution in the derivative's NOTICE file, source, accompanying documentation, or normal third-party notices display. The MetaClean dashboard and remote upload portal display the original-author credit.

Modified files must be marked as changed, and forks must not imply endorsement by the original author. Consult the full LICENSE file for the exact terms.

## Safety and limitations

MetaClean is not a secure-erasure utility. Flash storage wear levelling, filesystem snapshots, cloud backups, and Android media caches make guaranteed forensic erasure impossible through ordinary file deletion. The automatic workflow never overwrites originals. Metadata tools have format-specific coverage; a clean verification scan is evidence only for the tags those tools can inspect, not proof that every hidden provenance or C2PA structure is absent. Keep backups of important files.

The normal dashboard and API remain local-only. The network listener is guarded so only the separate upload portal can be reached by private-LAN clients after Host mode is explicitly enabled and a sharing link is supplied. Termux notifications and Host-mode wake locks require both the `termux-api` package and the matching Android Termux:API app.
