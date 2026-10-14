#!/usr/bin/env python3
"""
Ai-Lens — weekly check for new milestones and big deals, verified with Claude.

    ANTHROPIC_API_KEY=... python python/weekly_milestones.py [--days 8] [--dry-run]

1. Research: Claude searches the web for major AI announcements of the last
   few days and checks each one on the official source (server-side web search
   and web fetch). It writes a report of what it verified and what it rejected.
2. Extract: a second call turns the report into structured entries.
3. This script validates every entry, drops duplicates of existing data, adds
   the rest to assets/data/milestones.json and investments.json in date order,
   updates the counts in README.md, and writes a pull-request description.

Nothing is published: the GitHub workflow (.github/workflows/weekly-milestones.yml)
opens a pull request for a person to review. Runs on the Anthropic API with
your own key, billed per use.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

import anthropic

ROOT = Path(__file__).resolve().parent.parent
MILESTONES = ROOT / "assets" / "data" / "milestones.json"
INVESTMENTS = ROOT / "assets" / "data" / "investments.json"
README = ROOT / "README.md"

MODEL = os.environ.get("WEEKLY_MODEL", "claude-opus-5-5")
CATEGORIES = ["models", "products", "research", "policy", "business", "society"]
DEAL_TYPES = ["funding", "acquisition", "infrastructure", "strategic", "public", "market", "ipo"]
REGIONS = ["us", "europe", "china", "gulf", "northafrica", "other"]
CURRENCIES = {"USD": 1.0, "EUR": 1.1, "GBP": 1.3, "AED": 0.27, "MAD": 0.1}  # rough, for the size check
MIN_DEAL_USD = 1e9

log = logging.getLogger("ai-lens.weekly")

RESEARCH_SYSTEM = """You research AI news for Ai-Lens, a bilingual (Arabic/English) reference timeline of AI history. Accuracy matters more than coverage: anything you cannot verify on a source you actually opened is left out.

Find announcements made between {start} and {end} (inclusive) of these kinds:

MILESTONES
- a new frontier or flagship model, or a major new model family or version (not minor point updates, regional rollouts or price changes);
- a notable open-weight release from a significant lab;
- a product launch that changes what people can do with AI (e.g. a new agent product from a major lab);
- a research result widely reported as a breakthrough;
- a major AI law, regulation or government programme.

DEALS
- a funding round, acquisition, infrastructure deal or government programme worth at least USD 1 billion, announced or closed (not a rumour, a target or "in talks").

Check at least: OpenAI, Anthropic, Google / Google DeepMind, Meta, Microsoft, xAI, Amazon, Apple, NVIDIA, Mistral AI, Aleph Alpha, DeepSeek, Alibaba (Qwen), Moonshot (Kimi), Zhipu (Z.ai / GLM), ByteDance, MiniMax, Reflection AI, TII (Falcon), G42, MBZUAI, Institute of Foundation Models (K2), HUMAIN, ElevenLabs, Suno, Runway, Black Forest Labs. Also scan AI release trackers and the tech press (TechCrunch, The Verge, The Decoder, VentureBeat, Reuters) for anything big from other labs.

For every candidate:
1. Open the official source with web_fetch: the company's own announcement, blog post, model page or press release (or the government's own page). Use a major outlet's article only when no official page exists.
2. Confirm the date on that page. If only the month is certain, say so. Never guess a day.
3. Take every figure (parameters, prices, scores, amounts, valuations) from the page you opened. Note which claims are the company's own.
4. Skip anything already in the existing data listed below (same link, same model or product, or the same deal).

Do not include rumours, leaks, "reportedly" items, or anything you could not open and read.

Finish with a report: for each verified item give its kind (milestone or deal), organisation, date (and whether only the month is confirmed), the official URL you opened, the key facts with figures, and how significant it is. Then list the candidates you rejected, each with a one-line reason.

EXISTING DATA (most recent entries; do not repeat these):
{existing}"""

EXTRACT_SYSTEM = """You turn a verified research report into entries for Ai-Lens, a bilingual (Arabic/English) AI timeline. Use only facts stated in the report; never add figures, dates or claims. Include only items the report marks as verified with an official URL.

Milestone fields:
- date: YYYY-MM-DD as reported. precision: "month" when the report says only the month is confirmed, otherwise "day".
- category: models (model releases), products (apps, agents, features), research (papers, science), policy (law, regulation, government), business (companies, compute), society (work, education, culture).
- impact: 5 = era-defining (very rare); 4 = a lab's new flagship or frontier model; 3 = significant model or product; 2 = smaller release in a known line; 1 = minor.
- org: the organisation's usual short name (e.g. Google, Meta, Anthropic, Mistral AI, Microsoft, OpenAI).
- title_en: a short headline, about 3-10 words. title_ar: the same in natural Modern Standard Arabic; keep product and company names in Latin script.
- summary_en: one or two factual sentences (160-320 characters). Present company claims as claims ("Meta says..."). summary_ar: the same in natural Arabic ("تقول ...").
- link: the official URL from the report.

Deal fields: date, precision, type (funding, acquisition, infrastructure, strategic = corporate strategic investment, public = government programme, market, ipo), org, region (us, europe, china, gulf, northafrica, other), titles and summaries as above, link, amount and currency (USD, EUR, GBP, AED or MAD) exactly as reported, valuation and valuation_currency if reported (else 0 and "").

Also copy the report's rejected candidates with their reasons."""

_LANG_FIELDS = {
    "title_en": {"type": "string"}, "title_ar": {"type": "string"},
    "summary_en": {"type": "string"}, "summary_ar": {"type": "string"},
}
SCHEMA = {
    "type": "object",
    "properties": {
        "milestones": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string"}, "precision": {"type": "string", "enum": ["day", "month"]},
                "category": {"type": "string", "enum": CATEGORIES},
                "impact": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                "org": {"type": "string"}, **_LANG_FIELDS, "link": {"type": "string"},
            },
            "required": ["date", "precision", "category", "impact", "org", *_LANG_FIELDS, "link"],
            "additionalProperties": False,
        }},
        "deals": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "date": {"type": "string"}, "precision": {"type": "string", "enum": ["day", "month"]},
                "type": {"type": "string", "enum": DEAL_TYPES},
                "org": {"type": "string"}, "region": {"type": "string", "enum": REGIONS},
                **_LANG_FIELDS, "link": {"type": "string"},
                "amount": {"type": "number"}, "currency": {"type": "string", "enum": list(CURRENCIES)},
                "valuation": {"type": "number"}, "valuation_currency": {"type": "string"},
            },
            "required": ["date", "precision", "type", "org", "region", *_LANG_FIELDS, "link",
                         "amount", "currency", "valuation", "valuation_currency"],
            "additionalProperties": False,
        }},
        "rejected": {"type": "array", "items": {
            "type": "object",
            "properties": {"name": {"type": "string"}, "reason": {"type": "string"}},
            "required": ["name", "reason"], "additionalProperties": False,
        }},
    },
    "required": ["milestones", "deals", "rejected"],
    "additionalProperties": False,
}

# ── cost control ───────────────────────────────────────────────────────────
# Every run stays under MAX_USD (default $2). The API has no per-call spending cap,
# so each research request is kept small enough that its worst case is known:
# at most 10 server-tool iterations per request (then the API pauses), web_fetch
# text capped at FETCH_TOKENS per page. Before each further request the script
# checks that spent + WORST_REQUEST_USD + RESERVE_USD still fits; otherwise it
# stops searching and writes the report from what it gathered.
MAX_USD = float(os.environ.get("WEEKLY_MAX_USD", "2.0"))
FETCH_TOKENS = 3000
# Measured on real runs: a full research request (~18 searches, ~740K cached input
# tokens, ~13K output) costs about $0.90; most input is read back from the prompt
# cache at a twentieth of the price. A second request only starts if one more of
# these still fits under MAX_USD with the reserve.
WORST_REQUEST_USD = 1.00
RESERVE_USD = 0.30         # the wrap-up report and the extraction call (~$0.04-0.15)
MAX_REQUESTS = 4
WEB_SEARCH_USD = 0.01      # $10 per 1,000 searches
# $ per million tokens: input, output, cache read, cache write (5-minute).
PRICES = {
    "claude-opus-5-5": (4.0, 20.0, 0.20, 5.0),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5-5": (2.0, 10.0, 0.20, 2.5),
}
PRICE_UNKNOWN = (10.0, 50.0, 1.0, 12.5)  # a fallback model we don't list: assume the dearest tier

TOOLS = [
    {"type": "web_search_20260209", "name": "web_search", "max_uses": 20},
    {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 20, "max_content_tokens": FETCH_TOKENS},
]
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class Budget:
    def __init__(self, limit: float):
        self.limit, self.spent = limit, 0.0

    def add(self, resp, label: str) -> float:
        u = resp.usage
        p_in, p_out, p_read, p_write = PRICES.get(resp.model, PRICE_UNKNOWN)
        searches = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
        cost = ((u.input_tokens or 0) * p_in + (u.output_tokens or 0) * p_out
                + (getattr(u, "cache_read_input_tokens", 0) or 0) * p_read
                + (getattr(u, "cache_creation_input_tokens", 0) or 0) * p_write) / 1e6 + searches * WEB_SEARCH_USD
        self.spent += cost
        log.info("%s: $%.3f (model %s, in %s, out %s, cache read %s, searches %s) — total $%.3f of $%.2f",
                 label, cost, resp.model, u.input_tokens, u.output_tokens,
                 getattr(u, "cache_read_input_tokens", 0), searches, self.spent, self.limit)
        if self.spent > self.limit:
            raise RuntimeError(f"spending limit exceeded: ${self.spent:.2f} > ${self.limit:.2f}")
        return cost

    def room_for(self, amount: float) -> bool:
        return self.spent + amount <= self.limit


def _gathered(content: list) -> str:
    """Plain-text digest of what the research turn read: the model's notes plus the
    URL, title and text of each fetched page and search hit."""
    out: list[str] = []

    def walk(node, depth=0):
        if isinstance(node, dict):
            url, title = node.get("url"), node.get("title")
            if url and (title or node.get("page_age")):
                out.append(f"- {title or ''} <{url}> {node.get('page_age') or ''}".strip())
            for key in ("data", "text"):
                if isinstance(node.get(key), str) and len(node[key]) > 200 and depth > 0:
                    out.append(node[key][:FETCH_TOKENS * 4])
            for v in node.values():
                if isinstance(v, (dict, list)):
                    walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    for block in content:
        if block.type == "text" and block.text.strip():
            out.append(block.text.strip())
        elif block.type.endswith("_tool_result"):
            walk(block.to_dict())
    return "\n".join(out)[:240_000]


# ── Claude calls ───────────────────────────────────────────────────────────
def research(client: anthropic.Anthropic, budget: Budget, start: date, end: date, existing: str) -> str:
    """Agentic research with server-side web tools, within the budget; returns the report."""
    system = (RESEARCH_SYSTEM.replace("{start}", start.isoformat()).replace("{end}", end.isoformat())
              .replace("{existing}", existing))
    task = {"role": "user", "content": f"""Today is {end.isoformat()}. Research and verify this week's announcements, then write the report.

Searches and page fetches are limited (about 20 of each), so plan them:
1. Two or three searches on AI release trackers and weekly AI news round-ups for these dates.
2. One search each for: AI funding rounds or acquisitions of $1 billion or more this week; AI laws, regulation or government AI programmes this week; major AI research breakthroughs this week.
3. Searches for the biggest labs not yet covered by those results (OpenAI, Google, Anthropic, Meta, Microsoft, xAI, DeepSeek, Alibaba Qwen, Mistral), combining several labs in one query where you can.
4. Fetch the official page only for candidates that look major, to confirm the date and figures. Do not fetch pages for items that are clearly minor or already in the existing data.
Cover milestones and deals in every run."""}
    content: list = []
    finished = False
    for i in range(MAX_REQUESTS):
        if i and not budget.room_for(WORST_REQUEST_USD + RESERVE_USD):
            log.info("budget: stopping the search after %d requests", i)
            break
        messages = [task] + ([{"role": "assistant", "content": content}] if content else [])
        with client.beta.messages.stream(
            model=MODEL, max_tokens=32000, system=system, tools=TOOLS, messages=messages,
            output_config={"effort": "medium"}, cache_control={"type": "ephemeral"}, **FALLBACK,
        ) as stream:
            resp = stream.get_final_message()
        budget.add(resp, f"research request {i + 1}")
        content += resp.content
        if resp.stop_reason == "refusal":
            raise RuntimeError(f"research declined: {getattr(resp, 'stop_details', None)}")
        if resp.stop_reason != "pause_turn":  # long server-tool turns pause; resend to continue
            finished = True
            break
    report = "\n".join(b.text for b in content if b.type == "text").strip() if finished else ""
    if finished and report:
        return report
    # Out of budget (or no report): write it from what was gathered, without tools.
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=16000, system=system,
        messages=[{"role": "user", "content": "The search budget is used up. Below is everything you found. "
                   "Write the report now, from these sources only: verified items first, then rejected "
                   "candidates. Leave out anything these sources do not confirm.\n\n" + _gathered(content)}],
        output_config={"effort": "medium"}, **FALLBACK,
    )
    budget.add(resp, "report")
    report = "\n".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "refusal" or not report:
        raise RuntimeError("research returned no report")
    return report


def extract(client: anthropic.Anthropic, budget: Budget, report: str) -> dict:
    """Turn the report into schema-valid entries (no tools, structured output)."""
    resp = client.beta.messages.create(
        model=MODEL, max_tokens=16000, system=EXTRACT_SYSTEM,
        messages=[{"role": "user", "content": report}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        **FALLBACK,
    )
    budget.add(resp, "extraction")
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"extraction declined: {getattr(resp, 'stop_details', None)}")
    if resp.stop_reason == "max_tokens":
        raise RuntimeError("extraction hit max_tokens")
    return json.loads(next(b.text for b in resp.content if b.type == "text"))


# ── validation and merge ───────────────────────────────────────────────────
_COMMON = {"the", "and", "for", "with", "from", "new", "its", "first", "model", "models", "launches",
           "releases", "introducing", "frontier", "open", "weight", "raises", "billion", "million", "deal"}


def _words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9][\w.-]{2,}", text.lower()) if w not in _COMMON}


def _norm_link(url: str) -> str:
    return url.strip().rstrip("/").split("#")[0].lower()


def _duplicate(entry: dict, existing: list[dict]) -> str | None:
    d = date.fromisoformat(entry["date"])
    for old in existing:
        if old.get("link") and _norm_link(old["link"]) == _norm_link(entry["link"]):
            return f"same link as \"{old['title_en']}\""
        if abs((date.fromisoformat(old["date"]) - d).days) <= 14 \
                and len(_words(old["title_en"]) & _words(entry["title_en"])) >= 2:
            return f"same story as \"{old['title_en']}\" ({old['date']})"
    return None


def _check_common(e: dict, start: date, end: date) -> str | None:
    try:
        d = date.fromisoformat(e["date"])
    except ValueError:
        return f"bad date {e['date']!r}"
    if not start - timedelta(days=3) <= d <= end:
        return f"date {e['date']} outside {start}..{end}"
    parts = urlsplit(e["link"])
    if parts.scheme != "https" or not parts.netloc:
        return f"link is not an https URL: {e['link']!r}"
    for key in _LANG_FIELDS:
        if not e[key].strip():
            return f"empty {key}"
    if len(e["summary_en"]) > 420 or len(e["summary_ar"]) > 420:
        return "summary too long"
    return None


def _clean_milestone(e: dict) -> dict:
    out = {k: e[k] for k in ("date", "category", "impact", "org", "title_en", "title_ar",
                             "summary_en", "summary_ar", "link")}
    if e["precision"] == "month":
        out["precision"] = "month"
    return out


def _clean_deal(e: dict) -> dict:
    out = {k: e[k] for k in ("date", "type", "org", "region", "title_en", "title_ar",
                             "summary_en", "summary_ar", "link")}
    if e["precision"] == "month":
        out["precision"] = "month"
    out["amount"], out["currency"] = float(e["amount"]), e["currency"]
    if e["valuation"] > 0 and e["valuation_currency"] in CURRENCIES:
        out["valuation"], out["valuation_currency"] = float(e["valuation"]), e["valuation_currency"]
    return out


def _insert(items: list[dict], entry: dict) -> None:
    i = max((k for k, x in enumerate(items) if x["date"] <= entry["date"]), default=-1) + 1
    items.insert(i, entry)


def _write(path: Path, items: list[dict]) -> None:
    assert [x["date"] for x in items] == sorted(x["date"] for x in items), f"{path.name} out of order"
    path.write_text(json.dumps(items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _update_readme(n_milestones: int, n_deals: int) -> None:
    text = README.read_text(encoding="utf-8")
    text = re.sub(r"\| \d+ محطة", f"| {n_milestones} محطة", text)
    text = re.sub(r"\| \d+ milestones", f"| {n_milestones} milestones", text)
    text = re.sub(r"\| \d+ صفقة", f"| {n_deals} صفقة", text)
    text = re.sub(r"\| \d+ funding rounds", f"| {n_deals} funding rounds", text)
    README.write_text(text, encoding="utf-8")


def _existing_summary(milestones: list[dict], deals: list[dict], since: date) -> str:
    rows = [f"- milestone {m['date']} · {m['org']} · {m['title_en']} · {m['link']}"
            for m in milestones if m["date"] >= since.isoformat()]
    rows += [f"- deal {d['date']} · {d['org']} · {d['title_en']} · {d['link']}"
             for d in deals if d["date"] >= since.isoformat()]
    return "\n".join(rows) or "(none)"


def _pr_body(added_m: list[dict], added_d: list[dict], skipped: list[tuple[str, str]],
             rejected: list[dict], start: date, end: date, cost: float) -> str:
    lines = [f"Weekly check of AI announcements from {start} to {end}, verified against official sources "
             f"by `{MODEL}` (`python/weekly_milestones.py`). API cost of this run: ${cost:.2f}.", "",
             "**Please review each entry and its source before merging.** Nothing is published until this "
             "pull request is merged.", ""]
    if added_m:
        lines += ["### Milestones", "", "| Date | Title | Impact | Source |", "|---|---|---|---|"]
        lines += [f"| {m['date']}{' (month)' if m.get('precision') else ''} | {m['title_en']} | {m['impact']} "
                  f"| [{urlsplit(m['link']).netloc}]({m['link']}) |" for m in added_m]
        lines.append("")
    if added_d:
        lines += ["### Deals", "", "| Date | Title | Amount | Source |", "|---|---|---|---|"]
        lines += [f"| {d['date']} | {d['title_en']} | {d['amount']:,.0f} {d['currency']} "
                  f"| [{urlsplit(d['link']).netloc}]({d['link']}) |" for d in added_d]
        lines.append("")
    if skipped or rejected:
        lines += ["### Considered but not added", ""]
        lines += [f"- {name}: {why}" for name, why in skipped]
        lines += [f"- {r['name']}: {r['reason']}" for r in rejected]
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=8, help="how many days back to look")
    ap.add_argument("--dry-run", action="store_true", help="print the result, change no files")
    ap.add_argument("--pr-body", default=os.environ.get("PR_BODY", "pr-body.md"),
                    help="where to write the pull-request description")
    args = ap.parse_args()

    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=args.days - 1)
    milestones = json.loads(MILESTONES.read_text(encoding="utf-8"))
    deals = json.loads(INVESTMENTS.read_text(encoding="utf-8"))

    client = anthropic.Anthropic()
    budget = Budget(MAX_USD)
    report = research(client, budget, start, end, _existing_summary(milestones, deals, start - timedelta(days=45)))
    log.info("report:\n%s", report)
    found = extract(client, budget, report)
    log.info("total cost: $%.3f (limit $%.2f)", budget.spent, budget.limit)

    added_m, added_d, skipped = [], [], []
    for e in found["milestones"]:
        why = _check_common(e, start, end) or _duplicate(e, milestones)
        if why:
            skipped.append((e["title_en"], why))
            continue
        entry = _clean_milestone(e)
        _insert(milestones, entry)
        added_m.append(entry)
    for e in found["deals"]:
        why = _check_common(e, start, end) or _duplicate(e, deals)
        if not why and e["amount"] * CURRENCIES[e["currency"]] < MIN_DEAL_USD:
            why = "below USD 1 billion"
        if why:
            skipped.append((e["title_en"], why))
            continue
        entry = _clean_deal(e)
        _insert(deals, entry)
        added_d.append(entry)

    body = _pr_body(added_m, added_d, skipped, found["rejected"], start, end, budget.spent)
    print(body)
    if args.dry_run or not (added_m or added_d):
        log.info("no files changed (%s)", "dry run" if args.dry_run else "nothing new")
        return 0
    if added_m:
        _write(MILESTONES, milestones)
    if added_d:
        _write(INVESTMENTS, deals)
    _update_readme(len(milestones), len(deals))
    Path(args.pr_body).write_text(body, encoding="utf-8")
    log.info("added %d milestones and %d deals", len(added_m), len(added_d))
    return 0


if __name__ == "__main__":
    sys.exit(main())
