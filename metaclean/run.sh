#!/data/data/com.termux/files/usr/bin/bash
set -u
APP_HOME="$HOME/.local/share/metaclean"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
PORT="${MCLEAN_PORT:-5000}"
URL="http://127.0.0.1:${PORT}"
PIDFILE="$HOME/.cache/metaclean/server.pid"
LOGFILE="$HOME/.cache/metaclean/server.log"
mkdir -p "$(dirname "$PIDFILE")"

is_running() {
  [ -f "$PIDFILE" ] || return 1
  local pid; pid="$(cat "$PIDFILE" 2>/dev/null || true)"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

case "${1:-start}" in
  stop)
    if is_running; then kill "$(cat "$PIDFILE")" 2>/dev/null || true; rm -f "$PIDFILE"; echo "MetaClean stopped."; else echo "MetaClean is not running."; fi
    command -v termux-wake-unlock >/dev/null 2>&1 && termux-wake-unlock >/dev/null 2>&1 || true
    exit 0 ;;
  status)
    if is_running; then echo "MetaClean is running at $URL (PID $(cat "$PIDFILE"))."; else echo "MetaClean is stopped."; fi
    exit 0 ;;
  logs) tail -n 100 -f "$LOGFILE"; exit 0 ;;
  restart) "$0" stop; sleep 1 ;;
  start) ;;
  *) echo "Usage: metaclean [start|stop|restart|status|logs|open]"; exit 2 ;;
esac

if [ ! -d "$APP_HOME" ]; then echo "MetaClean installation not found. Run setup.sh first."; exit 1; fi
if ! command -v python >/dev/null 2>&1 || ! python -c 'import flask, waitress' >/dev/null 2>&1; then echo "Dependencies missing. Run metaclean-setup."; exit 1; fi
if ! is_running; then
  rm -f "$PIDFILE"
  (cd "$APP_HOME" && nohup env MCLEAN_PORT="$PORT" GI_TYPELIB_PATH="${PREFIX}/lib/girepository-1.0${GI_TYPELIB_PATH:+:$GI_TYPELIB_PATH}" python app.py >>"$LOGFILE" 2>&1 </dev/null & echo $! > "$PIDFILE")
  sleep 2
fi
if ! is_running; then echo "MetaClean failed to start. Check: metaclean logs"; exit 1; fi
echo "MetaClean is available at $URL"
if [ "${1:-}" = "open" ] || [ "${2:-}" = "--open" ]; then
  command -v termux-open-url >/dev/null 2>&1 && termux-open-url "$URL" || echo "Open $URL in your browser."
else
  command -v termux-open-url >/dev/null 2>&1 && termux-open-url "$URL" >/dev/null 2>&1 || true
fi
