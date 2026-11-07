# MetaClean for Termux

MetaClean is a localhost-only Flask dashboard for inventorying shared Android storage, inspecting metadata, and cleaning supported files into separate `.cleaned` copies.

## Install

1. Extract this directory somewhere in Termux home storage.
2. Run `bash setup.sh`.
3. Grant Android storage permission when prompted.
4. Run `metaclean` from any working directory. It starts the local service and opens `http://127.0.0.1:5000`.

Commands: `metaclean`, `metaclean open`, `metaclean status`, `metaclean stop`, `metaclean restart`, and `metaclean logs`. To update the installed copy after changing source files, rerun `bash setup.sh` from the updated project directory.

## Workflow

- **Scan** inventories all accessible regular files under `~/storage/shared`, including unknown extensions. Android's protected `Android/data` and `Android/obb` trees are excluded because ordinary Termux storage permission does not grant access to them.
- **RUN ALL** inventories storage and cleans every supported original using copy mode. Unsupported files remain visible and are never sent through an arbitrary cleaner.
- **Automatic monitoring** watches supported file signatures while MetaClean's server process is running. It cleans new or changed supported files into adjacent `.cleaned` copies. The preference persists and resumes the next time the service starts.
- Individual inspection and cleaning remain available from file cards. Manual replace mode must be used cautiously; the backend retains a backup before replacing an original.

## Safety and limitations

MetaClean is not a secure-erasure utility. Flash storage wear levelling, filesystem snapshots, cloud backups, and Android media caches make guaranteed forensic erasure impossible through ordinary file deletion. The automatic workflow never overwrites originals. Metadata tools have format-specific coverage; a clean verification scan is evidence only for the tags those tools can inspect, not proof that every hidden provenance or C2PA structure is absent. Keep backups of important files.

The service binds only to `127.0.0.1`; it is not exposed to the LAN. Termux:API notifications require both the `termux-api` package and the matching Android Termux:API app.
