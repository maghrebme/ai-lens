"""
Ai-Lens — optional bilingual enrichment with Claude.

When the `anthropic` package is installed and credentials are available
(ANTHROPIC_API_KEY or an `ant auth login` profile), each new story gets an
Arabic and English headline, a one-sentence summary in both languages, a
category and an impact score. Without it the site still works: headlines
show in their original language and the keyword classifier decides the
category.
"""

from __future__ import annotations

import json
import logging
import os

log = logging.getLogger("ai-lens.enrich")

CATEGORIES = ["models", "products", "research", "business", "policy", "society"]
BATCH = 20

SYSTEM = """You prepare AI-news headlines for a bilingual (Arabic/English) news timeline.

For every story you receive, return:
- title_ar: a natural Modern Standard Arabic headline (keep product and company names in Latin script, e.g. "OpenAI", "Gemini").
- title_en: a concise English headline.
- summary_ar / summary_en: one factual sentence each, using only what the headline and snippet say. Never invent figures, dates or quotes.
- category: one of models, products, research, business, policy, society.
  models = model releases and capabilities; products = apps and features; research = papers and science;
  business = funding, deals, chips, compute; policy = law, regulation, safety, security, government, military;
  society = work, education, health, culture.
- impact: 1-5, how significant the story is for the AI field (5 = major frontier release or landmark decision, 1 = minor or niche).
- milestone: true only if the story itself is a landmark for AI history — the launch of a new flagship model generation, a breakthrough result, or a binding law. Opinion pieces, guides, minor updates and funding rounds are false.

Return every id you were given, exactly once."""

SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "title_ar": {"type": "string"},
                    "title_en": {"type": "string"},
                    "summary_ar": {"type": "string"},
                    "summary_en": {"type": "string"},
                    "category": {"type": "string", "enum": CATEGORIES},
                    "impact": {"type": "integer", "enum": [1, 2, 3, 4, 5]},
                    "milestone": {"type": "boolean"},
                },
                "required": ["id", "title_ar", "title_en", "summary_ar", "summary_en",
                             "category", "impact", "milestone"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["items"],
    "additionalProperties": False,
}


def make_enricher(model: str, max_per_run: int):
    """Return a callable(stories) -> {id: fields}, or None when unavailable."""
    if os.environ.get("ENRICH", "auto").lower() in ("0", "off", "false", "no"):
        log.info("enrichment disabled by ENRICH")
        return None
    try:
        import anthropic
    except ImportError:
        log.info("enrichment off: `anthropic` package not installed (see python/requirements.txt)")
        return None
    try:
        client = anthropic.Anthropic()
    except Exception as exc:  # no credentials resolvable
        log.info("enrichment off: %s", exc)
        return None

    def call(batch: list[dict]) -> dict:
        payload = [{"id": s["id"], "source": s["source_name"], "headline": s["title"],
                    "snippet": s.get("summary", "")[:400]} for s in batch]
        request = dict(
            model=model,
            max_tokens=16000,
            system=SYSTEM,
            output_config={"effort": "low",
                           "format": {"type": "json_schema", "schema": SCHEMA}},
            messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        )
        try:
            # Server-side fallback: if a safety classifier declines, the API
            # retries on a fallback model inside the same call.
            resp = client.beta.messages.create(
                betas=["server-side-fallback-2026-07-01"], fallbacks="default", **request)
        except TypeError:
            resp = client.messages.create(**request)  # older SDK without `fallbacks`
        if resp.stop_reason == "refusal":
            log.warning("enrichment batch declined: %s", getattr(resp, "stop_details", None))
            return {}
        text = next((b.text for b in resp.content if b.type == "text"), "")
        out = {}
        for row in json.loads(text).get("items", []):
            row_id = row.pop("id", None)
            if row_id:
                out[row_id] = row
        return out

    def enrich(stories: list[dict]) -> dict:
        todo = stories[:max_per_run]
        result: dict = {}
        for start in range(0, len(todo), BATCH):
            batch = todo[start:start + BATCH]
            try:
                result.update(call(batch))
            except anthropic.RateLimitError:
                log.warning("enrichment rate-limited; will resume next refresh")
                break
            except anthropic.AuthenticationError as exc:
                log.warning("enrichment auth failed: %s", exc)
                break
            except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
                log.warning("enrichment batch failed: %s", exc)
            except (json.JSONDecodeError, StopIteration) as exc:
                log.warning("enrichment returned unreadable output: %s", exc)
        return result

    log.info("enrichment on: model=%s, up to %d stories per refresh", model, max_per_run)
    return enrich
