"""
Ai-Lens — fetch, parse, classify and cluster AI news.

Standard library only. The pipeline:

    fetch_all()   download every feed in parallel, parse RSS / Atom
    merge()       fold new items into the rolling store (data/news.json)
    build_view()  classify, score impact, collapse duplicate stories into
                  one lead item with `related` coverage ("echo")
"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import re
import threading
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from sources import SOURCES

log = logging.getLogger("ai-lens.news")

USER_AGENT = "Mozilla/5.0 (compatible; Ai-Lens/1.0; +local news timeline)"
FETCH_TIMEOUT = 15
MAX_FEED_BYTES = 5_000_000   # real feeds are well under 1 MB
MAX_SUMMARY = 320

# --------------------------------------------------------------------------
# Classification
# --------------------------------------------------------------------------

CATEGORIES = ["models", "products", "research", "business", "policy", "society"]

KEYWORDS = {
    "models": [
        "model", "llm", "gpt", "claude", "gemini", "llama", "mistral", "qwen", "deepseek",
        "grok", "weights", "open-weight", "open source", "open-source", "reasoning model",
        "multimodal", "benchmark", "fine-tun", "parameters", "checkpoint", "diffusion",
        "نموذج", "نماذج", "مفتوح المصدر", "مفتوحة المصدر",
    ],
    "products": [
        "app", "feature", "rolls out", "rollout", "launch", "available", "assistant",
        "chatbot", "chatgpt", "copilot", "agent", "agents", "browser", "api", "pricing",
        "subscription", "update", "device", "glasses", "phone", "android", "iphone",
        "ميزة", "تطبيق", "تطلق", "أطلقت", "يتيح", "تحديث", "مساعد", "روبوت محادثة", "وكيل",
    ],
    "research": [
        "research", "paper", "study", "scientist", "researchers", "university", "arxiv",
        "discovery", "protein", "physics", "math", "lab ", "experiment", "dataset",
        "بحث", "دراسة", "علماء", "باحثون", "باحثين", "جامعة", "اكتشاف",
    ],
    "business": [
        "funding", "raises", "raised", "billion", "million", "valuation", "acquire",
        "acquisition", "ipo", "investment", "investor", "revenue", "stock", "shares",
        "nvidia", "chip", "chips", "gpu", "data center", "datacenter", "compute",
        "partnership", "deal", "startup", "layoffs", "hiring",
        "تمويل", "استحواذ", "مليار", "مليون", "استثمار", "صفقة", "شراكة", "رقائق",
        "شرائح", "مراكز البيانات", "مركز بيانات", "أسهم", "شركة ناشئة",
    ],
    "policy": [
        "regulation", "regulator", "law", "lawsuit", "sue", "sued", "court", "judge",
        "ban", "government", "senate", "congress", "eu ", "european commission",
        "ai act", "policy", "safety", "copyright", "privacy", "antitrust", "ftc",
        "military", "pentagon", "election", "deepfake", "security",
        "قانون", "تنظيم", "حكومة", "دعوى", "محكمة", "سلامة", "حظر", "خصوصية",
        "تشريع", "الأمن", "وزارة", "مقاضاة", "الجيش", "عسكري", "ترمب", "ترامب",
        "البيت الأبيض", "الكونغرس", "الاتحاد الأوروبي",
    ],
    "society": [
        "jobs", "workers", "work", "education", "school", "students", "health",
        "doctor", "medical", "climate", "energy", "artists", "music", "film",
        "culture", "children", "ethics", "mental", "people",
        "وظائف", "تعليم", "طلاب", "صحة", "طبي", "مجتمع", "أطفال", "فنانين", "الطاقة",
    ],
}

BIG_KEYWORDS = [
    "launch", "launches", "unveil", "unveils", "introduc", "release", "releases",
    "announc", "billion", "acquire", "acquisition", "lawsuit", "ban", "breakthrough",
    "gpt-", "claude", "gemini", "record",
    "تطلق", "تكشف", "تعلن", "مليار", "استحواذ", "إطلاق",
]

# A headline that announces a new named model ("Introducing GPT-6", "Gemini 4 is here").
_RELEASE_VERB = re.compile(r"\b(introduc\w*|launch\w*|releas\w*|unveil\w*|announc\w*|meet|is here|now available)\b", re.I)
_MODEL_NAME = re.compile(
    r"\b(gpt|claude|gemini|gemma|llama|grok|sora|veo|imagen|o\d|qwen|deepseek|mistral|phi|glm|kimi|seedance)"
    r"[\s-]?(\d+(\.\d+)?|opus|sonnet|haiku|pro|ultra|flash)\b", re.I)


def is_release(title: str, source_kind: str) -> bool:
    """Heuristic for a major model launch worth a place on the main timeline."""
    return source_kind == "lab" and bool(_RELEASE_VERB.search(title)) and bool(_MODEL_NAME.search(title))


_INTRODUCING = re.compile(r"^(?:introducing|meet|announcing)\s+(.{2,40}?)(?:[:,—–-]|$)", re.I)


def widely_covered(lead: dict, stories: list[dict], min_outlets: int = 2) -> bool:
    """A lab's "Introducing X" post is a milestone when other outlets pick X up
    within a week — major launches get covered, minor posts do not."""
    if lead["source_kind"] != "lab":
        return False
    m = _INTRODUCING.match(lead["title"].strip())
    if not m:
        return False
    name = m.group(1).strip().rstrip(".")
    # Match the product name, tolerating a plural/singular "s" ("Dots" / "Dot agent").
    stem = re.escape(name.rstrip("s"))
    pat = re.compile(rf"\b{stem}s?\b", re.I)
    t0 = _parse_date(lead["published"])
    outlets = {s["source_name"] for s in stories
               if s["source"] != lead["source"]
               and abs((_parse_date(s["published"]) - t0).days) <= 7
               and (pat.search(s["title"]) or pat.search(s.get("summary", "")))}
    return len(outlets) >= min_outlets


AI_FILTER = [
    "ذكاء اصطناعي", "الذكاء الاصطناعي", "بالذكاء", "chatgpt", "openai", "gemini",
    "claude", "anthropic", "copilot", "deepseek", "llama", "nvidia", "إنفيديا",
    "نموذج لغوي", "النماذج اللغوية", " ai ", "ai-", "gpt",
]

_STOP = set("""
the a an and or of for to in on at by with from into over after about this that these
those its it's is are was were be been has have had will would can could new how why
what when who says said just more most than your you our their they them his her via
first also not but out up off one two all any some
في من على إلى الى عن مع هذا هذه ذلك التي الذي بعد قبل حول عبر بين كما أن إن لا ما
هل قد كل أو ثم بها به لها له عند منذ خلال ضمن تحت فوق جديد جديدة
الذكاء الاصطناعي ذكاء اصطناعي بالذكاء للذكاء artificial intelligence
""".split())

_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
_IMG_RE = re.compile(r"""<img[^>]+src=["']([^"']+)["']""", re.I)
_WORD_RE = re.compile(r"[\w؀-ۿ][\w؀-ۿ\-\.]*", re.U)
_ARABIC_RE = re.compile(r"[؀-ۿ]")


def clean_text(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", raw))
    return _WS_RE.sub(" ", text).strip()


def truncate(text: str, limit: int = MAX_SUMMARY) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(" ,.;:—-") + "…"


def detect_lang(text: str) -> str:
    return "ar" if len(_ARABIC_RE.findall(text)) > max(4, len(text) * 0.25) else "en"


def classify(text: str, hint: str) -> str:
    low = f" {text.lower()} "
    scores = {c: 0 for c in CATEGORIES}
    for cat, words in KEYWORDS.items():
        for w in words:
            if w in low:
                scores[cat] += 2 if len(w) > 6 else 1
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else hint


def is_big(text: str) -> bool:
    low = text.lower()
    return any(k in low for k in BIG_KEYWORDS)


def tokens(text: str) -> set[str]:
    out = set()
    for w in _WORD_RE.findall(text.lower()):
        w = w.strip(".-")
        if len(w) >= 3 and w not in _STOP:
            out.add(w)
    return out


# --------------------------------------------------------------------------
# Feed parsing
# --------------------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def _parse_date(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    try:
        dt = parsedate_to_datetime(raw)
    except (TypeError, ValueError, IndexError):
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _item_fields(node: ET.Element) -> dict:
    f: dict = {"categories": []}
    for child in node:
        name = _local(child.tag)
        text = (child.text or "").strip()
        if name == "title":
            f["title"] = text
        elif name == "link":
            href = child.get("href")
            rel = child.get("rel", "alternate")
            if href and rel == "alternate":
                f.setdefault("link", href)
            elif text:
                f.setdefault("link", text)
        elif name in ("pubdate", "published", "date"):
            f.setdefault("date", text)
        elif name == "updated":
            f.setdefault("updated", text)
        elif name in ("description", "summary"):
            f.setdefault("summary", text)
        elif name in ("thumbnail", "content") and child.get("url"):
            # media:thumbnail / media:content carry the image in an attribute.
            if child.get("medium", "image") == "image":
                f.setdefault("image", child.get("url"))
        elif name in ("encoded", "content") and text:
            f.setdefault("content", text)
        elif name == "enclosure" and (child.get("type") or "").startswith("image"):
            f.setdefault("image", child.get("url"))
        elif name == "group":
            for g in child:
                if _local(g.tag) in ("content", "thumbnail") and g.get("url"):
                    f.setdefault("image", g.get("url"))
        elif name == "source":
            f["publisher"] = text
        elif name == "category":
            f["categories"].append(text or child.get("term") or "")
    return f


def parse_feed(data: bytes, src: dict, now: datetime) -> list[dict]:
    root = ET.fromstring(data)
    nodes = [n for n in root.iter() if _local(n.tag) in ("item", "entry")]
    nodes = nodes[: src.get("max_items", 80)]
    out = []
    for node in nodes:
        f = _item_fields(node)
        title = clean_text(f.get("title"))
        link = (f.get("link") or "").strip()
        if not title or not link:
            continue
        source_name = src["name"]
        if f.get("publisher"):
            # Google News appends " - Publisher" to every title.
            source_name = f["publisher"]
            suffix = f" - {f['publisher']}"
            if title.endswith(suffix):
                title = title[: -len(suffix)].strip()
        body_html = f.get("summary") or f.get("content") or ""
        summary = truncate(clean_text(body_html))
        if src["id"].startswith("gnews"):
            summary = ""  # Google News descriptions only repeat the headline.
        image = f.get("image")
        if not image:
            m = _IMG_RE.search(f.get("content") or body_html)
            image = m.group(1) if m else None
        published = _parse_date(f.get("date")) or _parse_date(f.get("updated")) or now
        if published > now:
            published = now
        text = f"{title} {summary} {' '.join(f['categories'])}"
        if src.get("ai_filter"):
            low = f" {text.lower()} "
            if not any(k in low for k in AI_FILTER):
                continue
        out.append({
            "id": hashlib.sha1(link.encode("utf-8")).hexdigest()[:12],
            "title": title,
            "summary": summary,
            "url": link,
            "image": image,
            "source": src["id"],
            "source_name": source_name,
            "source_kind": src["kind"],
            "lang": detect_lang(title) if src["lang"] == "ar" else "en",
            "published": published.isoformat().replace("+00:00", "Z"),
            "hint": src.get("hint", "society"),
            "feed_tags": [c for c in f["categories"] if c][:6],
        })
    return out


def fetch_source(src: dict, now: datetime) -> tuple[str, list[dict], str | None]:
    req = urllib.request.Request(src["url"], headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml, */*",
    })
    try:
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:
            data = resp.read(MAX_FEED_BYTES + 1)
        if len(data) > MAX_FEED_BYTES:
            raise ValueError("feed larger than 5 MB")
        # Feeds never need DTD entities; refusing them rules out entity-expansion attacks.
        if b"<!ENTITY" in data[:20_000]:
            raise ValueError("feed declares XML entities")
        items = parse_feed(data, src, now)
        return src["id"], items, None
    except Exception as exc:  # network, HTTP, XML — one bad feed never sinks the run
        return src["id"], [], f"{type(exc).__name__}: {exc}"[:200]


def fetch_all() -> tuple[list[dict], dict]:
    now = datetime.now(timezone.utc)
    items: list[dict] = []
    status: dict = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for sid, got, err in pool.map(lambda s: fetch_source(s, now), SOURCES):
            items.extend(got)
            status[sid] = {"ok": err is None, "count": len(got), "error": err,
                           "checked_at": now.isoformat().replace("+00:00", "Z")}
            if err:
                log.warning("feed %s failed: %s", sid, err)
    return items, status


# --------------------------------------------------------------------------
# Store + view
# --------------------------------------------------------------------------


class NewsStore:
    """Rolling on-disk store of raw items plus a computed, clustered view."""

    def __init__(self, data_path: Path, retention_days: int):
        self.path = data_path / "news.json"
        self.retention = timedelta(days=retention_days)
        self.lock = threading.Lock()
        self.raw: dict[str, dict] = {}
        self.enrichment: dict[str, dict] = {}
        self.status: dict = {}
        self.updated_at: str | None = None
        self.view: list[dict] = []
        self._load()

    # ── persistence ────────────────────────────────────────────────────
    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.error("could not read %s: %s", self.path, exc)
            return
        self.raw = {i["id"]: i for i in doc.get("items", [])}
        self.enrichment = doc.get("enrichment", {})
        self.status = doc.get("status", {})
        self.updated_at = doc.get("updated_at")
        self.view = build_view(list(self.raw.values()), self.enrichment)
        log.info("loaded %d cached items (%d stories)", len(self.raw), len(self.view))

    def _save(self) -> None:
        doc = {"updated_at": self.updated_at, "status": self.status,
               "items": list(self.raw.values()), "enrichment": self.enrichment}
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    # ── refresh ────────────────────────────────────────────────────────
    def refresh(self, enricher=None) -> dict:
        fetched, status = fetch_all()
        now = datetime.now(timezone.utc)
        cutoff = now - self.retention
        with self.lock:
            for item in fetched:
                old = self.raw.get(item["id"])
                if old:
                    item["published"] = old["published"]  # first-seen date is stable
                self.raw[item["id"]] = item
            self.raw = {k: v for k, v in self.raw.items()
                        if _parse_date(v["published"]) and _parse_date(v["published"]) >= cutoff}
            self.enrichment = {k: v for k, v in self.enrichment.items() if k in self.raw}
            self.status = status
            self.updated_at = now.isoformat().replace("+00:00", "Z")
            self.view = build_view(list(self.raw.values()), self.enrichment)
            self._save()
        log.info("refresh: %d fetched, %d stored, %d stories",
                 len(fetched), len(self.raw), len(self.view))
        if enricher is not None:
            self.enrich(enricher)
        return {"fetched": len(fetched), "stored": len(self.raw), "stories": len(self.view)}

    def enrich(self, enricher) -> None:
        with self.lock:
            todo = [s for s in self.view if s["id"] not in self.enrichment]
        if not todo:
            return
        added = enricher(todo)
        if not added:
            return
        with self.lock:
            self.enrichment.update(added)
            self.view = build_view(list(self.raw.values()), self.enrichment)
            self._save()
        log.info("enriched %d stories", len(added))

    def snapshot(self, days: int | None = None) -> dict:
        with self.lock:
            items = self.view
            if days:
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                items = [i for i in items if _parse_date(i["published"]) >= cutoff]
            sources = [{"id": s["id"], "name": s["name"], "lang": s["lang"], "kind": s["kind"], "url": s["url"],
                        **self.status.get(s["id"], {})} for s in SOURCES]
            return {"updated_at": self.updated_at, "count": len(items),
                    "items": items, "sources": sources}


def build_view(raw: list[dict], enrichment: dict) -> list[dict]:
    """Classify, cluster duplicate coverage, score impact. Newest first."""
    raw = sorted(raw, key=lambda i: i["published"])
    toks = [tokens(i["title"]) for i in raw]
    times = [_parse_date(i["published"]) for i in raw]

    # Union-find over headlines that share most of their distinctive words
    # within a 48 h window — the same story told by several outlets.
    parent = list(range(len(raw)))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    window = timedelta(hours=48)
    for a in range(len(raw)):
        if len(toks[a]) < 3:
            continue
        for b in range(a + 1, len(raw)):
            if times[b] - times[a] > window:
                break
            if raw[a]["source"] == raw[b]["source"] or len(toks[b]) < 3:
                continue
            inter = len(toks[a] & toks[b])
            if inter >= 3 and inter / min(len(toks[a]), len(toks[b])) >= 0.55:
                parent[find(b)] = find(a)

    groups: dict[int, list[int]] = {}
    for idx in range(len(raw)):
        groups.setdefault(find(idx), []).append(idx)

    kind_rank = {"lab": 0, "press": 1, "aggregator": 2}
    stories = []
    for members in groups.values():
        lead_idx = min(members, key=lambda m: (kind_rank.get(raw[m]["source_kind"], 3), times[m]))
        lead = dict(raw[lead_idx])
        related = [{"source_name": raw[m]["source_name"], "url": raw[m]["url"],
                    "title": raw[m]["title"]} for m in members if m != lead_idx]
        outlets = {raw[m]["source_name"] for m in members}
        text = f"{lead['title']} {lead['summary']} {' '.join(lead.get('feed_tags', []))}"
        category = classify(text, lead.get("hint", "society"))
        impact = 2 + min(2, len(outlets) - 1)
        if lead["source_kind"] == "lab":
            impact += 1
        if is_big(lead["title"]):
            impact += 1
        lead.update({
            "published": min(raw[m]["published"] for m in members),
            "category": category,
            "impact": max(1, min(5, impact)),
            "echo": len(outlets),
            "related": related[:8],
            "milestone": is_release(lead["title"], lead["source_kind"]),
        })
        extra = enrichment.get(lead["id"])
        if extra:
            for key, limit in (("title_ar", 200), ("title_en", 200), ("summary_ar", 400), ("summary_en", 400)):
                if isinstance(extra.get(key), str) and extra[key].strip():
                    lead[key] = extra[key].strip()[:limit]
            if extra.get("category") in CATEGORIES:
                lead["category"] = extra["category"]
            if isinstance(extra.get("milestone"), bool):
                lead["milestone"] = extra["milestone"]
            if isinstance(extra.get("impact"), int):
                lead["impact"] = max(lead["impact"] - 1, min(5, extra["impact"]))
        lead.pop("hint", None)
        stories.append(lead)
    for s in stories:
        if not s["milestone"] and widely_covered(s, stories):
            s["milestone"] = True
    stories.sort(key=lambda s: s["published"], reverse=True)
    return stories
