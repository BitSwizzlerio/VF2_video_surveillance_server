#!/usr/bin/env python3
"""Read-only HTTP API for browsing and streaming VF2 surveillance footage.

Standard-library only (Python 3.7+), so it runs on the VisionFive 2's stock
Debian without extra packages. It exposes the recorded footage that the shell
scripts write to ``BASE_DIR`` (default ``/mnt/nvme``) over a small JSON + byte
API consumed by the desktop frontend.

Endpoints
---------
    GET /api/health
        -> { "status": "ok" }

    GET /api/cameras
        -> [{ "id": "cam1", "name": "cam1", "ip": "192.168.0.101" }, ...]

    GET /api/cameras/{id}/segments?day=YYYY-MM-DD
        -> [{ "start": "2024-06-15T13:30:00",
               "durationSeconds": 900,
               "source": "LOOSE_MP4" | "ARCHIVED",
               "resourceId": "cam1/Sat/13/cam1_20240615_133000.mp4" }, ...]

    GET /api/segments/{resourceId}/stream      (supports HTTP Range requests)
        -> video/mp4

Recent footage is stored as loose ``.mp4`` files; older footage is rolled into
per-hour ``.tar.gz`` archives by ``pave.sh``. Archived segments are extracted to
a local cache on first request so the client always receives plain mp4 bytes.

Configuration (environment variables override config.sh / defaults):
    VF2_BASE_DIR   storage root            (default: parsed from config.sh, else /mnt/nvme)
    VF2_CAMS_CONF  camera list file        (default: cams.conf next to this script)
    VF2_DURATION   nominal segment seconds (default: parsed from config.sh, else 900)
    VF2_HOST       bind address            (default: 0.0.0.0)
    VF2_PORT       bind port               (default: 8080)
    VF2_CACHE_DIR  archive extraction cache(default: <tmp>/vf2_api_cache)
    VF2_TOKEN      if set, require 'Authorization: Bearer <token>' on every request
"""

from __future__ import annotations

import json
import os
import re
import sys
import tarfile
import tempfile
import threading
import urllib.parse
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# Matches recorder filenames like "cam1_20240615_133000.mp4".
_FILE_RE = re.compile(r"_(?P<date>\d{8})_(?P<time>\d{6})\.mp4$")


def _parse_config_value(text: str, key: str):
    """Pull a simple KEY="value" / KEY=value assignment out of config.sh."""
    m = re.search(rf'^\s*{key}=["\']?([^"\'#\n]+)', text, re.MULTILINE)
    return m.group(1).strip() if m else None


def _load_config():
    base_dir = "/mnt/nvme"
    duration = 900
    config_sh = os.path.join(SCRIPT_DIR, "config.sh")
    if os.path.isfile(config_sh):
        try:
            with open(config_sh, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            base_dir = _parse_config_value(text, "BASE_DIR") or base_dir
            dur = _parse_config_value(text, "DURATION")
            if dur and dur.isdigit():
                duration = int(dur)
        except OSError:
            pass
    return base_dir, duration


_BASE_DIR_DEFAULT, _DURATION_DEFAULT = _load_config()

BASE_DIR = os.path.realpath(os.environ.get("VF2_BASE_DIR", _BASE_DIR_DEFAULT))
CAMS_CONF = os.environ.get("VF2_CAMS_CONF", os.path.join(SCRIPT_DIR, "cams.conf"))
DURATION = int(os.environ.get("VF2_DURATION", _DURATION_DEFAULT))
HOST = os.environ.get("VF2_HOST", "0.0.0.0")
PORT = int(os.environ.get("VF2_PORT", "8080"))
CACHE_DIR = os.environ.get("VF2_CACHE_DIR", os.path.join(tempfile.gettempdir(), "vf2_api_cache"))
TOKEN = os.environ.get("VF2_TOKEN", "")

_extract_lock = threading.Lock()


def list_cameras():
    """Read cams.conf -> [{id, name, ip}]. Blank/comment lines are ignored."""
    cameras = []
    if not os.path.isfile(CAMS_CONF):
        return cameras
    with open(CAMS_CONF, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            cam_id = parts[0]
            ip = parts[1] if len(parts) > 1 else ""
            name = parts[2] if len(parts) > 2 else cam_id
            cameras.append({"id": cam_id, "name": name, "ip": ip})
    return cameras


def _parse_start(filename: str):
    m = _FILE_RE.search(filename)
    if not m:
        return None
    try:
        return datetime.strptime(m.group("date") + m.group("time"), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def _tar_mp4_members(tar_path: str):
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            for member in tar.getmembers():
                if member.isfile() and member.name.endswith(".mp4"):
                    yield os.path.basename(member.name)
    except (tarfile.TarError, OSError):
        return


def _index_path(archive_path: str) -> str:
    return archive_path + ".idx"


def _read_index(archive_path: str):
    """Return cached mp4 basenames from the sidecar .idx, or None if stale/missing.

    Reading a per-hour .tar.gz of MJPEG footage means decompressing hundreds of
    megabytes just to learn the filenames, which is far too slow on the VF2. The
    recorder (pave.sh) writes a tiny "<archive>.idx" listing alongside each
    archive; we read that instead. ``api.py --reindex`` backfills existing ones.
    """
    idx = _index_path(archive_path)
    try:
        if os.path.isfile(idx) and os.path.getmtime(idx) >= os.path.getmtime(archive_path):
            with open(idx, "r", encoding="utf-8", errors="replace") as f:
                return [line.strip() for line in f if line.strip()]
    except OSError:
        pass
    return None


def _build_index(archive_path: str):
    """Decompress an archive once to list its mp4s and cache the result in .idx."""
    names = list(_tar_mp4_members(archive_path))
    try:
        with open(_index_path(archive_path), "w", encoding="utf-8") as f:
            for name in names:
                f.write(name + "\n")
    except OSError:
        pass
    return names


def _archive_mp4_names(archive_path: str):
    """mp4 basenames in an archive, preferring the fast .idx sidecar."""
    names = _read_index(archive_path)
    if names is None:
        names = _build_index(archive_path)
    return names


def list_segments(cam_id: str, day: str):
    """List segments for a camera on a calendar day (YYYY-MM-DD)."""
    try:
        target = datetime.strptime(day, "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("day must be YYYY-MM-DD")

    # The recorder stores by weekday abbreviation (Mon, Tue, ...). The exact
    # date in each filename is used to filter, so this is correct even though
    # weekday folders are reused across weeks.
    dow = target.strftime("%a")
    cam_dir = os.path.join(BASE_DIR, cam_id, dow)
    segments = []
    if not os.path.isdir(cam_dir):
        return segments

    for hour in sorted(os.listdir(cam_dir)):
        hour_dir = os.path.join(cam_dir, hour)
        if not os.path.isdir(hour_dir):
            continue
        for name in sorted(os.listdir(hour_dir)):
            full = os.path.join(hour_dir, name)
            if name.endswith(".mp4") and os.path.isfile(full):
                start = _parse_start(name)
                if start and start.date() == target:
                    segments.append(_segment(cam_id, dow, hour, name, start, "LOOSE_MP4"))
            elif name.endswith(".tar.gz") and os.path.isfile(full):
                for member in _archive_mp4_names(full):
                    start = _parse_start(member)
                    if start and start.date() == target:
                        segments.append(_segment(cam_id, dow, hour, member, start, "ARCHIVED"))

    segments.sort(key=lambda s: s["start"])
    return segments


def _segment(cam_id, dow, hour, name, start, source):
    return {
        "start": start.isoformat(timespec="seconds"),
        "durationSeconds": DURATION,
        "source": source,
        "resourceId": f"{cam_id}/{dow}/{hour}/{name}",
    }


def _safe_resolve(rel: str):
    """Resolve a resourceId under BASE_DIR, rejecting path traversal."""
    rel = urllib.parse.unquote(rel).lstrip("/")
    full = os.path.realpath(os.path.join(BASE_DIR, rel))
    if full != BASE_DIR and not full.startswith(BASE_DIR + os.sep):
        raise PermissionError("path escapes storage root")
    return full


def _extract_from_archive(parent_dir: str, basename: str):
    """Extract a single mp4 from any .tar.gz in parent_dir into the cache."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(CACHE_DIR, basename)
    if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
        return cache_path
    if not os.path.isdir(parent_dir):
        return None
    with _extract_lock:
        if os.path.isfile(cache_path) and os.path.getsize(cache_path) > 0:
            return cache_path
        for archive in sorted(os.listdir(parent_dir)):
            if not archive.endswith(".tar.gz"):
                continue
            archive_path = os.path.join(parent_dir, archive)
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    for member in tar.getmembers():
                        if member.isfile() and os.path.basename(member.name) == basename:
                            src = tar.extractfile(member)
                            if src is None:
                                continue
                            tmp = cache_path + ".part"
                            with open(tmp, "wb") as out:
                                while True:
                                    chunk = src.read(64 * 1024)
                                    if not chunk:
                                        break
                                    out.write(chunk)
                            os.replace(tmp, cache_path)
                            return cache_path
            except (tarfile.TarError, OSError):
                continue
    return None


class Handler(BaseHTTPRequestHandler):
    server_version = "VF2Api/1.0"
    protocol_version = "HTTP/1.1"

    # --- helpers ---------------------------------------------------------
    def _authorized(self):
        if not TOKEN:
            return True
        auth = self.headers.get("Authorization", "")
        return auth == f"Bearer {TOKEN}"

    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _send_error_json(self, status, message):
        self._send_json({"error": message}, status=status)

    def _serve_file_range(self, path, content_type="video/mp4"):
        try:
            size = os.path.getsize(path)
        except OSError:
            self._send_error_json(404, "not found")
            return

        start, end, status = 0, size - 1, 200
        range_header = self.headers.get("Range")
        if range_header and range_header.startswith("bytes="):
            spec = range_header[len("bytes="):].split(",")[0].strip()
            s, _, e = spec.partition("-")
            try:
                if s == "":
                    start = max(0, size - int(e))
                else:
                    start = int(s)
                    end = int(e) if e else size - 1
            except ValueError:
                start, end = 0, size - 1
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            end = min(end, size - 1)
            status = 206

        length = end - start + 1
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(length))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        if self.command == "HEAD":
            return

        remaining = length
        with open(path, "rb") as f:
            f.seek(start)
            while remaining > 0:
                chunk = f.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                remaining -= len(chunk)

    # --- routing ---------------------------------------------------------
    def do_GET(self):
        if not self._authorized():
            self._send_error_json(401, "unauthorized")
            return

        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        try:
            if path == "/api/health":
                self._send_json({"status": "ok"})
                return

            if path == "/api/cameras":
                self._send_json(list_cameras())
                return

            m = re.fullmatch(r"/api/cameras/([^/]+)/segments", path)
            if m:
                cam_id = urllib.parse.unquote(m.group(1))
                day = query.get("day", [""])[0]
                if not day:
                    self._send_error_json(400, "missing 'day' parameter")
                    return
                self._send_json(list_segments(cam_id, day))
                return

            if path.startswith("/api/segments/") and path.endswith("/stream"):
                rel = path[len("/api/segments/"):-len("/stream")]
                self._serve_stream(rel)
                return

            self._send_error_json(404, "not found")
        except PermissionError:
            self._send_error_json(403, "forbidden")
        except ValueError as e:
            self._send_error_json(400, str(e))
        except Exception as e:  # noqa: BLE001 - report, don't crash the server
            self._send_error_json(500, f"internal error: {e}")

    def do_HEAD(self):
        self.do_GET()

    def _serve_stream(self, rel):
        path = _safe_resolve(rel)
        if os.path.isfile(path):
            self._serve_file_range(path)
            return
        # Not a loose file: try extracting it from a per-hour archive.
        extracted = _extract_from_archive(os.path.dirname(path), os.path.basename(path))
        if extracted:
            self._serve_file_range(extracted)
        else:
            self._send_error_json(404, "segment not found")

    def log_message(self, fmt, *args):
        # Compact single-line logging to stdout.
        print("%s - %s" % (self.address_string(), fmt % args))


def reindex():
    """Backfill a .idx sidecar for every archive that lacks an up-to-date one.

    Run this once on the VF2 after deploying (``python3 api.py --reindex``) so the
    first segment listing for older footage is instant instead of decompressing
    gigabytes of archives over HTTP.
    """
    built = 0
    skipped = 0
    for root, _dirs, files in os.walk(BASE_DIR):
        for name in files:
            if not name.endswith(".tar.gz"):
                continue
            archive_path = os.path.join(root, name)
            if _read_index(archive_path) is not None:
                skipped += 1
                continue
            _build_index(archive_path)
            built += 1
            print(f"indexed {archive_path}")
    print(f"Reindex complete: {built} built, {skipped} already current")


def main():
    if "--reindex" in sys.argv:
        reindex()
        return
    os.makedirs(CACHE_DIR, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"VF2 API serving {BASE_DIR} on http://{HOST}:{PORT}  "
          f"(cameras: {CAMS_CONF}, token: {'on' if TOKEN else 'off'})")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("Shutting down")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
