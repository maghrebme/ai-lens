#!/usr/bin/env python3
"""
Ai-Lens — build a static copy of the site for hosting without a server
(GitHub Pages, Cloudflare Pages, any static host).

    python python/build_static.py [--out _site]

1. Loads the rolling news store from DATA_PATH (data/news.json). In CI the
   previous store is downloaded from the live site first, so history builds up
   across runs (see .github/workflows/pages.yml).
2. Fetches every feed once (and enriches with Claude if configured).
3. Writes the pages plus api/news.json, api/config.json and api/store.json.
   The front end falls back to these files when the live API is absent.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

from enrich import make_enricher  # noqa: E402
from news import NewsStore  # noqa: E402

PAGES = ["index.html", "news.html", "invest.html", "favicon.svg"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="_site")
    args = ap.parse_args()

    data_path = Path(os.environ.get("DATA_PATH", ROOT / "data"))
    data_path.mkdir(parents=True, exist_ok=True)
    retention = int(os.environ.get("RETENTION_DAYS", "45"))
    enricher = make_enricher(os.environ.get("ENRICH_MODEL", "claude-opus-5-5"),
                             int(os.environ.get("ENRICH_MAX_PER_REFRESH", "120")))

    store = NewsStore(data_path, retention)
    result = store.refresh(enricher)
    print(f"refresh: {result}")

    out = (ROOT / args.out).resolve()
    if out.exists():
        shutil.rmtree(out)
    (out / "api").mkdir(parents=True)
    for name in PAGES:
        shutil.copy2(ROOT / name, out / name)
    shutil.copytree(ROOT / "assets", out / "assets")

    snapshot = store.snapshot(retention)
    (out / "api" / "news.json").write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")
    config = {"env": "static", "static": True, "default_lang": os.environ.get("DEFAULT_LANG", "ar"),
              "refresh_minutes": int(os.environ.get("REFRESH_MINUTES", "720")),
              "retention_days": retention, "enrichment": enricher is not None}
    (out / "api" / "config.json").write_text(json.dumps(config), encoding="utf-8")
    # The raw store, so the next scheduled build can continue the history.
    shutil.copy2(data_path / "news.json", out / "api" / "store.json")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    print(f"built {out} — {snapshot['count']} stories")


if __name__ == "__main__":
    main()
