# MetaClean for Termux

MetaClean is a localhost-only Flask dashboard for inventorying shared Android storage, inspecting metadata, and cleaning supported files into separate `.cleaned` copies.

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

## Updating

For Git clone installations:

```bash
cd ~/MetaClean
git pull
cd metaclean
bash setup.sh
```

For curl or ZIP installations, extract the latest project files again and rerun `bash setup.sh` from the updated project directory.

## Workflow

- **Scan** inventories all accessible regular files under `~/storage/shared`, including unknown extensions. Android's protected `Android/data` and `Android/obb` trees are excluded because ordinary Termux storage permission does not grant access to them.
- **RUN ALL** inventories storage and cleans every supported original using copy mode. Unsupported files remain visible and are never sent through an arbitrary cleaner.
- **Automatic monitoring** watches supported file signatures while MetaClean's server process is running. It cleans new or changed supported files into adjacent `.cleaned` copies. The preference persists and resumes the next time the service starts.
- Individual inspection and cleaning remain available from file cards. Manual replace mode must be used cautiously; the backend retains a backup before replacing an original.

## Safety and limitations

MetaClean is not a secure-erasure utility. Flash storage wear levelling, filesystem snapshots, cloud backups, and Android media caches make guaranteed forensic erasure impossible through ordinary file deletion. The automatic workflow never overwrites originals. Metadata tools have format-specific coverage; a clean verification scan is evidence only for the tags those tools can inspect, not proof that every hidden provenance or C2PA structure is absent. Keep backups of important files.

The service binds only to `127.0.0.1`; it is not exposed to the LAN. Termux:API notifications require both the `termux-api` package and the matching Android Termux:API app.
