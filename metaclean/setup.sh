#!/data/data/com.termux/files/usr/bin/bash
set -u

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR" || exit 1

C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_OFF=$'\033[0m'
ok()   { printf '%s[ok]%s   %s\n' "$C_OK" "$C_OFF" "$*"; }
warn() { printf '%s[warn]%s %s\n' "$C_WARN" "$C_OFF" "$*"; }
fail() { printf '%s[fail]%s %s\n' "$C_ERR" "$C_OFF" "$*"; }
step() { printf '\n==> %s\n' "$*"; }

if ! command -v pkg >/dev/null 2>&1 || [ -z "${PREFIX:-}" ]; then
  fail "This script must be run inside Termux."
  exit 1
fi

pip_install() {
  python -m pip install "$@" >/dev/null 2>&1 && return 0
  python -m pip install --break-system-packages "$@" >/dev/null 2>&1
}

step "Refreshing package lists"
pkg update -y >/dev/null 2>&1 || warn "pkg update reported problems; continuing"
DEBIAN_FRONTEND=noninteractive apt-get -y -o Dpkg::Options::=--force-confold upgrade >/dev/null 2>&1 \
  || warn "pkg upgrade reported problems; continuing"

step "Installing required packages"
CORE_FAILED=0
for p in python ffmpeg exiftool termux-api; do
  if pkg install -y "$p" >/dev/null 2>&1; then ok "$p"; else fail "$p could not be installed"; CORE_FAILED=1; fi
done
if [ "$CORE_FAILED" -ne 0 ]; then
  fail "Required packages are missing. Check your connection or run: termux-change-repo"
  exit 1
fi

step "Installing optional packages"
for p in qpdf termux-tools libffi openssl clang make pkg-config glib gobject-introspection libcairo gdk-pixbuf poppler; do
  if pkg install -y "$p" >/dev/null 2>&1; then ok "$p"; else warn "$p not installed (optional)"; fi
done

step "Linking shared storage"
if [ ! -d "$HOME/storage/shared" ]; then
  echo "Android will ask for storage permission. Tap Allow."
  termux-setup-storage
  for _ in $(seq 1 45); do
    [ -d "$HOME/storage/shared" ] && break
    sleep 1
  done
fi
if [ -d "$HOME/storage/shared" ] && ls "$HOME/storage/shared" >/dev/null 2>&1; then
  ok "$HOME/storage/shared is readable"
else
  warn "Storage is not linked yet. Run termux-setup-storage, allow access, then start MetaClean."
fi

step "Installing Python packages"
if python -m pip install -r requirements.txt >/dev/null 2>&1 || python -m pip install --break-system-packages -r requirements.txt >/dev/null 2>&1; then
  ok "flask, werkzeug, waitress"
else
  fail "pip could not install requirements.txt"
  exit 1
fi

step "MAT2 policy"
echo "MAT2 is intentionally not installed on Termux."
echo "MetaClean uses ExifTool, FFmpeg, qpdf and the built-in Office scrubber instead."

mkdir -p "$HOME/.cache/metaclean"
chmod +x "$APP_DIR/run.sh" "$APP_DIR/setup.sh" "$APP_DIR/app.py" 2>/dev/null || true

step "Summary"
printf '  exiftool            %s\n' "$(exiftool -ver 2>/dev/null || echo missing)"
printf '  ffmpeg              %s\n' "$(ffmpeg -version 2>/dev/null | head -n 1 | cut -d' ' -f3 || echo missing)"
printf '  qpdf                %s\n' "$(qpdf --version 2>/dev/null | head -n 1 || echo missing)"
printf '  mat2                disabled on Termux'
if command -v termux-notification >/dev/null 2>&1; then
  printf '  termux-notification present\n'
else
  printf '  termux-notification missing\n'
fi
echo
echo "Notifications also need the Termux:API Android app, installed from the same source as Termux (F-Droid or GitHub)."
echo "Start MetaClean with: ./run.sh"

step "Installing a permanent global launcher"
INSTALL_DIR="$HOME/.local/share/metaclean"
mkdir -p "$HOME/.local/share" "$PREFIX/bin"
SOURCE_REAL="$(cd "$APP_DIR" && pwd -P)"
TARGET_REAL="$(mkdir -p "$INSTALL_DIR" && cd "$INSTALL_DIR" && pwd -P)"
if [ "$SOURCE_REAL" != "$TARGET_REAL" ]; then
  cp -a "$APP_DIR/." "$INSTALL_DIR/"
fi
chmod +x "$INSTALL_DIR/app.py" "$INSTALL_DIR/run.sh" "$INSTALL_DIR/setup.sh"
ln -sf "$INSTALL_DIR/run.sh" "$PREFIX/bin/metaclean"
ln -sf "$INSTALL_DIR/setup.sh" "$PREFIX/bin/metaclean-setup"
case ":$PATH:" in *":$PREFIX/bin:"*) ;; *) warn "$PREFIX/bin is not currently in PATH; add export PATH=\"$PREFIX/bin:\$PATH\" to ~/.bashrc" ;; esac
ok "Installed globally: metaclean"
ok "Installed updater: metaclean-setup"
