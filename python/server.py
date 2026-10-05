#!/usr/bin/env python3
"""
Ai-Lens — static site + news API.

Standard library only (the optional Claude enrichment needs `anthropic`).

    GET  /api/health          liveness probe
    GET  /api/config          public runtime config
    GET  /api/news?days=N     clustered stories, newest first
    POST /api/refresh         re-fetch every feed now (rate-limited)

Configuration comes from .env (see .env.example / .env.server.example).
All front-end URLs are relative, and a leading BASE_PATH is stripped, so the
site also works mounted under a prefix such as http://localhost:8080/ai-lens/.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import posixpath
import re
from urllib.parse import parse_qs, unquote, urlsplit

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))


def load_env(path: Path) -> None:
    """Minimal .env reader — os.environ always wins, so the shell can override."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_env(ROOT / ".env")


def _path(value: str) -> Path:
    p = Path(value)
    return p if p.is_absolute() else (ROOT / p).resolve()


ENV_TYPE = os.environ.get("ENV_TYPE", "local").lower()
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8420"))
BASE_PATH = os.environ.get("BASE_PATH", "").rstrip("/")
DATA_PATH = _path(os.environ.get("DATA_PATH", "./data"))
LOG_PATH = _path(os.environ.get("LOG_PATH", "./logs"))
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ar")
REFRESH_MINUTES = max(5, int(os.environ.get("REFRESH_MINUTES", "720")))
RETENTION_DAYS = max(1, int(os.environ.get("RETENTION_DAYS", "45")))
ENRICH_MODEL = os.environ.get("ENRICH_MODEL", "claude-opus-5-5")
ENRICH_MAX = int(os.environ.get("ENRICH_MAX_PER_REFRESH", "120"))

DATA_PATH.mkdir(parents=True, exist_ok=True)
LOG_PATH.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(name)s  %(message)s",
    handlers=[logging.FileHandler(LOG_PATH / "server.log", encoding="utf-8"),
              logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("ai-lens")

from enrich import make_enricher  # noqa: E402  (after logging is configured)
from news import NewsStore  # noqa: E402

STORE = NewsStore(DATA_PATH, RETENTION_DAYS)
ENRICHER = make_enricher(ENRICH_MODEL, ENRICH_MAX)
_refresh_lock = threading.Lock()
_last_refresh = 0.0

# Same policy as the <meta> tag in the pages, plus frame-ancestors (header-only).
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; style-src-attr 'unsafe-inline'; "
       "img-src 'self' data:; font-src 'self'; connect-src 'self'; object-src 'none'; "
       "base-uri 'self'; form-action 'none'; frame-ancestors 'none'")

# Only these files are ever served from disk — never python/, data/, logs/ or .env.
PUBLIC_FILES = {"/index.html", "/news.html", "/invest.html", "/reflections.html", "/philosophy.html", "/favicon.svg"}
ASSETS = (ROOT / "assets").resolve()


def public_path(path: str) -> str | None:
    """Map a request path to a servable file, or None.

    The path is URL-decoded and normalised *before* the allow-list check, and the
    final file is resolved (following symlinks) and must stay inside assets/, so
    encoded tricks such as /assets/%2e%2e/.env cannot escape."""
    clean = posixpath.normpath("/" + unquote(path).lstrip("/"))
    if clean == "/":
        clean = "/index.html"
    if clean in PUBLIC_FILES:
        return clean
    target = (ROOT / clean.lstrip("/")).resolve()
    if clean.startswith("/assets/") and target.is_relative_to(ASSETS) and target.is_file():
        return clean
    return None

def run_refresh(reason: str) -> dict | None:
    global _last_refresh
    if not _refresh_lock.acquire(blocking=False):
        return None
    try:
        _last_refresh = time.time()
        log.info("refresh (%s)", reason)
        return STORE.refresh(ENRICHER)
    except Exception:
        log.exception("refresh failed")
        return None
    finally:
        _refresh_lock.release()


def refresher() -> None:
    while True:
        run_refresh("scheduled")
        time.sleep(REFRESH_MINUTES * 60)


class Handler(SimpleHTTPRequestHandler):
    server_version = "Ai-Lens/1.0"

    def log_message(self, fmt: str, *args) -> None:
        log.debug("%s %s", self.address_string(), fmt % args)

    # ── helpers ────────────────────────────────────────────────────────
    def _route(self) -> tuple[str, dict]:
        parts = urlsplit(self.path)
        path = parts.path
        if BASE_PATH and (path == BASE_PATH or path.startswith(BASE_PATH + "/")):
            path = path[len(BASE_PATH):] or "/"
        return path, parse_qs(parts.query)

    def _json(self, payload, status: int = 200, cache: int = 0) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", f"public, max-age={cache}" if cache else "no-store")
        self.end_headers()
        self.wfile.write(body)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "strict-origin-when-cross-origin")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Security-Policy", CSP)
        super().end_headers()

    # ── verbs ──────────────────────────────────────────────────────────
    def do_GET(self) -> None:  # noqa: N802
        path, query = self._route()
        if path == "/api/health":
            return self._json({"ok": True, "updated_at": STORE.updated_at,
                               "stories": len(STORE.view)})
        if path == "/api/config":
            return self._json({"env": ENV_TYPE, "default_lang": DEFAULT_LANG,
                               "refresh_minutes": REFRESH_MINUTES,
                               "retention_days": RETENTION_DAYS,
                               "enrichment": ENRICHER is not None})
        if path == "/api/news":
            try:
                days = int(query.get("days", ["0"])[0]) or None
            except ValueError:
                days = None
            return self._json(STORE.snapshot(days), cache=60 if ENV_TYPE == "server" else 0)
        if path.startswith("/api/"):
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        return self._serve_static(path, head=False)

    def do_HEAD(self) -> None:  # noqa: N802
        path, _ = self._route()
        if path.startswith("/api/"):
            self.send_response(HTTPStatus.METHOD_NOT_ALLOWED)
            self.end_headers()
            return None
        return self._serve_static(path, head=True)

    def _serve_static(self, path: str, head: bool) -> None:
        safe = public_path(path)
        if safe is None:
            return self.send_error(HTTPStatus.NOT_FOUND)
        rng = re.fullmatch(r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip())
        if rng and rng.group(0) != "bytes=-":
            return self._serve_range(ROOT / safe.lstrip("/"), rng, head)
        self.path = safe
        return super().do_HEAD() if head else super().do_GET()

    def _serve_range(self, file: Path, rng: re.Match, head: bool) -> None:
        """Byte ranges, so audio can seek (and play at all in Safari)."""
        size = file.stat().st_size
        first, last = rng.group(1), rng.group(2)
        if first:
            start, end = int(first), min(int(last) if last else size - 1, size - 1)
        else:  # suffix range: the last N bytes
            start, end = max(0, size - int(last)), size - 1
        if start > end or start >= size:
            self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
            self.send_header("Content-Range", f"bytes */{size}")
            self.end_headers()
            return None
        self.send_response(HTTPStatus.PARTIAL_CONTENT)
        self.send_header("Content-Type", self.guess_type(str(file)))
        self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        if not head:
            with open(file, "rb") as f:
                f.seek(start)
                remaining = end - start + 1
                while remaining > 0:
                    chunk = f.read(min(65536, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        return None

    def do_POST(self) -> None:  # noqa: N802
        path, _ = self._route()
        if path != "/api/refresh":
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        wait = 60 - (time.time() - _last_refresh)
        if wait > 0:
            return self._json({"ok": False, "retry_in": int(wait)}, HTTPStatus.TOO_MANY_REQUESTS)
        result = run_refresh("manual")
        if result is None:
            return self._json({"ok": False, "busy": True}, HTTPStatus.CONFLICT)
        return self._json({"ok": True, **result})

    def guess_type(self, path):
        if str(path).endswith(".js"):
            return "text/javascript; charset=utf-8"
        if str(path).endswith(".m4a"):
            return "audio/mp4"
        return super().guess_type(path)


def main() -> None:
    threading.Thread(target=refresher, daemon=True, name="refresher").start()
    handler = partial(Handler, directory=str(ROOT))
    httpd = ThreadingHTTPServer((HOST, PORT), handler)
    log.info("Ai-Lens on http://%s:%d%s/  (env=%s, data=%s)",
             HOST, PORT, BASE_PATH, ENV_TYPE, DATA_PATH)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
