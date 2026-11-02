"""SEO helpers for the static multilingual book.

Works with Python's standard library; no SEO subscription or external service.
The site URL can be overridden in site/seo.json or by SITE_URL.
"""
from __future__ import annotations

import html
import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlsplit

from markdown_it import MarkdownIt

SITEMAP_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"
XHTML_NS = "http://www.w3.org/1999/xhtml"
ET.register_namespace("", SITEMAP_NS)
ET.register_namespace("xhtml", XHTML_NS)

SEO_FILE = Path(__file__).with_name("seo.json")
SEO = json.loads(SEO_FILE.read_text(encoding="utf-8"))


def base_url(repo_url: str) -> str:
    """Prefer an explicit public site URL; otherwise infer standard GitHub Pages."""
    explicit = os.environ.get("SITE_URL", "").strip() or SEO.get("site_url", "").strip()
    if explicit:
        url = explicit
    else:
        match = re.fullmatch(r"https://github\.com/([^/]+)/([^/]+)/?", repo_url, re.I)
        if not match:
            raise ValueError("Set site_url in site/seo.json to your public website URL")
        owner, repository = match.groups()
        url = f"https://{owner.lower()}.github.io/{repository}/"
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
        raise ValueError("site_url must be an HTTPS address without query or fragment")
    return url.rstrip("/") + "/"


def canonical(base: str, lang: str, current: int | None, route) -> str:
    return f"{base}{lang}/" if current is None else f"{base}{lang}/{route(current)}/"


def description_from_markdown(source: str, heading: str) -> str:
    """Use the first meaningful passage rather than an identical description for every chapter."""
    md = MarkdownIt("commonmark")
    tokens = md.parse(source)
    candidates = []
    for index, token in enumerate(tokens):
        if token.type != "paragraph_open" or index + 1 >= len(tokens):
            continue
        inline = tokens[index + 1]
        if inline.type != "inline":
            continue
        raw = re.sub(r"\s+", " ", inline.content).strip()
        raw = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", raw)
        raw = re.sub(r"[`*_~]", "", raw)
        raw = html.unescape(raw)
        if len(raw) >= 85 and not raw.startswith("http"):
            candidates.append(raw)
    intro = candidates[0] if candidates else ""
    # Chapter names add topical context to introductions with a humorous opening.
    combined = f"{heading}. {intro}" if intro else heading
    if len(combined) <= 162:
        return combined
    abbreviated = combined[:160].rsplit(" ", 1)[0].rstrip(" ,;:-")
    return abbreviated + "…"


def meta_description(lang: str, number: int | None, title: str, source: str | None = None) -> str:
    if number is None:
        return SEO.get("home_descriptions", {}).get(lang, title)
    override = SEO.get("chapter_descriptions", {}).get(lang, {}).get(str(number))
    if override:
        return override
    return description_from_markdown(source or "", title)


def google_verification_meta() -> str:
    token = SEO.get("google_site_verification", "").strip()
    return (f'<meta name="google-site-verification" '
            f'content="{html.escape(token, quote=True)}">') if token else ""


def make_head(*, lang: str, current: int | None, title: str, description: str,
              all_docs: dict, langs: list[str], route, repo_url: str, license_url: str) -> str:
    base = base_url(repo_url)
    page_url = canonical(base, lang, current, route)
    book_name = SEO.get("book_titles", {}).get(lang, "¿Nirvana? ¡Aguántame el cubata!")
    home_suffix = SEO.get("home_title_suffix", {}).get(lang, "")
    page_title = (f"{book_name} | {home_suffix}" if home_suffix else book_name) if current is None else f"{title} | {book_name}"
    # Every language is its own canonical; NEVER point all chapters to Spanish.
    other_versions = [other for other in langs if current is None or current in all_docs[other]]
    tag = lambda value: html.escape(str(value), quote=True)
    fragments = [
        f'<title>{tag(page_title)}</title>',
        f'<meta name="description" content="{tag(description)}">',
        f'<link rel="canonical" href="{tag(page_url)}">',
    ]
    for other in other_versions:
        fragments.append(f'<link rel="alternate" hreflang="{tag(other)}" '
                         f'href="{tag(canonical(base, other, current, route))}">')
    if current is None:
        fragments.append(f'<link rel="alternate" hreflang="x-default" href="{tag(canonical(base, "es", None, route))}">')
    locale = {"es": "es_ES", "en": "en_US", "de": "de_DE"}
    fragments.extend([
        f'<meta property="og:type" content="{"book" if current is None else "article"}">',
        f'<meta property="og:title" content="{tag(page_title)}">',
        f'<meta property="og:description" content="{tag(description)}">',
        f'<meta property="og:url" content="{tag(page_url)}">',
        f'<meta property="og:site_name" content="{tag(book_name)}">',
        f'<meta property="og:locale" content="{locale.get(lang, "en_US")}">',
        f'<meta property="og:image" content="{tag(base + "assets/logo.png")}">',
        '<meta name="twitter:card" content="summary">',
        f'<meta name="twitter:title" content="{tag(page_title)}">',
        f'<meta name="twitter:description" content="{tag(description)}">',
    ])
    for other in other_versions:
        if other != lang and other in locale:
            fragments.append(f'<meta property="og:locale:alternate" content="{locale[other]}">')
    verification = google_verification_meta()
    if verification:
        fragments.append(verification)
    author = SEO.get("author", "").strip()
    book = {
        "@type": "Book",
        "name": book_name,
        "alternateName": "¿Nirvana? ¡Aguántame el cubata!" if lang != "es" else None,
        "inLanguage": lang,
        "url": canonical(base, lang, None, route),
        "isAccessibleForFree": True,
        "license": license_url,
    }
    if author:
        book["author"] = {"@type": "Person", "name": author}
    book = {k: v for k, v in book.items() if v is not None}
    if current is None:
        entity = book
    else:
        entity = {
            "@type": "Chapter",
            "name": title,
            "description": description,
            "inLanguage": lang,
            "url": page_url,
            "isPartOf": book,
        }
        if current >= 0:
            entity["position"] = current
        if author:
            entity["author"] = {"@type": "Person", "name": author}
    entity["@context"] = "https://schema.org"
    script = json.dumps(entity, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e")
    fragments.append(f'<script type="application/ld+json">{script}</script>')
    return "\n".join(fragments)


def write_seo_files(output: Path, *, all_docs: dict, langs: list[str], route, repo_url: str) -> None:
    """Generate complete sitemap from PUBLISHED pages only (never stale hardcoded URLs)."""
    base = base_url(repo_url)
    root = ET.Element(f"{{{SITEMAP_NS}}}urlset")
    for lang in langs:
        for current in [None, *all_docs[lang]]:
            entry = ET.SubElement(root, f"{{{SITEMAP_NS}}}url")
            ET.SubElement(entry, f"{{{SITEMAP_NS}}}loc").text = canonical(base, lang, current, route)
            # The same reciprocal cluster of languages is repeated for each version.
            alternatives = [other for other in langs if current is None or current in all_docs[other]]
            for other in alternatives:
                ET.SubElement(entry, f"{{{XHTML_NS}}}link", {
                    "rel": "alternate",
                    "hreflang": other,
                    "href": canonical(base, other, current, route),
                })
    # Pretty-print sitemap.xml for easier inspection in a browser or text editor.
    # XML structure and Google Search Console compatibility stay unchanged.
    ET.indent(root, space="  ")
    ET.ElementTree(root).write(output / "sitemap.xml", encoding="utf-8", xml_declaration=True)
    # NOTE: for a GitHub Pages project URL (under /repository/), robots.txt in
    # that subdirectory is NOT the domain-wide robots.txt Google reads.
    (output / "robots.txt").write_text(
        "User-agent: *\nAllow: /\n\nSitemap: " + base + "sitemap.xml\n", encoding="utf-8"
    )
