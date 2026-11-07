#!/usr/bin/env bash
set -euo pipefail

REPO_ARCHIVE="https://github.com/0xb0rn3/MetaClean/archive/refs/heads/main.tar.gz"
SCRIPT_DIR=""
if [[ "${BASH_SOURCE[0]:-}" == /* ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P || true)"
fi

if command -v pkg >/dev/null 2>&1 && [[ -n "${PREFIX:-}" ]]; then
  echo "[MetaClean] Termux detected."
  if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/metaclean/setup.sh" ]]; then
    exec bash "$SCRIPT_DIR/metaclean/setup.sh"
  elif [[ -f "$PWD/metaclean/setup.sh" ]]; then
    exec bash "$PWD/metaclean/setup.sh"
  fi
  command -v curl >/dev/null 2>&1 || { echo "Install curl first: pkg install curl tar"; exit 1; }
  TMP="$(mktemp -d)"
  trap 'rm -rf "$TMP"' EXIT
  curl -fsSL "$REPO_ARCHIVE" | tar -xz -C "$TMP"
  bash "$TMP/MetaClean-main/metaclean/setup.sh"
  exit $?
fi

if [[ "$(uname -s 2>/dev/null || true)" == Linux ]]; then
  echo "[MetaClean] Linux detected."
  if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/install-linux.sh" ]]; then
    exec bash "$SCRIPT_DIR/install-linux.sh"
  elif [[ -f "$PWD/install-linux.sh" ]]; then
    exec bash "$PWD/install-linux.sh"
  fi
  command -v curl >/dev/null 2>&1 || { echo "curl is required to download the Linux installer."; exit 1; }
  exec bash <(curl -fsSL "https://raw.githubusercontent.com/0xb0rn3/MetaClean/main/install-linux.sh")
fi

echo "Unsupported platform. Use install.ps1 on Windows or the dedicated installer for your OS."
exit 1
