#!/usr/bin/env bash
set -euo pipefail

REPO_ARCHIVE="https://github.com/0xb0rn3/MetaClean/archive/refs/heads/main.tar.gz"
INSTALL_DIR="$HOME/.local/share/metaclean"
TEMP_SOURCE=""

say(){ printf '\n[MetaClean] %s\n' "$*"; }
fail(){ printf '[MetaClean] ERROR: %s\n' "$*" >&2; exit 1; }

# Supports a cloned checkout and: curl .../install-linux.sh | bash
SCRIPT_DIR=""
if [[ "${BASH_SOURCE[0]:-}" == /* ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" 2>/dev/null && pwd -P || true)"
fi
if [[ -n "$SCRIPT_DIR" && -f "$SCRIPT_DIR/metaclean/app.py" ]]; then
  SOURCE_DIR="$SCRIPT_DIR/metaclean"
elif [[ -f "$PWD/metaclean/app.py" ]]; then
  SOURCE_DIR="$PWD/metaclean"
else
  command -v curl >/dev/null 2>&1 || fail "curl is required to download MetaClean."
  TEMP_SOURCE="$(mktemp -d)"
  say "Downloading MetaClean source"
  curl -fsSL "$REPO_ARCHIVE" | tar -xz -C "$TEMP_SOURCE"
  SOURCE_DIR="$TEMP_SOURCE/MetaClean-main/metaclean"
fi
[[ -f "$SOURCE_DIR/app.py" ]] || fail "Could not locate metaclean/app.py."

if [[ $EUID -eq 0 ]]; then
  SUDO=()
elif command -v sudo >/dev/null 2>&1; then
  SUDO=(sudo)
else
  fail "Install system packages as root or install sudo."
fi

say "Detecting Linux distribution and installing native tools"
if command -v apt-get >/dev/null 2>&1; then
  "${SUDO[@]}" apt-get update
  "${SUDO[@]}" apt-get install -y python3 python3-venv python3-pip ffmpeg libimage-exiftool-perl qpdf
  if apt-cache show mat2 >/dev/null 2>&1; then "${SUDO[@]}" apt-get install -y mat2 || true; fi
elif command -v dnf >/dev/null 2>&1; then
  "${SUDO[@]}" dnf install -y python3 python3-pip ffmpeg perl-Image-ExifTool qpdf
  "${SUDO[@]}" dnf install -y mat2 >/dev/null 2>&1 || true
elif command -v pacman >/dev/null 2>&1; then
  "${SUDO[@]}" pacman -Sy --needed --noconfirm python python-pip ffmpeg perl-image-exiftool qpdf
  "${SUDO[@]}" pacman -S --needed --noconfirm mat2 >/dev/null 2>&1 || true
elif command -v zypper >/dev/null 2>&1; then
  "${SUDO[@]}" zypper --non-interactive install python3 python3-pip ffmpeg perl-Image-ExifTool qpdf
  "${SUDO[@]}" zypper --non-interactive install mat2 >/dev/null 2>&1 || true
elif command -v apk >/dev/null 2>&1; then
  "${SUDO[@]}" apk add python3 py3-pip py3-virtualenv ffmpeg exiftool qpdf
  "${SUDO[@]}" apk add mat2 >/dev/null 2>&1 || true
elif command -v xbps-install >/dev/null 2>&1; then
  "${SUDO[@]}" xbps-install -Syu python3 python3-pip ffmpeg perl-Image-ExifTool qpdf
  "${SUDO[@]}" xbps-install -y mat2 >/dev/null 2>&1 || true
else
  fail "Unsupported package manager. Install Python 3, ExifTool, FFmpeg and qpdf, then rerun this installer."
fi

say "Installing MetaClean into $INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$HOME/.local/bin" "$HOME/MetaClean/Files"
cp -a "$SOURCE_DIR/." "$INSTALL_DIR/"
python3 -m venv "$INSTALL_DIR/.venv"
"$INSTALL_DIR/.venv/bin/python" -m pip install --upgrade pip
"$INSTALL_DIR/.venv/bin/python" -m pip install -r "$INSTALL_DIR/requirements.txt"

cat > "$HOME/.local/bin/metaclean" <<'LAUNCHER'
#!/usr/bin/env bash
APP_HOME="$HOME/.local/share/metaclean"
exec "$APP_HOME/.venv/bin/python" "$APP_HOME/app.py" "$@"
LAUNCHER
chmod +x "$HOME/.local/bin/metaclean"

for profile in "$HOME/.bashrc" "$HOME/.zshrc"; do
  if [[ -f "$profile" ]] && ! grep -Fq 'export PATH="$HOME/.local/bin:$PATH"' "$profile"; then
    printf '\n# MetaClean command\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$profile"
  fi
done
export PATH="$HOME/.local/bin:$PATH"

say "Installation complete"
printf '  Python:    %s\n' "$(python3 --version 2>&1)"
printf '  ExifTool:  %s\n' "$(exiftool -ver 2>/dev/null || echo 'not detected')"
printf '  FFmpeg:    %s\n' "$(ffmpeg -version 2>/dev/null | head -n 1 || echo 'not detected')"
printf '  qpdf:      %s\n' "$(qpdf --version 2>/dev/null | head -n 1 || echo 'not detected')"
printf '  MAT2:      %s\n' "$(mat2 --version 2>/dev/null | head -n 1 || echo 'not installed; optional on Linux')"
echo
echo "Run: metaclean"
echo "Then open: http://127.0.0.1:5000"
echo "Default file root: $HOME/MetaClean/Files"
echo "To host uploads for trusted devices, open Cleaning options > Host for devices on your local network."
[[ -n "$TEMP_SOURCE" ]] && rm -rf "$TEMP_SOURCE"
