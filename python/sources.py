"""
Ai-Lens — news sources.

Every source is a public RSS / Atom feed, except `format: "blog"` sources, whose
blog index page is read directly (see news.parse_blog). `kind` drives the impact heuristic
(first-party lab announcements weigh more than press coverage), `hint` is the
category used when the keyword classifier finds nothing, and `ai_filter`
keeps only AI-related items from general technology feeds.
"""

from urllib.parse import quote

_GNEWS_AR_QUERY = quote("الذكاء الاصطناعي when:3d")

SOURCES = [
    # ── First-party labs ────────────────────────────────────────────────
    {"id": "openai", "name": "OpenAI", "lang": "en", "kind": "lab", "hint": "models",
     "url": "https://openai.com/news/rss.xml"},
    {"id": "deepmind", "name": "Google DeepMind", "lang": "en", "kind": "lab", "hint": "research",
     "url": "https://deepmind.google/blog/rss.xml"},
    {"id": "google-ai", "name": "Google AI", "lang": "en", "kind": "lab", "hint": "products",
     "url": "https://blog.google/technology/ai/rss/"},
    {"id": "mistral", "name": "Mistral AI", "lang": "en", "kind": "lab", "hint": "models",
     "url": "https://mistral.ai/rss.xml"},
    {"id": "aleph-alpha", "name": "Aleph Alpha", "lang": "en", "kind": "lab", "hint": "models",
     "url": "https://aleph-alpha.com/en/blog/", "format": "blog",
     "post_pattern": r'href="(/en/blog/[a-z0-9-]{12,}/)"', "max_items": 8},
    {"id": "huggingface", "name": "Hugging Face", "lang": "en", "kind": "lab", "hint": "models",
     "url": "https://huggingface.co/blog/feed.xml"},

    # ── Press ───────────────────────────────────────────────────────────
    {"id": "techcrunch", "name": "TechCrunch", "lang": "en", "kind": "press", "hint": "business",
     "url": "https://techcrunch.com/category/artificial-intelligence/feed/"},
    {"id": "verge", "name": "The Verge", "lang": "en", "kind": "press", "hint": "products",
     "url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"},
    {"id": "ars", "name": "Ars Technica", "lang": "en", "kind": "press", "hint": "society",
     "url": "https://arstechnica.com/ai/feed/"},
    {"id": "wired", "name": "WIRED", "lang": "en", "kind": "press", "hint": "society",
     "url": "https://www.wired.com/feed/tag/ai/latest/rss"},
    {"id": "mittr", "name": "MIT Technology Review", "lang": "en", "kind": "press", "hint": "research",
     "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed"},
    {"id": "mitnews", "name": "MIT News", "lang": "en", "kind": "press", "hint": "research",
     "url": "https://news.mit.edu/rss/topic/artificial-intelligence2"},
    {"id": "sifted", "name": "Sifted", "lang": "en", "kind": "press", "hint": "business",
     "url": "https://sifted.eu/feed", "ai_filter": True},
    {"id": "decoder", "name": "The Decoder", "lang": "en", "kind": "press", "hint": "models",
     "url": "https://the-decoder.com/feed/"},

    # ── Arabic ──────────────────────────────────────────────────────────
    {"id": "aitnews", "name": "البوابة التقنية", "lang": "ar", "kind": "press", "hint": "products",
     "url": "https://aitnews.com/feed/", "ai_filter": True},
    {"id": "gnews-ar", "name": "أخبار Google", "lang": "ar", "kind": "aggregator", "hint": "society",
     "url": f"https://news.google.com/rss/search?q={_GNEWS_AR_QUERY}&hl=ar&gl=AE&ceid=AE:ar",
     "max_items": 60},
]
