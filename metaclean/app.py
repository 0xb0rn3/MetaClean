#!/usr/bin/env python3
"""MetaClean - inspect and strip file metadata from a local web UI inside Termux."""

import errno
import hashlib
import hmac
import ipaddress
import json
import mimetypes
import os
import platform
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
import zipfile
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlsplit

from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.exceptions import HTTPException
from werkzeug.utils import secure_filename

# ---------------------------------------------------------------- configuration

BIND_HOST = "0.0.0.0"  # Network socket is guarded; LAN access remains disabled until Host is enabled.
PORT = int(os.environ.get("MCLEAN_PORT", "5000"))
IS_TERMUX = bool(os.environ.get("PREFIX", "").startswith("/data/data/com.termux")) or "com.termux" in sys.executable.lower()
IS_WINDOWS = os.name == "nt"
IS_LINUX = sys.platform.startswith("linux") and not IS_TERMUX
PLATFORM_NAME = "Termux" if IS_TERMUX else ("Windows" if IS_WINDOWS else ("Linux" if IS_LINUX else platform.system()))
DEFAULT_ROOT = "~/storage/shared" if IS_TERMUX else "~/MetaClean/Files"
ROOT = os.path.abspath(os.path.expanduser(os.environ.get("MCLEAN_ROOT", DEFAULT_ROOT)))
ROOT_REAL = os.path.realpath(ROOT)
WORK_BASE = os.path.abspath(os.path.expanduser(os.environ.get("MCLEAN_TMP") or tempfile.gettempdir()))
if IS_WINDOWS:
    _data_home = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    DEFAULT_DATA = os.path.join(_data_home, "MetaClean", "Data")
else:
    DEFAULT_DATA = "~/.cache/metaclean"
DATA_DIR = os.path.abspath(os.path.expanduser(os.environ.get("MCLEAN_DATA", DEFAULT_DATA)))
THUMB_DIR = os.path.join(DATA_DIR, "thumbs")
TOKEN = secrets.token_urlsafe(24)
MAX_REMOTE_FILES = 25
MAX_UPLOAD_BYTES = 1024 * 1024 * 1024

CLEAN_MARK = ".cleaned"
ENGINES = ("auto", "mat2", "exiftool", "both")
MODES = ("copy", "replace")
CATEGORIES = ("ai", "location", "identity", "software", "device", "other")
FLAGGED = ("ai", "location", "identity", "software")

TYPES = {
    "image": {".jpg", ".jpeg", ".png", ".webp", ".heic"},
    "video": {".mp4", ".mkv", ".mov"},
    "audio": {".mp3", ".flac"},
    "document": {".pdf", ".docx", ".xlsx", ".pptx"},
}
EXT_TYPE = {ext: kind for kind, exts in TYPES.items() for ext in exts}
# Discovery is broader than cleaning support: detection never implies cleanability.
DISCOVERY_TYPES = {
    "image": {".jpg",".jpeg",".jpe",".png",".gif",".webp",".heic",".heif",".avif",".bmp",".tif",".tiff",".dng",".cr2",".cr3",".nef",".arw",".raf",".rw2",".orf",".pef"},
    "video": {".mp4",".m4v",".mkv",".mov",".3gp",".3g2",".webm",".avi",".wmv",".mpg",".mpeg",".ts",".m2ts",".mts"},
    "audio": {".mp3",".m4a",".aac",".wav",".flac",".ogg",".opus",".amr",".aiff",".aif",".wma",".mid",".midi"},
    "document": {".pdf",".doc",".docx",".docm",".odt",".rtf",".txt",".md",".csv",".tsv",".xls",".xlsx",".xlsm",".ods",".ppt",".pptx",".pptm",".odp",".epub"},
}
DISCOVERY_EXT_TYPE = {ext: kind for kind, extensions in DISCOVERY_TYPES.items() for ext in extensions}
OOXML_EXT = {".docx", ".xlsx", ".pptx"}
EXIF_WRITE = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".mp4", ".mov", ".mp3", ".flac"}
SKIP_DIRS = {"Android/data", "Android/obb"}
NOISE_DIRS = {".thumbnails", ".cache", "cache", "caches", "tmp", "temp", "thumbnails", "lost+found", "$recycle.bin", "recycle.bin"}
NOISE_FILES = {".nomedia", ".ds_store", "thumbs.db", "desktop.ini"}
NOISE_SUFFIXES = (".tmp", ".temp", ".part", ".partial", ".crdownload", ".download", ".lock", ".swp", ".log", ".bak")

for _ext, _mime in {
    ".heic": "image/heic",
    ".webp": "image/webp",
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".flac": "audio/flac",
}.items():
    mimetypes.add_type(_mime, _ext)

app = Flask(__name__)
app.json.sort_keys = False
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
POOL = ThreadPoolExecutor(max_workers=3, thread_name_prefix="job")
CLEAN_LOCK = threading.Lock()
HOSTING = {"enabled": False, "token": "", "wake_lock": None}
HOSTING_LOCK = threading.RLock()


class ApiError(Exception):
    def __init__(self, message, status=400, code="error"):
        super().__init__(message)
        self.status = status
        self.code = code


class ToolError(Exception):
    pass


# ---------------------------------------------------------------- helpers

def tail(text, limit=300):
    text = (text or "").strip()
    return text[-limit:] if len(text) > limit else text


def run(cmd, timeout=600):
    try:
        return subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout
        )
    except FileNotFoundError:
        raise ToolError(f"{os.path.basename(cmd[0])} is not installed")
    except subprocess.TimeoutExpired:
        raise ToolError(f"{os.path.basename(cmd[0])} timed out after {timeout}s")


def explain(exc):
    if isinstance(exc, (ApiError, ToolError)):
        return str(exc)
    if isinstance(exc, PermissionError):
        return (
            "Permission denied. Check Termux storage access (termux-setup-storage) "
            "or whether another app has the file locked."
        )
    if isinstance(exc, FileNotFoundError):
        return "The file no longer exists."
    if isinstance(exc, OSError):
        if exc.errno == errno.ENOSPC:
            return "No space left on device."
        if exc.errno in (errno.EBUSY, errno.ETXTBSY):
            return "The file is busy or locked by another process."
        if exc.errno == errno.EROFS:
            return "Storage is mounted read-only."
        if exc.errno in (errno.EACCES, errno.EPERM):
            return "Permission denied. The file may be locked or owned by another app."
        return f"I/O error: {exc.strerror or exc}"
    return f"{type(exc).__name__}: {exc}"


def is_cleaned_name(name):
    return os.path.splitext(name)[0].lower().endswith(CLEAN_MARK)


def twin_rel(rel):
    base, ext = os.path.splitext(rel)
    if base.lower().endswith(CLEAN_MARK):
        return base[: -len(CLEAN_MARK)] + ext
    return base + CLEAN_MARK + ext


def rel_of(full):
    return os.path.relpath(full, ROOT)


def resolve(rel):
    if not isinstance(rel, str) or not rel or "\x00" in rel:
        raise ApiError("Invalid file path.", 400, "bad_path")
    full = os.path.normpath(os.path.join(ROOT, rel))
    if full != ROOT and not full.startswith(ROOT + os.sep):
        raise ApiError("Path is outside the storage root.", 403, "outside_root")
    real = os.path.realpath(full)
    if real != ROOT_REAL and not real.startswith(ROOT_REAL + os.sep):
        raise ApiError("Path resolves outside the storage root.", 403, "outside_root")
    if not os.path.isfile(full):
        raise ApiError("File not found.", 404, "not_found")
    return full


def clean_paths(raw):
    if not isinstance(raw, list) or not raw or not all(isinstance(p, str) for p in raw):
        raise ApiError("'paths' must be a non-empty list of file paths.", 400, "bad_paths")
    unique = list(dict.fromkeys(raw))
    if len(unique) > 5000:
        raise ApiError("Too many files for one job (maximum 5000).", 400, "too_many")
    return unique


def int_arg(name, default, low, high):
    try:
        value = int(request.args.get(name, default))
    except (TypeError, ValueError):
        raise ApiError(f"Invalid '{name}' value.", 400, "bad_arg")
    return max(low, min(high, value))


# ---------------------------------------------------------------- external tools

_TOOLS = {"at": 0.0, "data": {}}
_TOOLS_LOCK = threading.Lock()
_PROBES = {
    "exiftool": ["-ver"],
    "mat2": ["--version"],
    "ffmpeg": ["-version"],
    "ffprobe": ["-version"],
    "qpdf": ["--version"],
}


def _probe(cmd):
    try:
        proc = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=30
        )
    except subprocess.TimeoutExpired:
        return False, "timed out"
    except OSError as exc:
        return False, str(exc)
    ok = proc.returncode == 0
    lines = (proc.stdout if ok else (proc.stderr or proc.stdout)).strip().splitlines()
    if not lines:
        return ok, ""
    return ok, (lines[0] if ok else lines[-1])[:160]


def tools(force=False):
    with _TOOLS_LOCK:
        if not force and _TOOLS["data"] and time.time() - _TOOLS["at"] < 60:
            return _TOOLS["data"]
        data = {}
        for name, args in _PROBES.items():
            if name == "mat2" and IS_TERMUX:
                data[name] = {
                    "available": False, "version": "",
                    "error": "intentionally disabled on Termux; use ExifTool and FFmpeg",
                }
                continue
            path = shutil.which(name)
            info = {"available": False, "version": "", "error": "not installed"}
            if path:
                ok, line = _probe([path] + args)
                info = {
                    "available": ok,
                    "version": line if ok else "",
                    "error": "" if ok else (line or "failed to start"),
                }
            data[name] = info
        notif = shutil.which("termux-notification")
        data["termux-notification"] = {
            "available": bool(notif),
            "version": "",
            "error": "" if notif else "not installed",
        }
        _TOOLS["data"] = data
        _TOOLS["at"] = time.time()
        return data


def storage_state():
    if not os.path.isdir(ROOT):
        return {
            "ok": False,
            "writable": False,
            "reason": f"File root not found: {ROOT}. Check the installation and storage path.",
        }
    try:
        os.listdir(ROOT)
    except PermissionError:
        return {
            "ok": False,
            "writable": False,
            "reason": "Permission denied reading shared storage. Run termux-setup-storage and allow access.",
        }
    except OSError as exc:
        return {"ok": False, "writable": False, "reason": f"Cannot read storage: {exc.strerror or exc}"}
    return {"ok": True, "writable": os.access(ROOT, os.W_OK), "reason": ""}


def media_scan(paths):
    exe = shutil.which("termux-media-scan")
    if not exe or not paths:
        return
    for i in range(0, len(paths), 40):
        try:
            subprocess.run([exe] + paths[i : i + 40], capture_output=True, timeout=30)
        except (OSError, subprocess.SubprocessError):
            return


def send_notification(title, content, job_id):
    exe = shutil.which("termux-notification")
    if not exe:
        return "termux-notification is not installed (pkg install termux-api, plus the Termux:API app)"
    cmd = [
        exe, "--title", title, "--content", content,
        "--id", f"metaclean-{job_id}", "--group", "metaclean", "--priority", "high",
        "--action", f"termux-open-url http://127.0.0.1:{PORT}/",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=15)
    except subprocess.TimeoutExpired:
        return "termux-notification timed out (is the Termux:API app installed?)"
    except OSError as exc:
        return str(exc)
    if proc.returncode != 0:
        return tail(proc.stderr or proc.stdout or "termux-notification failed", 160)
    return "sent"


# ---------------------------------------------------------------- metadata inspection

NAME_AI = re.compile(
    r"c2pa|jumbf|claim|manifest|digitalsource|aigenerat|prompt|^parameters$|sd-?metadata|"
    r"comfy|invokeai|generationdata|credentials",
    re.I,
)
GROUP_AI = re.compile(r"c2pa|jumbf|contentcredentials", re.I)
VALUE_AI = re.compile(
    r"trainedalgorithmicmedia|algorithmicmedia|stable[ -]?diffusion|midjourney|dall[-·]?e|openai|"
    r"firefly|comfyui|automatic1111|novelai|civitai|synthid|\bgemini\b|\bimagen\b|chatgpt|"
    r"ai[- ]generated|generative ai|c2pa|content credentials|jumbf|negative prompt|leonardo\.ai|"
    r"\bsdxl\b|bing image creator|made with ai",
    re.I,
)
LOCATION_RE = re.compile(
    r"gps|latitude|longitude|location|coordinates|^city$|^country|province|sublocation|geotag", re.I
)
SOFTWARE_RE = re.compile(
    r"software|creatortool|historysoftwareagent|producer|encoder|encodedby|^application|"
    r"writingapp|writinglibrary|generator|processingsoftware|firmware|toolkit",
    re.I,
)
IDENTITY_RE = re.compile(
    r"artist|author|copyright|owner|serial|by-?line|credit|contributor|publisher|rights|"
    r"lastmodifiedby|^company|^manager|xpauthor|uniqueid|documentid|instanceid|deviceid|userid|"
    r"username|email|phone|account|^creator$|^lastauthor",
    re.I,
)
DEVICE_RE = re.compile(
    r"^make$|^model$|^lens(model|make|info|id)?$|cameramodel|devicemodel|devicemanufacturer|"
    r"androidversion|manufacturer",
    re.I,
)
C2PA_GROUP = re.compile(r"c2pa|jumbf", re.I)


def classify(group, name, value):
    if group.upper().startswith("ICC"):
        return "other"
    if NAME_AI.search(name) or GROUP_AI.search(group) or VALUE_AI.search(value[:4000]):
        return "ai"
    if LOCATION_RE.search(name):
        return "location"
    if SOFTWARE_RE.search(name):
        return "software"
    if IDENTITY_RE.search(name):
        return "identity"
    if DEVICE_RE.search(name):
        return "device"
    return "other"


def exif_rows(path):
    proc = run(["exiftool", "-j", "-G1", "-a", "-u", "-m", "-api", "LargeFileSupport=1", path], timeout=180)
    try:
        data = json.loads(proc.stdout)[0]
    except (ValueError, IndexError, TypeError):
        raise ToolError("exiftool: " + (tail(proc.stderr or proc.stdout, 200) or "no output"))
    rows = []
    for key, value in data.items():
        if key == "SourceFile":
            continue
        group, sep, name = key.partition(":")
        if not sep:
            group, name = "", key
        if group in ("System", "ExifTool"):
            continue
        rows.append((group, name, value))
    return rows


def mat2_show(path):
    exe = shutil.which("mat2") or "mat2"
    proc = run([exe, "--no-sandbox", "--show", path], timeout=180)
    if proc.returncode != 0 and "no-sandbox" in (proc.stderr or "").lower():
        proc = run([exe, "--show", path], timeout=180)
    rows = []
    for line in (proc.stdout or "").splitlines():
        match = re.match(r"^\s+(.+?):\s(.*)$", line)
        if match:
            rows.append(("mat2", match.group(1).strip(), match.group(2)))
    note = ""
    if proc.returncode != 0 and not rows:
        note = "mat2: " + (tail(proc.stderr or proc.stdout, 200) or "could not read this file")
    return rows, note


def probe_streams(path):
    proc = run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path], timeout=90)
    try:
        data = json.loads(proc.stdout or "{}")
    except ValueError:
        raise ToolError("ffprobe returned unreadable output")
    streams = []
    for stream in data.get("streams", []):
        kind = stream.get("codec_type", "unknown")
        streams.append(
            {
                "index": stream.get("index"),
                "type": kind,
                "codec": stream.get("codec_name", "unknown"),
                "tags": stream.get("tags") or {},
                "hidden": kind in ("data", "attachment"),
            }
        )
    return streams


def collect_tags(rows):
    tags = []
    for group, name, value in rows:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        text = text.replace("\x00", "")
        tags.append(
            {
                "group": group,
                "name": name,
                "value": text[:400],
                "truncated": len(text) > 400,
                "category": classify(group, name, text),
            }
        )
    order = {cat: i for i, cat in enumerate(CATEGORIES)}
    tags.sort(key=lambda t: (order[t["category"]], t["group"], t["name"]))
    return tags


def verify(path, T):
    if not T["exiftool"]["available"]:
        return None
    try:
        tags = collect_tags(exif_rows(path))
    except ToolError:
        return None
    return [f"{t['group']}:{t['name']}" for t in tags if t["category"] in FLAGGED]


# ---------------------------------------------------------------- cleaning steps

_CORE_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
    'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
    'xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
)
_APP_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
)
_CUSTOM_XML = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
    'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
)
_OOXML_REPLACE = {
    "docProps/core.xml": _CORE_XML,
    "docProps/app.xml": _APP_XML,
    "docProps/custom.xml": _CUSTOM_XML,
}


def _out(work, idx, ext):
    return os.path.join(work, f"s{idx}{ext}")


def _usable(path):
    return os.path.isfile(path) and os.path.getsize(path) > 0


def step_exiftool(cur, work, ext, ftype, idx, notes):
    out = _out(work, idx, ext)
    cmd = ["exiftool", "-m", "-api", "LargeFileSupport=1", "-all="]
    if ftype == "image":
        cmd += ["-tagsFromFile", "@", "-ColorSpaceTags", "-Orientation", "-icc_profile"]
    cmd += ["-o", out, cur]
    proc = run(cmd, timeout=900)
    if not _usable(out):
        raise ToolError("exiftool failed: " + (tail(proc.stderr or proc.stdout) or "no output produced"))
    if ftype == "image":
        try:
            leftover = [r for r in exif_rows(out) if C2PA_GROUP.search(r[0])]
        except ToolError:
            leftover = []
        if leftover:
            out2 = _out(work, idx + 100, ext)
            run(["exiftool", "-m", "-JUMBF:all=", "-C2PA:all=", "-o", out2, out], timeout=300)
            cleared = False
            if _usable(out2):
                try:
                    cleared = not any(C2PA_GROUP.search(r[0]) for r in exif_rows(out2))
                except ToolError:
                    cleared = False
            if cleared:
                out = out2
            else:
                notes.append(
                    "A C2PA/JUMBF manifest survived the exiftool pass. Choose the 'Both' engine so mat2 re-encodes the image."
                )
    return out


def step_mat2(cur, work, ext, ftype, idx, notes):
    inp = cur
    if os.path.dirname(cur) != work:
        inp = os.path.join(work, f"in{idx}{ext}")
        shutil.copyfile(cur, inp)
    exe = shutil.which("mat2") or "mat2"
    proc = run([exe, "--no-sandbox", inp], timeout=1800)
    if proc.returncode != 0 and "no-sandbox" in (proc.stderr or "").lower():
        proc = run([exe, inp], timeout=1800)
    base, suffix = os.path.splitext(inp)
    out = base + CLEAN_MARK + suffix
    if not _usable(out):
        raise ToolError("mat2 failed: " + (tail(proc.stderr or proc.stdout) or "no output produced"))
    return out


def step_ffmpeg(cur, work, ext, ftype, idx, notes):
    out = _out(work, idx, ext)
    base = [
        "ffmpeg", "-nostdin", "-y", "-v", "error", "-i", cur,
        "-map", "0:v?", "-map", "0:a?", "-map", "0:s?", "-c", "copy",
        "-map_metadata", "-1", "-map_chapters", "-1",
        "-fflags", "+bitexact", "-flags:v", "+bitexact", "-flags:a", "+bitexact",
    ]
    strict = ["-map_metadata:s:v", "-1", "-map_metadata:s:a", "-1", "-map_metadata:s:s", "-1"]
    proc = run(base + strict + [out], timeout=3600)
    if proc.returncode != 0 or not _usable(out):
        if os.path.exists(out):
            os.remove(out)
        proc = run(base + [out], timeout=3600)
        if proc.returncode != 0 or not _usable(out):
            raise ToolError("ffmpeg failed: " + (tail(proc.stderr or proc.stdout) or "no output produced"))
        notes.append("Per-stream tags (language, handler names) may remain; global tags were removed.")
    return out


def step_qpdf(cur, work, ext, ftype, idx, notes):
    out = _out(work, idx, ext)
    proc = run(["qpdf", "--linearize", cur, out], timeout=900)
    if proc.returncode not in (0, 3) or not _usable(out):
        raise ToolError("qpdf failed: " + (tail(proc.stderr or proc.stdout) or "no output produced"))
    return out


def step_ooxml(cur, work, ext, ftype, idx, notes):
    out = _out(work, idx, ext)
    try:
        with zipfile.ZipFile(cur) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                name = item.filename
                if name.lower().startswith("docprops/thumbnail"):
                    continue
                data = zin.read(item)
                if name in _OOXML_REPLACE:
                    data = _OOXML_REPLACE[name].encode("utf-8")
                elif name == "_rels/.rels":
                    data = re.sub(rb'<Relationship\b[^>]*?/thumbnail"[^>]*?/>', b"", data)
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = item.external_attr
                zout.writestr(info, data)
    except zipfile.BadZipFile:
        raise ToolError("This is not a valid Office document.")
    notes.append(
        "Built-in scrubber cleared document properties and the thumbnail. Comments and tracked changes are untouched; install mat2 for a deeper clean."
    )
    return out


STEPS = {
    "exiftool": step_exiftool,
    "mat2": step_mat2,
    "ffmpeg": step_ffmpeg,
    "qpdf": step_qpdf,
    "ooxml": step_ooxml,
}


def plan_for(ftype, ext, engine, T):
    def have(name):
        return T.get(name, {}).get("available", False)

    if engine == "mat2":
        return ["mat2"]
    if engine == "exiftool":
        return ["exiftool", "qpdf"] if ext == ".pdf" else ["exiftool"]
    if ftype == "image":
        plan = ["exiftool"] if have("exiftool") else ["mat2"]
        if engine == "both" and plan == ["exiftool"] and ext != ".heic" and have("mat2"):
            plan.append("mat2")
        return plan
    if ftype in ("video", "audio"):
        plan = ["mat2"] if have("mat2") else ["ffmpeg"]
        if ext in EXIF_WRITE and have("exiftool") and (engine == "both" or plan == ["ffmpeg"]):
            plan.append("exiftool")
        return plan
    if have("mat2"):
        return ["mat2"]
    return ["exiftool", "qpdf"] if ext == ".pdf" else ["ooxml"]


def check_plan(plan, ext, T):
    for step in plan:
        if step in T and not T[step]["available"]:
            detail = T[step]["error"] or "unavailable"
            raise ToolError(f"{step} is required for {ext} files but is not usable ({detail}).")
    if "mat2" in plan and ext == ".heic":
        raise ToolError("mat2 does not support HEIC. Use Auto or exiftool.")
    if "exiftool" in plan and ext not in EXIF_WRITE and ext != ".pdf":
        raise ToolError(f"exiftool cannot write {ext} files. Use Auto or mat2.")


def clean_one(rel, mode, engine, T):
    src = resolve(rel)
    st = os.stat(src)
    ext = os.path.splitext(src)[1].lower()
    ftype = EXT_TYPE.get(ext)
    if not ftype:
        raise ApiError(f"No safe cleaner is registered for {ext or 'extensionless files'}.", 415, "unsupported_type")
    if mode == "copy" and is_cleaned_name(os.path.basename(src)):
        return {"rel": rel, "status": "skipped", "message": "Already a cleaned copy."}
    plan = plan_for(ftype, ext, engine, T)
    check_plan(plan, ext, T)
    os.makedirs(WORK_BASE, exist_ok=True)
    folder = os.path.dirname(src)
    if shutil.disk_usage(WORK_BASE).free < st.st_size * 2.2 + 1048576 or shutil.disk_usage(folder).free < st.st_size * 1.1 + 1048576:
        raise OSError(errno.ENOSPC, "No space left on device")
    work = tempfile.mkdtemp(prefix="mclean-", dir=WORK_BASE)
    part = None
    notes = []
    try:
        cur = src
        for idx, step in enumerate(plan):
            cur = STEPS[step](cur, work, ext, ftype, idx, notes)
        if not _usable(cur):
            raise ToolError("Cleaning produced an empty file. The original was left untouched.")
        if mode == "replace":
            dest = src
        else:
            base, suffix = os.path.splitext(src)
            dest = base + CLEAN_MARK + suffix
        part = f"{dest}.{secrets.token_hex(3)}.part"
        shutil.copyfile(cur, part)
        os.utime(part, ns=(st.st_atime_ns, st.st_mtime_ns))
        if mode == "replace":
            backup = src + ".metaclean.bak"
            if os.path.exists(backup):
                backup = src + f".{int(time.time())}.metaclean.bak"
            shutil.copy2(src, backup)
        os.replace(part, dest)
        part = None
    finally:
        if part and os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
        shutil.rmtree(work, ignore_errors=True)
    after = os.stat(dest)
    index_upsert(dest)
    residual = verify(dest, T)
    return {
        "rel": rel,
        "status": "ok",
        "output": rel_of(dest),
        "engines": plan,
        "before": st.st_size,
        "after": after.st_size,
        "verified": residual is not None,
        "residual": residual or [],
        "notes": notes,
        "dest": dest,
    }


# ---------------------------------------------------------------- index

INDEX = {"items": {}, "scanned_at": None}
INDEX_LOCK = threading.Lock()


def is_noise_path(rel):
    parts = [part.lower() for part in rel.replace("\\", "/").split("/") if part]
    directory_parts = parts if rel.endswith("/") else parts[:-1]
    if any(part in NOISE_DIRS for part in directory_parts):
        return True
    name = parts[-1] if parts else ""
    if name in NOISE_FILES or name.startswith(".~"):
        return True
    return name.endswith("~") or name.endswith(NOISE_SUFFIXES)


def detect_file_type(full, ext):
    kind = DISCOVERY_EXT_TYPE.get(ext)
    if kind:
        return kind
    mime = (mimetypes.guess_type(full, strict=False)[0] or "").lower()
    if mime.startswith("image/"): return "image"
    if mime.startswith("video/"): return "video"
    if mime.startswith("audio/"): return "audio"
    if mime.startswith("text/") or mime in {
        "application/pdf", "application/rtf", "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.oasis.opendocument.text", "application/vnd.oasis.opendocument.spreadsheet",
        "application/vnd.oasis.opendocument.presentation", "application/epub+zip",
    }:
        return "document"
    try:
        with open(full, "rb") as handle:
            head = handle.read(32)
    except OSError:
        return "other"
    if head.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"GIF87a", b"GIF89a", b"BM", b"II*\x00", b"MM\x00*")):
        return "image"
    if head.startswith(b"RIFF") and head[8:12] == b"WEBP": return "image"
    if head.startswith(b"%PDF-"): return "document"
    if len(head) >= 12 and head[4:8] == b"ftyp":
        return "image" if head[8:12] in (b"avif",b"avis",b"heic",b"heix",b"hevc",b"mif1") else "video"
    if head.startswith((b"ID3", b"fLaC", b"OggS")) or (head.startswith(b"RIFF") and head[8:12] == b"WAVE"):
        return "audio"
    return "other"


def entry_for(full, st=None):
    st = st or os.stat(full)
    rel = rel_of(full)
    name = os.path.basename(full)
    ext = os.path.splitext(name)[1].lower()
    return {
        "rel": rel,
        "name": name,
        "dir": os.path.dirname(rel),
        "size": st.st_size,
        "mtime": st.st_mtime,
        "type": detect_file_type(full, ext),
        "supported": ext in EXT_TYPE,
        "ext": ext,
        "cleaned": is_cleaned_name(name),
        "twin": False,
    }


def index_upsert(full):
    ent = entry_for(full)
    with INDEX_LOCK:
        items = INDEX["items"]
        items[ent["rel"]] = ent
        other = items.get(twin_rel(ent["rel"]))
        ent["twin"] = other is not None
        if other is not None:
            other["twin"] = True
    return ent


def index_remove(rel):
    with INDEX_LOCK:
        INDEX["items"].pop(rel, None)
        other = INDEX["items"].get(twin_rel(rel))
        if other is not None:
            other["twin"] = False


# ---------------------------------------------------------------- jobs

JOBS = {}
JOBS_LOCK = threading.Lock()


def new_job(kind, total=0):
    job = {
        "id": uuid.uuid4().hex[:12],
        "kind": kind,
        "status": "queued",
        "total": total,
        "done": 0,
        "failed": 0,
        "current": "",
        "message": "",
        "results": [],
        "created": time.time(),
        "started": None,
        "finished": None,
        "notify_status": "",
        "found": 0,
        "folders": 0,
        "skipped_dirs": 0,
        "_cancel": threading.Event(),
    }
    with JOBS_LOCK:
        JOBS[job["id"]] = job
        finished = sorted((j for j in JOBS.values() if j["finished"]), key=lambda j: j["finished"])
        while len(JOBS) > 40 and finished:
            JOBS.pop(finished.pop(0)["id"], None)
    return job


def finish_job(job, status, message=""):
    job["status"] = status
    job["message"] = message
    job["current"] = ""
    job["finished"] = time.time()


def public_job(job):
    data = {k: v for k, v in job.items() if not k.startswith("_")}
    data["results"] = list(job["results"])[-300:]
    data["results_total"] = len(job["results"])
    return data


def run_scan_job(job, include_hidden):
    job["status"] = "running"
    job["started"] = time.time()
    items = {}
    stack = [ROOT]
    folders = skipped = 0
    try:
        while stack:
            if job["_cancel"].is_set():
                break
            current = stack.pop()
            folders += 1
            job["folders"] = folders
            job["skipped_dirs"] = skipped
            job["current"] = os.path.relpath(current, ROOT) if current != ROOT else ""
            try:
                with os.scandir(current) as it:
                    entries = list(it)
            except OSError:
                skipped += 1
                continue
            for entry in entries:
                if entry.name.startswith(".") and not include_hidden:
                    continue
                try:
                    if entry.is_dir(follow_symlinks=False):
                        rel_dir = os.path.relpath(entry.path, ROOT)
                        if rel_dir not in SKIP_DIRS and not is_noise_path(rel_dir + "/"):
                            stack.append(entry.path)
                    elif entry.is_file(follow_symlinks=False):
                        rel_file = os.path.relpath(entry.path, ROOT)
                        if is_noise_path(rel_file):
                            continue
                        ent = entry_for(entry.path, entry.stat(follow_symlinks=False))
                        items[ent["rel"]] = ent
                        job["found"] = len(items)
                except OSError:
                    continue
        job["skipped_dirs"] = skipped
        if job["_cancel"].is_set():
            finish_job(job, "cancelled", "Scan cancelled; previous results kept.")
        elif folders == skipped:
            finish_job(job, "failed", explain(PermissionError()))
        else:
            for rel, ent in items.items():
                ent["twin"] = twin_rel(rel) in items
            with INDEX_LOCK:
                INDEX["items"] = items
                INDEX["scanned_at"] = time.time()
            finish_job(job, "done", f"Found {len(items)} files in {folders} folders.")
    except Exception as exc:
        app.logger.exception("scan failed")
        finish_job(job, "failed", explain(exc))


def run_clean_job(job, paths, mode, engine, notify, delete_original=False):
    try:
        with CLEAN_LOCK:
            job["status"] = "running"
            job["started"] = time.time()
            T = tools()
            written = []
            for rel in paths:
                if job["_cancel"].is_set():
                    break
                job["current"] = rel
                try:
                    res = clean_one(rel, mode, engine, T)
                    if res.get("dest"):
                        written.append(res.pop("dest"))
                    if res.get("status") == "ok" and delete_original and mode == "copy":
                        try:
                            original = resolve(rel)
                            os.remove(original)
                            index_remove(rel)
                            res["original_deleted"] = True
                        except Exception as delete_exc:
                            res["original_deleted"] = False
                            res.setdefault("notes", []).append(
                                "Cleaned copy was created, but the original could not be deleted: " + explain(delete_exc)
                            )
                except Exception as exc:
                    if not isinstance(exc, (ApiError, ToolError, OSError)):
                        app.logger.exception("clean failed for %s", rel)
                    res = {"rel": rel, "status": "error", "message": explain(exc)}
                job["results"].append(res)
                job["done"] += 1
                if res["status"] == "error":
                    job["failed"] += 1
            media_scan(written)
        ok = sum(1 for r in job["results"] if r["status"] == "ok")
        warned = sum(1 for r in job["results"] if r["status"] == "ok" and r.get("residual"))
        deleted_originals = sum(1 for r in job["results"] if r.get("original_deleted"))
        summary = f"{ok} cleaned, {job['failed']} failed"
        if deleted_originals:
            summary += f", {deleted_originals} originals deleted after cleanup"
        if warned:
            summary += f", {warned} with leftover tags"
        if job["_cancel"].is_set():
            finish_job(job, "cancelled", "Cancelled. " + summary)
        elif job["failed"] and job["failed"] == job["total"]:
            finish_job(job, "failed", summary)
        else:
            finish_job(job, "done", summary)
        if notify and IS_TERMUX:
            job["notify_status"] = send_notification("MetaClean finished", summary, job["id"])
    except Exception as exc:
        app.logger.exception("clean job crashed")
        finish_job(job, "failed", explain(exc))


def shred(path):
    size = os.path.getsize(path)
    with open(path, "r+b", buffering=0) as handle:
        left = size
        while left > 0:
            chunk = min(left, 1 << 20)
            handle.write(os.urandom(chunk))
            left -= chunk
        handle.flush()
        os.fsync(handle.fileno())


def run_delete_job(job, paths, secure):
    job["status"] = "running"
    job["started"] = time.time()
    removed = []
    freed = 0
    try:
        for rel in paths:
            if job["_cancel"].is_set():
                break
            job["current"] = rel
            try:
                full = resolve(rel)
                size = os.path.getsize(full)
                if secure and not os.path.islink(full):
                    shred(full)
                os.remove(full)
                index_remove(rel)
                removed.append(full)
                freed += size
                res = {"rel": rel, "status": "ok", "before": size, "message": "Deleted."}
            except Exception as exc:
                if not isinstance(exc, (ApiError, OSError)):
                    app.logger.exception("delete failed for %s", rel)
                res = {"rel": rel, "status": "error", "message": explain(exc)}
            job["results"].append(res)
            job["done"] += 1
            if res["status"] == "error":
                job["failed"] += 1
        media_scan(removed)
        summary = f"{len(removed)} deleted, {job['failed']} failed"
        if job["_cancel"].is_set():
            finish_job(job, "cancelled", "Cancelled. " + summary)
        elif job["failed"] and job["failed"] == job["total"]:
            finish_job(job, "failed", summary)
        else:
            finish_job(job, "done", summary)
    except Exception as exc:
        app.logger.exception("delete job crashed")
        finish_job(job, "failed", explain(exc))


# ---------------------------------------------------------------- thumbnails

_THUMB_SEM = threading.Semaphore(2)
_THUMB_FAIL = set()


def make_thumb(full, ftype):
    st = os.stat(full)
    key = hashlib.sha1(f"{full}|{st.st_size}|{st.st_mtime_ns}".encode("utf-8", "replace")).hexdigest()
    out = os.path.join(THUMB_DIR, key + ".jpg")
    if os.path.exists(out):
        return out
    if key in _THUMB_FAIL:
        return None
    os.makedirs(THUMB_DIR, exist_ok=True)
    tmp = os.path.join(THUMB_DIR, f"{key}.{secrets.token_hex(3)}.tmp.jpg")
    seeks = [["-ss", "1"], []] if ftype == "video" else [[]]
    with _THUMB_SEM:
        if os.path.exists(out):
            return out
        for seek in seeks:
            try:
                proc = run(
                    ["ffmpeg", "-nostdin", "-y", "-v", "error"] + seek
                    + ["-i", full, "-frames:v", "1", "-vf", "scale='min(320,iw)':-2", "-q:v", "6", "-update", "1", tmp],
                    timeout=45,
                )
            except ToolError:
                continue
            if proc.returncode == 0 and _usable(tmp):
                os.replace(tmp, out)
                return out
    if os.path.exists(tmp):
        os.remove(tmp)
    _THUMB_FAIL.add(key)
    return None


# ---------------------------------------------------------------- request guards

def valid_host_header():
    try:
        hostname = urlsplit("//" + (request.host or "")).hostname
        if not hostname:
            return False
        if hostname.lower() in ("localhost", socket.gethostname().lower()):
            return True
        address = ipaddress.ip_address(hostname)
        return address.is_private or address.is_loopback
    except ValueError:
        return False


def guard():
    if not valid_host_header():
        return jsonify(error="bad_host", message="Unexpected Host header."), 403
    try:
        client = ipaddress.ip_address(request.remote_addr or "")
        local_client = client.is_loopback
    except ValueError:
        client = None
        local_client = False

    if not local_client:
        with HOSTING_LOCK:
            enabled = HOSTING["enabled"]
            host_token = HOSTING["token"]
        client_private = bool(client and client.is_private and not client.is_link_local)
        if not enabled or not client_private or request.path not in ("/remote", "/remote/clean"):
            return jsonify(error="host_disabled", message="Remote access is disabled or this is not a private LAN client."), 403
        supplied = request.args.get("access", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), host_token.encode("utf-8")):
            return jsonify(error="host_access_denied", message="This sharing link is invalid or has expired."), 403
        if request.method not in ("GET", "POST"):
            return jsonify(error="method_not_allowed", message="Method not allowed."), 405
        if request.path == "/remote/clean" and request.method != "POST":
            return jsonify(error="method_not_allowed", message="Method not allowed."), 405
        if request.path == "/remote/clean" and request.mimetype != "multipart/form-data":
            return jsonify(error="bad_content_type", message="Upload must use multipart/form-data."), 415
        return None

    if request.path.startswith("/api/"):
        supplied = request.headers.get("X-MC-Token") or request.args.get("t", "")
        if not hmac.compare_digest(supplied.encode("utf-8"), TOKEN.encode("utf-8")):
            return jsonify(error="unauthorized", message="Invalid session token. Reload the page."), 401
        if request.method == "POST" and not request.is_json:
            return jsonify(error="bad_content_type", message="Expected application/json."), 415
    return None


@app.before_request
def register_request_guard():
    return guard()


@app.after_request
def add_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    if resp.mimetype == "text/html":
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self'; "
            "style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
        )
        resp.headers["Cache-Control"] = "no-store"
    elif resp.mimetype == "application/json":
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.errorhandler(ApiError)
def handle_api_error(exc):
    return jsonify(error=exc.code, message=str(exc)), exc.status


@app.errorhandler(ToolError)
def handle_tool_error(exc):
    return jsonify(error="tool_error", message=str(exc)), 502


@app.errorhandler(HTTPException)
def handle_http_error(exc):
    return jsonify(error=exc.name.lower().replace(" ", "_"), message=exc.description), exc.code


@app.errorhandler(Exception)
def handle_unexpected(exc):
    app.logger.exception("Unhandled error")
    return jsonify(error="internal_error", message=explain(exc)), 500


# ---------------------------------------------------------------- routes

@app.get("/")
def index():
    return render_template("index.html", token=TOKEN)


def interface_ipv4_addresses():
    """Read IPv4 addresses from active interfaces; useful where Android hostname DNS is limited."""
    if not sys.platform.startswith("linux"):
        return set()
    try:
        import fcntl
        import struct
        interfaces = socket.if_nameindex()
    except (ImportError, OSError, AttributeError):
        return set()

    found = set()
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            for _index, name in interfaces:
                try:
                    request = struct.pack("256s", name.encode("utf-8")[:15])
                    result = fcntl.ioctl(probe.fileno(), 0x8915, request)  # SIOCGIFADDR
                    ip = socket.inet_ntoa(result[20:24])
                    address = ipaddress.ip_address(ip)
                    if address.is_private and not address.is_loopback and not address.is_link_local:
                        found.add(ip)
                except (OSError, ValueError, UnicodeError):
                    continue
    except OSError:
        pass
    return found


def lan_ipv4_addresses():
    found = interface_ipv4_addresses()
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = item[4][0]
            addr = ipaddress.ip_address(ip)
            if addr.is_private and not addr.is_loopback and not addr.is_link_local:
                found.add(ip)
    except OSError:
        pass
    # UDP connect selects the active network route without sending payload data.
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("192.0.2.1", 9))
        ip = probe.getsockname()[0]
        addr = ipaddress.ip_address(ip)
        if addr.is_private and not addr.is_loopback and not addr.is_link_local:
            found.add(ip)
    except OSError:
        pass
    finally:
        probe.close()
    return sorted(found)


def set_termux_wake_lock(enabled):
    """Request/release Android's Termux wake lock without making it a host-mode dependency."""
    if not IS_TERMUX:
        return None
    command = "termux-wake-lock" if enabled else "termux-wake-unlock"
    executable = shutil.which(command)
    if not executable:
        return {
            "ok": False,
            "message": (
                "Termux:API command is unavailable. Install the Termux:API package and "
                "the matching Termux:API Android app. Keep Termux in the foreground while hosting."
            ),
        }
    try:
        proc = subprocess.run(
            [executable], capture_output=True, encoding="utf-8", errors="replace", timeout=20
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "message": f"{command} timed out; check the Termux:API app."}
    except OSError as exc:
        return {"ok": False, "message": f"{command} could not start: {exc}"}
    if proc.returncode != 0:
        detail = tail(proc.stderr or proc.stdout, 180)
        return {
            "ok": False,
            "message": detail or f"{command} failed. Check that the Termux:API app is installed and matches the Termux installation source.",
        }
    return {
        "ok": True,
        "message": (
            "Android wake lock is active while LAN hosting is enabled. This can increase battery use."
            if enabled else "Android wake lock released."
        ),
    }


def host_status():
    with HOSTING_LOCK:
        enabled = HOSTING["enabled"]
        key = HOSTING["token"]
        wake_lock = HOSTING.get("wake_lock")
    urls = [f"http://{ip}:{PORT}/remote?access={key}" for ip in lan_ipv4_addresses()] if enabled else []
    return {
        "enabled": enabled,
        "urls": urls,
        "scope": "private local network only",
        "wake_lock": wake_lock if IS_TERMUX else None,
    }


def cleanup_stale_remote_temp():
    """Remove abandoned upload workspaces left by an earlier stopped/crashed process."""
    try:
        names = os.listdir(WORK_BASE)
    except OSError:
        return
    for name in names:
        if not name.startswith("metaclean-remote-"):
            continue
        folder = os.path.join(WORK_BASE, name)
        if not os.path.isdir(folder):
            continue
        owner_file = os.path.join(folder, ".metaclean-owner")
        try:
            with open(owner_file, "r", encoding="ascii") as handle:
                owner_pid = int(handle.read().strip())
        except (OSError, ValueError):
            shutil.rmtree(folder, ignore_errors=True)
            continue
        if owner_pid == os.getpid():
            continue
        try:
            os.kill(owner_pid, 0)
        except ProcessLookupError:
            shutil.rmtree(folder, ignore_errors=True)
        except PermissionError:
            continue
        except OSError:
            shutil.rmtree(folder, ignore_errors=True)


@app.get("/remote")
def remote_portal():
    with HOSTING_LOCK:
        enabled = HOSTING["enabled"]
        key = HOSTING["token"]
    access = request.args.get("access", "")
    if not enabled or not hmac.compare_digest(access.encode("utf-8"), key.encode("utf-8")):
        raise ApiError("Host sharing is disabled or this link has expired.", 403, "host_access_denied")
    return render_template("remote.html", access=access, max_files=MAX_REMOTE_FILES, max_mb=MAX_UPLOAD_BYTES // (1024 * 1024))


@app.post("/remote/clean")
def remote_clean():
    with HOSTING_LOCK:
        enabled = HOSTING["enabled"]
        key = HOSTING["token"]
    if not enabled or not hmac.compare_digest(request.args.get("access", "").encode("utf-8"), key.encode("utf-8")):
        raise ApiError("Host sharing is disabled or this link has expired.", 403, "host_access_denied")

    uploads = [item for item in request.files.getlist("files") if item and item.filename]
    if not uploads:
        raise ApiError("Choose at least one file to clean.", 400, "no_uploads")
    if len(uploads) > MAX_REMOTE_FILES:
        raise ApiError(f"Upload no more than {MAX_REMOTE_FILES} files at once.", 400, "too_many_uploads")
    engine = request.form.get("engine", "auto")
    if engine not in ENGINES:
        raise ApiError("Invalid cleaning engine.", 400, "bad_engine")

    os.makedirs(WORK_BASE, exist_ok=True)
    temp_dir = tempfile.mkdtemp(prefix="metaclean-remote-", dir=WORK_BASE)
    with open(os.path.join(temp_dir, ".metaclean-owner"), "w", encoding="ascii") as owner:
        owner.write(str(os.getpid()))
    outputs = []
    T = tools()
    try:
        for number, upload in enumerate(uploads, 1):
            safe_name = secure_filename(os.path.basename(upload.filename)) or f"upload-{number}"
            ext = os.path.splitext(safe_name)[1].lower()
            ftype = EXT_TYPE.get(ext)
            if not ftype:
                raise ApiError(f"{safe_name}: no safe cleaner is registered for this file type.", 415, "unsupported_type")
            source = os.path.join(temp_dir, f"input-{number}{ext}")
            upload.save(source)
            if not _usable(source):
                raise ApiError(f"{safe_name}: file is empty or could not be saved.", 400, "empty_upload")
            plan = plan_for(ftype, ext, engine, T)
            check_plan(plan, ext, T)
            work = tempfile.mkdtemp(prefix=f"work-{number}-", dir=temp_dir)
            try:
                current = source
                notes = []
                for step_index, step_name in enumerate(plan):
                    current = STEPS[step_name](current, work, ext, ftype, step_index, notes)
                output_name = f"{number:02d}_{os.path.splitext(safe_name)[0]}.cleaned{ext}"
                output_path = os.path.join(temp_dir, output_name)
                shutil.copyfile(current, output_path)
                residual = verify(output_path, T)
                outputs.append((output_path, output_name, {
                    "original": safe_name, "engines": plan, "notes": notes,
                    "verified": residual is not None, "residual": residual or [],
                }))
            finally:
                shutil.rmtree(work, ignore_errors=True)

        archive_path = os.path.join(temp_dir, "MetaClean-cleaned.zip")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for output_path, output_name, _info in outputs:
                archive.write(output_path, arcname=output_name)
        response = send_file(archive_path, mimetype="application/zip", as_attachment=True, download_name="MetaClean-cleaned.zip", max_age=0)
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.call_on_close(lambda: shutil.rmtree(temp_dir, ignore_errors=True))
        return response
    except Exception:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


@app.get("/api/status")
def api_status():
    T = tools(force=request.args.get("refresh") == "1")
    st = storage_state()
    banners = []
    if not st["ok"]:
        banners.append({"level": "error", "text": st["reason"]})
    elif not st["writable"]:
        banners.append(
            {"level": "warn", "text": "The configured file root is read-only. Inspection works, but cleaning and deletion need write access."}
        )
    if not T["exiftool"]["available"]:
        banners.append(
            {"level": "error", "text": f"ExifTool is unavailable ({T['exiftool']['error']}). Rerun the platform installer or add ExifTool to PATH."}
        )
    if not T["mat2"]["available"] and not IS_TERMUX:
        banners.append(
            {
                "level": "warn",
                "text": f"mat2 is unavailable ({T['mat2']['error']}). Built-in fallbacks will be used: exiftool for images, ffmpeg for audio/video, qpdf and an Office scrubber for documents.",
            }
        )
    if not T["ffmpeg"]["available"]:
        banners.append(
            {"level": "warn", "text": "FFmpeg is missing: thumbnails and audio/video fallback cleaning are unavailable. Install FFmpeg and ensure it is on PATH."}
        )
    if IS_TERMUX and not T["termux-notification"]["available"]:
        banners.append(
            {"level": "warn", "text": "termux-notification is missing: install the termux-api package and the Termux:API app to get completion notifications."}
        )
    return jsonify(
        root=ROOT,
        port=PORT,
        platform={"name": PLATFORM_NAME, "termux": IS_TERMUX, "windows": IS_WINDOWS, "linux": IS_LINUX},
        host=host_status(),
        storage=st,
        tools=T,
        banners=banners,
        indexed=len(INDEX["items"]),
        scanned_at=INDEX["scanned_at"],
        monitor_enabled=MONITOR["enabled"],
    )


def _filter_ok(flt, ent):
    if flt == "originals":
        return not ent["cleaned"]
    if flt == "cleaned":
        return ent["cleaned"]
    if flt == "withcopy":
        return not ent["cleaned"] and ent["twin"]
    if flt == "nocopy":
        return not ent["cleaned"] and not ent["twin"]
    return True


@app.get("/api/files")
def api_files():
    args = request.args
    ftype = args.get("type", "all")
    query = args.get("q", "").strip().lower()
    flt = args.get("filter", "all")
    sort = args.get("sort", "date")
    reverse = args.get("order", "desc") != "asc"
    offset = int_arg("offset", 0, 0, 10_000_000)
    limit = int_arg("limit", 60, 1, 200)
    with INDEX_LOCK:
        items = list(INDEX["items"].values())
        scanned_at = INDEX["scanned_at"]
    base = [e for e in items if (not query or query in e["rel"].lower()) and _filter_ok(flt, e)]
    counts = {"all": 0, "image": 0, "video": 0, "audio": 0, "document": 0, "other": 0}
    for ent in base:
        counts[ent["type"]] += 1
    counts["all"] = sum(counts[k] for k in ("image", "video", "audio", "document"))
    # Keep unknown and non-media files available in the explicit Other tab.
    chosen = ([e for e in base if e["type"] != "other"] if ftype == "all"
              else [e for e in base if e["type"] == ftype])
    if sort == "name":
        chosen.sort(key=lambda e: e["name"].lower(), reverse=reverse)
    elif sort == "size":
        chosen.sort(key=lambda e: e["size"], reverse=reverse)
    else:
        chosen.sort(key=lambda e: e["mtime"], reverse=reverse)
    if args.get("ids") == "1":
        sel = [
            {"rel": e["rel"], "name": e["name"], "size": e["size"], "twin": e["twin"], "cleaned": e["cleaned"]}
            for e in chosen if e["supported"]
        ]
        return jsonify(sel=sel)
    return jsonify(
        total=len(chosen),
        total_size=sum(e["size"] for e in chosen),
        counts=counts,
        items=chosen[offset : offset + limit],
        scanned_at=scanned_at,
    )


@app.get("/api/metadata")
def api_metadata():
    full = resolve(request.args.get("path", ""))
    T = tools()
    ext = os.path.splitext(full)[1].lower()
    ftype = entry_for(full)["type"]
    if ftype == "other":
        raise ApiError("This file is not recognised as a media or document format.", 415, "unsupported_type")
    if not (T["exiftool"]["available"] or T["mat2"]["available"]):
        raise ApiError("No inspection tool is available. Install exiftool: pkg install exiftool", 503, "missing_tool")
    rows, notes, engines = [], [], []
    if T["exiftool"]["available"]:
        try:
            rows += exif_rows(full)
            engines.append("exiftool")
        except ToolError as exc:
            notes.append(str(exc))
    if T["mat2"]["available"]:
        try:
            mat_rows, note = mat2_show(full)
            rows += mat_rows
            engines.append("mat2")
            if note:
                notes.append(note)
        except ToolError as exc:
            notes.append(str(exc))
    streams = []
    if ftype in ("video", "audio") and T["ffprobe"]["available"]:
        try:
            streams = probe_streams(full)
        except ToolError as exc:
            notes.append(str(exc))
    tags = collect_tags(rows)
    summary = {cat: 0 for cat in CATEGORIES}
    for tag in tags:
        summary[tag["category"]] += 1
    summary["total"] = len(tags)
    st = os.stat(full)
    return jsonify(
        path=rel_of(full),
        size=st.st_size,
        mtime=st.st_mtime,
        type=ftype,
        engines=engines,
        summary=summary,
        tags=tags,
        streams=streams,
        hidden_streams=sum(1 for s in streams if s["hidden"]),
        notes=notes,
    )


@app.get("/api/file")
def api_file():
    full = resolve(request.args.get("path", ""))
    mime = mimetypes.guess_type(full)[0] or "application/octet-stream"
    return send_file(full, mimetype=mime, conditional=True, max_age=0)


@app.get("/api/thumb")
def api_thumb():
    full = resolve(request.args.get("path", ""))
    ftype = entry_for(full)["type"]
    if ftype not in ("image", "video") or not tools()["ffmpeg"]["available"]:
        raise ApiError("No thumbnail available.", 404, "no_thumb")
    thumb = make_thumb(full, ftype)
    if not thumb:
        raise ApiError("No thumbnail available.", 404, "no_thumb")
    return send_file(thumb, mimetype="image/jpeg", max_age=86400)


@app.post("/api/scan")
def api_scan():
    body = request.get_json(silent=True) or {}
    state = storage_state()
    if not state["ok"]:
        raise ApiError(state["reason"], 503, "storage_unavailable")
    with JOBS_LOCK:
        for existing in JOBS.values():
            if existing["kind"] == "scan" and existing["status"] in ("queued", "running"):
                return jsonify(job_id=existing["id"], reused=True)
    job = new_job("scan")
    POOL.submit(run_scan_job, job, bool(body.get("include_hidden")))
    return jsonify(job_id=job["id"], reused=False)


@app.post("/api/clean")
def api_clean():
    body = request.get_json(silent=True) or {}
    paths = clean_paths(body.get("paths"))
    mode = body.get("mode", "copy")
    engine = body.get("engine", "auto")
    if mode not in MODES:
        raise ApiError("Invalid mode. Use 'copy' or 'replace'.", 400, "bad_mode")
    if engine not in ENGINES:
        raise ApiError("Invalid engine.", 400, "bad_engine")
    T = tools()
    if not any(T[name]["available"] for name in ("exiftool", "mat2", "ffmpeg")):
        raise ApiError("No cleaning tool is available. Run setup.sh to install exiftool and ffmpeg.", 503, "missing_tool")
    state = storage_state()
    if not state["ok"]:
        raise ApiError(state["reason"], 503, "storage_unavailable")
    if not state["writable"]:
        raise ApiError("Shared storage is read-only for Termux.", 403, "read_only")
    delete_original = bool(body.get("delete_original", False))
    if delete_original and mode != "copy":
        raise ApiError("Delete original after cleanup is only available when saving a cleaned copy.", 400, "bad_delete_original_mode")
    job = new_job("clean", len(paths))
    POOL.submit(run_clean_job, job, paths, mode, engine, bool(body.get("notify", True)), delete_original)
    return jsonify(job_id=job["id"])


def run_all_job(job, include_hidden, notify=True, delete_original=False):
    """Inventory all accessible files, then clean every supported original as copies."""
    try:
        scan = new_job("scan")
        run_scan_job(scan, include_hidden)
        if scan["status"] != "done":
            finish_job(job, scan["status"], scan["message"])
            return
        with INDEX_LOCK:
            paths = [e["rel"] for e in INDEX["items"].values()
                     if e.get("supported") and not e.get("cleaned")
                     and not os.path.exists(os.path.join(ROOT, twin_rel(e["rel"]))) ]
        job["total"] = len(paths)
        if not paths:
            finish_job(job, "done", "Inventory complete. No supported original files need cleaning.")
            if notify and IS_TERMUX:
                job["notify_status"] = send_notification("MetaClean finished", job["message"], job["id"])
            return
        run_clean_job(job, paths, "copy", "auto", notify, delete_original)
    except Exception as exc:
        app.logger.exception("run-all job failed")
        finish_job(job, "failed", explain(exc))


MONITOR = {"enabled": False, "thread": None, "interval": 30, "seen": {}}
MONITOR_LOCK = threading.Lock()
MONITOR_CONFIG = os.path.join(DATA_DIR, "monitor.json")

def save_monitor_setting(enabled):
    os.makedirs(DATA_DIR, exist_ok=True)
    temp = MONITOR_CONFIG + ".tmp"
    with open(temp, "w", encoding="utf-8") as handle:
        json.dump({"enabled": bool(enabled)}, handle)
    os.replace(temp, MONITOR_CONFIG)

def monitor_snapshot():
    snapshot = {}
    for current, dirs, files in os.walk(ROOT, followlinks=False):
        dirs[:] = [d for d in dirs if os.path.relpath(os.path.join(current, d), ROOT) not in SKIP_DIRS
                   and not is_noise_path(os.path.relpath(os.path.join(current, d), ROOT) + "/")]
        for name in files:
            rel = os.path.relpath(os.path.join(current, name), ROOT)
            if is_noise_path(rel) or os.path.splitext(name)[1].lower() not in EXT_TYPE or is_cleaned_name(name):
                continue
            full = os.path.join(current, name)
            try:
                st = os.stat(full, follow_symlinks=False)
                snapshot[rel_of(full)] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    return snapshot

def monitor_loop():
    while True:
        with MONITOR_LOCK:
            if not MONITOR["enabled"]:
                return
            interval = MONITOR["interval"]
        time.sleep(interval)
        with MONITOR_LOCK:
            if not MONITOR["enabled"]:
                return
        try:
            discovered = []
            for current, dirs, files in os.walk(ROOT, followlinks=False):
                dirs[:] = [d for d in dirs if os.path.relpath(os.path.join(current, d), ROOT) not in SKIP_DIRS
                           and not is_noise_path(os.path.relpath(os.path.join(current, d), ROOT) + "/")]
                for name in files:
                    full = os.path.join(current, name)
                    ext = os.path.splitext(name)[1].lower()
                    if is_noise_path(os.path.relpath(full, ROOT)) or ext not in EXT_TYPE or is_cleaned_name(name):
                        continue
                    try:
                        st = os.stat(full, follow_symlinks=False)
                        rel = rel_of(full)
                        sig = (st.st_size, st.st_mtime_ns)
                        with MONITOR_LOCK:
                            old = MONITOR["seen"].get(rel)
                            MONITOR["seen"][rel] = sig
                        if old is None or old != sig:
                            discovered.append(rel)
                    except OSError:
                        continue
            if discovered:
                job = new_job("monitor-clean", len(discovered))
                POOL.submit(run_clean_job, job, discovered, "copy", "auto", True)
        except Exception:
            app.logger.exception("monitor cycle failed")


@app.post("/api/run-all")
def api_run_all():
    body = request.get_json(silent=True) or {}
    state = storage_state()
    if not state["ok"] or not state["writable"]:
        raise ApiError(state.get("reason") or "Shared storage is read-only.", 503, "storage_unavailable")
    with JOBS_LOCK:
        for existing in JOBS.values():
            if existing["kind"] == "run-all" and existing["status"] in ("queued", "running"):
                return jsonify(job_id=existing["id"], reused=True)
    delete_original = bool(body.get("delete_original", False))
    job = new_job("run-all")
    POOL.submit(run_all_job, job, bool(body.get("include_hidden", True)), bool(body.get("notify", True)), delete_original)
    return jsonify(job_id=job["id"], reused=False)


@app.post("/api/host")
def api_host():
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled"))
    with HOSTING_LOCK:
        if enabled:
            HOSTING["enabled"] = True
            HOSTING["token"] = secrets.token_urlsafe(32)
        else:
            HOSTING["enabled"] = False
            HOSTING["token"] = ""

    # Android can suspend background work when the screen turns off. Request
    # Termux's wake lock only for the period in which the user has opted into hosting.
    wake_lock = set_termux_wake_lock(enabled) if IS_TERMUX else None
    with HOSTING_LOCK:
        HOSTING["wake_lock"] = wake_lock
    return jsonify(host=host_status())


@app.post("/api/monitor")
def api_monitor():
    body = request.get_json(silent=True) or {}
    enabled = bool(body.get("enabled"))
    with MONITOR_LOCK:
        MONITOR["enabled"] = enabled
        if enabled:
            if not MONITOR["seen"]:
                MONITOR["seen"] = monitor_snapshot()
            if MONITOR["thread"] is None or not MONITOR["thread"].is_alive():
                MONITOR["thread"] = threading.Thread(target=monitor_loop, name="metaclean-monitor", daemon=True)
                MONITOR["thread"].start()
    save_monitor_setting(enabled)
    return jsonify(enabled=MONITOR["enabled"], interval=MONITOR["interval"])


@app.post("/api/delete")
def api_delete():
    body = request.get_json(silent=True) or {}
    if body.get("confirm") is not True:
        raise ApiError("Deletion must be confirmed.", 400, "not_confirmed")
    paths = clean_paths(body.get("paths"))
    job = new_job("delete", len(paths))
    POOL.submit(run_delete_job, job, paths, bool(body.get("secure")))
    return jsonify(job_id=job["id"])


@app.get("/api/jobs")
def api_jobs():
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda j: j["created"], reverse=True)[:20]
    return jsonify(jobs=[public_job(j) for j in jobs])


@app.get("/api/jobs/<job_id>")
def api_job(job_id):
    job = JOBS.get(job_id)
    if not job:
        raise ApiError("Unknown job id.", 404, "no_job")
    return jsonify(public_job(job))


@app.post("/api/jobs/<job_id>/cancel")
def api_job_cancel(job_id):
    job = JOBS.get(job_id)
    if not job:
        raise ApiError("Unknown job id.", 404, "no_job")
    job["_cancel"].set()
    return jsonify(ok=True)


# ---------------------------------------------------------------- entry point

def main():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(ROOT, exist_ok=True)
    os.makedirs(WORK_BASE, exist_ok=True)
    # Hosting is always off after a process restart; clear any stale Android lock.
    if IS_TERMUX:
        set_termux_wake_lock(False)
    cleanup_stale_remote_temp()
    found = tools(force=True)
    try:
        with open(MONITOR_CONFIG, "r", encoding="utf-8") as handle:
            saved_monitor = bool(json.load(handle).get("enabled"))
        if saved_monitor and storage_state()["ok"]:
            MONITOR["seen"] = monitor_snapshot()
            MONITOR["enabled"] = True
            MONITOR["thread"] = threading.Thread(target=monitor_loop, name="metaclean-monitor", daemon=True)
            MONITOR["thread"].start()
    except (OSError, ValueError, TypeError):
        pass
    print(f"MetaClean root : {ROOT}")
    for name, info in found.items():
        state = info["version"] or "ok" if info["available"] else f"missing ({info['error']})"
        print(f"  {name:<20} {state}")
    print(f"Listening on http://127.0.0.1:{PORT} (LAN host mode is opt-in)")
    try:
        from waitress import serve
    except ImportError:
        app.run(host=BIND_HOST, port=PORT, threaded=True)
        return
    try:
        serve(app, host=BIND_HOST, port=PORT, threads=8, ident="metaclean")
    except OSError as exc:
        print(f"Cannot start server on port {PORT}: {exc.strerror or exc}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
