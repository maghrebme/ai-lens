#!/usr/bin/env python3
"""
Ai-Lens — turn a Word article into the HTML used by reflections.html.

    python python/docx_to_article.py article-ar.docx ar > /tmp/ar.html
    python python/docx_to_article.py article-en.docx en > /tmp/en.html

Word styles map to: first Title → disclosure note, second Title → <h1>,
Subtitle → standfirst, Heading 1 → <h2> (with an anchor for the contents
list), Heading 2+ → <h3>, numbered/bulleted paragraphs → <li>, others → <p>.
Bold and italic runs are kept. A title of the form "Title: question" is split
into the title and the standfirst. A final paragraph that is entirely bold
becomes the closing pull quote.

The output has two marked parts, <!-- head:xx --> and <!-- body:xx -->; replace
the matching blocks in reflections.html with them. Standard library only.
"""

from __future__ import annotations

import html
import re
import sys
import zipfile


def _runs(p: str) -> str:
    out = []
    for r in re.findall(r"<w:r[ >].*?</w:r>", p, re.S):
        rpr = re.search(r"<w:rPr>(.*?)</w:rPr>", r, re.S)
        rpr = rpr.group(1) if rpr else ""
        bold = bool(re.search(r'<w:b/>|<w:b w:val="(?:1|true)"/>', rpr))
        italic = bool(re.search(r'<w:i/>|<w:i w:val="(?:1|true)"/>', rpr))
        parts = []
        for m in re.finditer(r"<w:t(?:\s[^>]*)?>([^<]*)</w:t>|<w:tab/>|<w:br/>", r):
            tok = m.group(0)
            parts.append(" " if tok.startswith("<w:tab") else "\n" if tok.startswith("<w:br") else html.unescape(m.group(1)))
        text = html.escape("".join(parts), quote=False).replace("\n", "<br>")
        if not text:
            continue
        if italic:
            text = f"<em>{text}</em>"
        if bold:
            text = f"<strong>{text}</strong>"
        out.append(text)
    s = re.sub(r"</strong><strong>|</em><em>", "", "".join(out))
    return re.sub(r"\s+", " ", s).strip()


def blocks(path: str) -> list[tuple[str, str]]:
    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    result, titles = [], 0
    for p in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        style = (re.search(r'<w:pStyle w:val="([^"]+)"', p) or [None, ""])[1]
        body = _runs(p)
        if not body:
            continue
        plain = re.sub(r"<[^>]+>", "", body)
        if style == "Title":
            titles += 1
            if titles == 1:
                result.append(("note", plain))
            elif ":" in plain:  # "Title: question" → title + standfirst
                head, tail = plain.split(":", 1)
                result += [("h1", head.strip()), ("standfirst", tail.strip())]
            else:
                result.append(("h1", plain))
        elif style == "Subtitle":
            result.append(("standfirst", plain))
        elif style.replace(" ", "") == "Heading1":
            result.append(("h2", plain))
        elif style.startswith("Heading"):
            result.append(("h3", plain))
        elif "<w:numPr>" in p:
            result.append(("li", body))
        else:
            result.append(("p", body))
    return result


def render(path: str, lang: str) -> str:
    bl = blocks(path)
    head = {k: v for k, v in bl if k in ("note", "h1", "standfirst")}
    body = [(k, v) for k, v in bl if k not in ("note", "h1", "standfirst")]
    closing = None
    if body and body[-1][0] == "p" and re.fullmatch(r"<strong>.*</strong>", body[-1][1]):
        closing = re.sub(r"</?strong>", "", body.pop()[1])

    out, toc, n, in_list = [], [], 0, False
    for kind, text in body:
        if kind != "li" and in_list:
            out.append("</ul>")
            in_list = False
        if kind == "h2":
            n += 1
            anchor = f"{lang}-s{n}"
            toc.append(f'<li><a href="#{anchor}">{html.escape(text)}</a></li>')
            out.append(f'<h2 id="{anchor}">{html.escape(text)}</h2>')
        elif kind == "h3":
            out.append(f"<h3>{html.escape(text)}</h3>")
        elif kind == "li":
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{text}</li>")
        else:
            out.append(f"<p>{text}</p>")
    if in_list:
        out.append("</ul>")

    e = html.escape
    d = "rtl" if lang == "ar" else "ltr"
    head_html = "\n".join(x for x in [
        f'<header class="essay-head" lang="{lang}" dir="{d}" data-lang="{lang}">',
        f'  <h1>{e(head.get("h1", ""))}</h1>',
        f'  <p class="standfirst">{e(head.get("standfirst", ""))}</p>' if head.get("standfirst") else "",
        f'  <p class="ai-note">{e(head.get("note", ""))}</p>' if head.get("note") else "",
        "</header>"] if x)
    body_html = "\n".join(x for x in [
        f'<div class="essay" lang="{lang}" dir="{d}" data-lang="{lang}">',
        '  <details class="essay-toc"><summary class="toc-title" data-i18n="contents"></summary><ol>',
        *[f"    {t}" for t in toc],
        "  </ol></details>",
        '  <div class="essay-body">',
        *[f"    {line}" for line in out],
        f'    <blockquote class="closing"><p>{e(closing)}</p></blockquote>' if closing else "",
        "  </div>",
        "</div>"] if x)
    return (f"<!-- head:{lang} -->\n{head_html}\n<!-- /head:{lang} -->\n"
            f"<!-- body:{lang} -->\n{body_html}\n<!-- /body:{lang} -->")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    print(render(sys.argv[1], sys.argv[2]))
