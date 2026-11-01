#!/usr/bin/env python3
"""Build a multilingual, static book from docs/<language>/*.md.

Run from the repository root: python site/build.py
Output: _site/ (for GitHub Pages). No JavaScript framework is required.
"""
from __future__ import annotations

import html
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from markdown_it import MarkdownIt
from seo import base_url, google_verification_meta, make_head, meta_description, write_seo_files

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
DOCS = ROOT / "docs"
OUT = ROOT / "_site"
CONFIG = json.loads((SITE / "config.json").read_text(encoding="utf-8"))
VERSION_RAW = os.environ.get("SITE_VERSION", "V0.1.0").strip() or "V0.1.0"
VERSION_MATCH = re.fullmatch(r"[vV](\d+)\.(\d+)\.(\d+)", VERSION_RAW)
VERSION = "V" + ".".join(VERSION_MATCH.groups()) if VERSION_MATCH else VERSION_RAW
LANGS = list(dict.fromkeys(CONFIG["languages"]))
DEFAULT_LANG = CONFIG["default_language"]
REPO_URL = CONFIG["repo_url"].rstrip("/")
LICENSE_URL = CONFIG["license_url"]
REPO_LICENSE_URL = f"{REPO_URL}/blob/main/LICENSE.md"
BOOKS_FILE = ROOT / "dist" / "manifest.json"
BOOKS = json.loads(BOOKS_FILE.read_text(encoding="utf-8")) if BOOKS_FILE.is_file() else {"languages": {}}
DISCUSSIONS_FILE = ROOT / "dist" / "discussions.json"
DISCUSSIONS = json.loads(DISCUSSIONS_FILE.read_text(encoding="utf-8")) if DISCUSSIONS_FILE.is_file() else {"pages": {}}


def find_logo() -> Path:
    """Use the user's actual logo.png (no generated or placeholder artwork)."""
    candidates = (ROOT / "logo.png", SITE / "static" / "logo.png", DOCS / "assets" / "logo.png")
    for candidate in candidates:
        if candidate.is_file():
            if candidate.read_bytes()[:8] != b"\x89PNG\r\n\x1a\n":
                raise ValueError(f"Expected a PNG image: {candidate}")
            return candidate
    raise FileNotFoundError(
        "logo.png not found. Add it at the repository root (next to site/, book/, docs/), "
        "or at site/static/logo.png or docs/assets/logo.png."
    )


def discussion_url(lang: str, number: int) -> str | None:
    """Return the dedicated GitHub Discussion for this exact chapter and language."""
    return DISCUSSIONS.get("pages", {}).get(lang, {}).get(route(number))


def verify_discussions(all_docs: dict) -> None:
    """Never publish chapter links that silently fall back to the forum index.

    Enabled in GitHub Actions after site/sync_discussions.py has created the threads.
    Local builds can still be used without a GitHub token or a discussion manifest.
    """
    if os.getenv("REQUIRE_DISCUSSIONS") != "1":
        return
    missing = []
    invalid = []
    for lang, chapters in all_docs.items():
        for number in chapters:
            url = discussion_url(lang, number)
            key = f"{lang}/{route(number)}"
            if not url:
                missing.append(key)
            elif not re.fullmatch(re.escape(REPO_URL) + r"/discussions/[1-9]\d*/?", url):
                invalid.append(f"{key}: {url}")
    if missing or invalid:
        details = []
        if missing:
            details.append("Missing discussion URLs: " + ", ".join(missing))
        if invalid:
            details.append("Invalid discussion URLs: " + "; ".join(invalid))
        raise RuntimeError("GitHub Discussions mapping incomplete. " + " | ".join(details)
                           + ". Check the preceding 'Find or create one GitHub Discussion per chapter' step.")


UI = {
 "es": {
  "subtitle":"Una exploración abierta y revisable del Dharma", "version_label":"Versión", "home":"Inicio", "contents":"Índice", "read":"Empezar a leer", "chapters":"Capítulos disponibles", "about":"Este proyecto", "about_text":"Una interpretación del Dharma como modelo para explorar la experiencia, abierta a preguntas, críticas y revisiones.", "unfinished":"Texto en desarrollo: no es una edición definitiva.", "change":"Debatir y proponer", "source":"Ver fuente Markdown", "previous":"Anterior", "next":"Siguiente", "in_progress":"Traducción en preparación", "in_progress_text":"Todavía no hay capítulos publicados en este idioma. Puedes leer la edición original en español.", "missing_translation":"No disponible en este idioma", "part-1":"Agradecimientos", "part0":"Prólogo", "part1":"I · Aprender a mirar", "part2":"II · Un mapa del Dharma", "part3":"III · Aprender a caminar", "part4":"IV · Explorar la experiencia", "part5":"V · Más allá del mapa", "part6":"Apéndices", "part7":"Bibliografía", "feedback":"¿Alguna objeción o propuesta?", "feedback_text":"El contenido es revisable. Contrasta las ideas, señala problemas o plantea una mejora en GitHub Discussions.", "original":"Leer el original en español", "license":"El contenido de este libro se distribuye bajo la licencia", "license_repo":"Leer LICENSE.md en GitHub", "edit":"En revisión", "home_title":"Explorar el Dharma sin confundir el mapa con el territorio", "home_description":"Un modelo abierto para observar la experiencia, examinar el sufrimiento y debatir caminos de transformación.", "language":"Idioma", "progress":"Actualmente disponible", "discuss_chapter":"Comentar este capítulo", "discuss_hint":"Debate público en GitHub Discussions. Se necesita una cuenta de GitHub para participar."},
 "en": {
  "subtitle":"An open, revisable exploration of the Dharma", "version_label":"Version", "home":"Home", "contents":"Contents", "read":"Start reading", "chapters":"Available chapters", "about":"About this project", "about_text":"An interpretation of the Dharma as a model for exploring experience, open to questions, criticism and revision.", "unfinished":"Work in progress: not a final edition.", "change":"Discuss and suggest", "source":"View Markdown source", "previous":"Previous", "next":"Next", "in_progress":"Translation in progress", "in_progress_text":"No chapters have been published in this language yet. You can read the Spanish original.", "missing_translation":"Not available in this language", "part-1":"Acknowledgements", "part0":"Prologue", "part1":"I · Learning to observe", "part2":"II · A map of the Dharma", "part3":"III · Learning the path", "part4":"IV · Exploring experience", "part5":"V · Beyond the map", "part6":"Appendices", "part7":"Bibliography", "feedback":"Have a criticism or suggestion?", "feedback_text":"This text is open to revision. Challenge ideas, identify issues or propose improvements on GitHub Discussions.", "original":"Read the original in Spanish", "license":"This book is distributed under the license", "license_repo":"Read LICENSE.md on GitHub", "edit":"Under review", "home_title":"Explore the Dharma without mistaking the map for the territory", "home_description":"An open model for observing experience, examining suffering and discussing paths toward transformation.", "language":"Language", "progress":"Currently available", "discuss_chapter":"Discuss this chapter", "discuss_hint":"Public discussion on GitHub. A GitHub account is needed to comment."},
 "de": {
  "subtitle":"Eine offene, überarbeitbare Erkundung des Dharma", "version_label":"Version", "home":"Startseite", "contents":"Inhalt", "read":"Lesen beginnen", "chapters":"Verfügbare Kapitel", "about":"Über dieses Projekt", "about_text":"Eine Interpretation des Dharma als Modell zur Erforschung der Erfahrung, offen für Fragen, Kritik und Überarbeitung.", "unfinished":"In Arbeit: keine endgültige Ausgabe.", "change":"Diskutieren und vorschlagen", "source":"Markdown-Quelle ansehen", "previous":"Zurück", "next":"Weiter", "in_progress":"Übersetzung in Vorbereitung", "in_progress_text":"In dieser Sprache sind noch keine Kapitel veröffentlicht. Du kannst die spanische Originalfassung lesen.", "missing_translation":"In dieser Sprache nicht verfügbar", "part-1":"Danksagung", "part0":"Prolog", "part1":"I · Wahrnehmen lernen", "part2":"II · Eine Karte des Dharma", "part3":"III · Den Weg gehen lernen", "part4":"IV · Erfahrung erkunden", "part5":"V · Jenseits der Karte", "part6":"Anhänge", "part7":"Bibliographie", "feedback":"Ein Einwand oder Vorschlag?", "feedback_text":"Dieser Text ist offen für Überarbeitungen. Hinterfrage Ideen, benenne Probleme und schlage Verbesserungen auf GitHub Discussions vor.", "original":"Spanisches Original lesen", "license":"Dieses Buch wird unter der Lizenz veröffentlicht", "license_repo":"LICENSE.md auf GitHub lesen", "edit":"In Bearbeitung", "home_title":"Den Dharma erkunden, ohne die Karte mit dem Gebiet zu verwechseln", "home_description":"Ein offenes Modell zum Beobachten der Erfahrung, zum Untersuchen von Leiden und zum Diskutieren von Veränderung.", "language":"Sprache", "progress":"Derzeit verfügbar", "discuss_chapter":"Dieses Kapitel kommentieren", "discuss_hint":"Öffentliche Diskussion auf GitHub. Zum Kommentieren wird ein GitHub-Konto benötigt."}
}

GROUPS = [(-1,-1,-1),(0,0,0),(1,1,6),(2,7,13),(3,14,18),(4,19,25),(5,26,29),(6,90,98),(7,99,99)]


def route(num: int) -> str:
    """Stable URLs; 0 is reserved for acknowledgements, 00 for prologue."""
    return "0" if num == -1 else f"{num:02d}"


def e(x: object) -> str:
    return html.escape(str(x), quote=True)


def part_for(number: int) -> int:
    for part, lo, hi in GROUPS:
        if lo <= number <= hi:
            return part
    raise ValueError(f"Chapter number {number:02d} is outside the configured ranges in GROUPS")


def extract_title(markdown: str, filename: str) -> str:
    for line in markdown.splitlines():
        match = re.match(r"^#\s+(.+?)\s*$", line)
        if match:
            return re.sub(r"\s+#+$", "", match.group(1)).strip()
    return filename.replace("-", " ")


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text or "section"


def collect() -> dict[str,dict[int,dict]]:
    all_docs = {}
    for lang in LANGS:
        pages = {}
        path = DOCS / lang
        if path.is_dir():
            for p in sorted(path.glob("*.md")):
                match = re.match(r"^(\d{2})[-_]", p.name)
                if not match:
                    # Prefix 0 is for acknowledgements in every language.
                    if not re.match(r"^0[-_].+\.md$", p.name) and p.name != "agradecimientos.md":
                        print(f"Skipping file without numerical prefix: {p}", file=sys.stderr)
                    continue
                num = int(match.group(1))
                part_for(num)  # Avoid silently omitting ungrouped chapters from the index.
                if num in pages:
                    raise ValueError(f"Duplicate chapter number {num:02} for {lang}")
                source = p.read_text(encoding="utf-8-sig")
                if num == 99:
                    # The filename remains 99-bibliografia.md, but 99 is not a printed chapter number.
                    source = re.sub(r"(?m)^#\s*99\s*[.．:–-]\s*", "# ", source, count=1)
                pages[num] = {"number": num, "title": extract_title(source, p.stem), "source": source, "path": p}
        # Acknowledgements display as 0; prologue displays as 00.
        # Support the previous name during migration, but do not permit duplicates.
        # Recognise translated names, e.g. 0-acknowledgements.md and 0-danksagung.md.
        legacy = path / "agradecimientos.md"
        candidates = sorted(path.glob("0-*.md"))
        if legacy.is_file():
            candidates.append(legacy)
        if len(candidates) > 1:
            raise ValueError(f"Multiple acknowledgements for {lang}: {', '.join(map(str, candidates))}. Remove duplicates.")
        acknowledgements = candidates[0] if candidates else None
        if acknowledgements is not None:
            source = acknowledgements.read_text(encoding="utf-8-sig")
            pages[-1] = {"number": -1, "title": extract_title(source, "Agradecimientos"),
                         "source": source, "path": acknowledgements}
        all_docs[lang] = dict(sorted(pages.items()))
    if not all_docs[DEFAULT_LANG]:
        raise SystemExit(f"No Markdown chapters in docs/{DEFAULT_LANG}/")
    return all_docs


def nav(lang: str, all_docs: dict, current: int | None, prefix: str) -> str:
    t = UI[lang]
    pages = all_docs[lang]
    out = [f'<nav class="chapter-nav" aria-label="{e(t["contents"])}">', f'<div class="nav-label">{e(t["contents"])}</div>']
    for part, lo, hi in GROUPS:
        items = [doc for num,doc in pages.items() if lo <= num <= hi]
        if not items:
            continue
        if part == 7:
            # Bibliography is a stand-alone section, not a numbered appendix.
            num = items[0]["number"]
            active = ' active' if num == current else ''
            aria = ' aria-current="page"' if num == current else ''
            out.append(f'<div class="chapter-group bibliography-group"><a class="part-title bibliography-link{active}"{aria} '
                       f'href="{e(prefix)}{e(lang)}/{route(num)}/">{e(t["part7"])}</a></div>')
            continue
        out.append(f'<div class="chapter-group"><div class="part-title">{e(t[f"part{part}"])}</div>')
        for doc in items:
            num = doc["number"]
            active = ' class="active" aria-current="page"' if num == current else ''
            name = re.sub(r"^\d+\.\s*", "", doc["title"])
            out.append(f'<a{active} href="{e(prefix)}{e(lang)}/{route(num)}/"><span class="chapter-number">{("0" if num == -1 else f"{num:02d}")}</span><span>{e(name)}</span></a>')
        out.append('</div>')
    out.append('</nav>')
    return "".join(out)


def render_markdown(text: str, lang: str, doc_path: Path, all_docs: dict, prefix: str) -> str:
    md = MarkdownIt("commonmark", {"html": True, "typographer": True}).enable("table").enable("strikethrough")
    tokens = md.parse(text)
    counters: dict[str,int] = defaultdict(int)
    for token in tokens:
        if token.type == "heading_open":
            pass
        if token.type == "inline":
            for child in token.children or []:
                if child.type in ("link_open", "image"):
                    attribute = "href" if child.type == "link_open" else "src"
                    href = child.attrGet(attribute) or ""
                    parts = urlsplit(href)
                    if parts.scheme or parts.netloc or not parts.path:
                        continue
                    target = (doc_path.parent / unquote(parts.path)).resolve()
                    if child.type == "link_open" and parts.path.lower().endswith(".md"):
                        num_match = re.match(r"^(\d{2})[-_]", target.name)
                        number = (-1 if re.match(r"^0[-_]", target.name) or target.name == "agradecimientos.md" else
                                  int(num_match.group(1)) if num_match else None)
                        if number is not None and target.is_relative_to(DOCS) and number in all_docs[lang]:
                            new_href = f"{prefix}{lang}/{route(number)}/"
                            if parts.fragment:
                                new_href += "#" + quote(parts.fragment)
                            child.attrSet(attribute, new_href)
                    elif target.is_relative_to(DOCS / "assets"):
                        rel = target.relative_to(DOCS / "assets").as_posix()
                        if target.is_file():
                            child.attrSet(attribute, f"{prefix}assets/content/{quote(rel, safe='/')}")
    for i,tok in enumerate(tokens):
        if tok.type == "heading_open" and i+1 < len(tokens) and tokens[i+1].type == "inline":
            content = tokens[i+1].content
            ident = slug(content)
            counters[ident] += 1
            if counters[ident] > 1:
                ident += f"-{counters[ident]}"
            tok.attrSet("id", ident)
    return md.renderer.render(tokens, md.options, {})


def language_options(lang: str, current: int | None, all_docs: dict, prefix: str) -> str:
    names = {"es":"Español", "en":"English", "de":"Deutsch"}
    menu = []
    for other in LANGS:
        translated = current is None or current in all_docs[other]
        if translated:
            url = f"{prefix}{other}/" if current is None else f"{prefix}{other}/{route(current)}/"
            css = "lang-option selected" if lang == other else "lang-option"
            menu.append(f'<a class="{css}" lang="{other}" hreflang="{other}" href="{e(url)}">{e(names.get(other,other))}</a>')
        else:
            menu.append(f'<span class="lang-option muted" lang="{other}" title="{e(UI[lang]["missing_translation"])}">{e(names.get(other,other))} <span aria-hidden="true">·</span></span>')
    return ''.join(menu)


def sidebar_downloads(lang: str, prefix: str) -> str:
    """Provide PDF/EPUB download links on every page, for the current language only."""
    edition = BOOKS.get("languages", {}).get(lang)
    if not edition:
        return ""

    labels = {
        "es": ("Descargar", "Edición parcial"),
        "en": ("Download", "Partial edition"),
        "de": ("Herunterladen", "Teilausgabe"),
    }
    heading, partial_label = labels.get(lang, labels["en"])
    links = []
    for fmt in ("pdf", "epub"):
        filename = edition.get(fmt)
        if filename:
            href = f"{prefix}downloads/{quote(filename)}"
            links.append(f'<a class="sidebar-download-link" href="{e(href)}" download '
                         f'aria-label="{e(heading)} {fmt.upper()}">{fmt.upper()} ↓</a>')
    if not links:
        return ""

    partial = (f'<small class="sidebar-download-note">{e(partial_label)}</small>'
               if edition.get("partial") else "")
    return (f'<section class="sidebar-downloads" aria-label="{e(heading)}">'
            f'<div class="sidebar-download-heading">{e(heading)}</div>'
            f'<div class="sidebar-download-buttons">{"".join(links)}</div>{partial}</section>')


def header_downloads(lang: str, prefix: str) -> str:
    """Always-visible compact PDF/EPUB links in the top bar."""
    edition = BOOKS.get("languages", {}).get(lang)
    if not edition:
        return ""
    links = []
    for fmt in ("pdf", "epub"):
        filename = edition.get(fmt)
        if filename:
            href = f"{prefix}downloads/{quote(filename)}"
            links.append(f'<a class="topbar-download" href="{e(href)}" download title="{fmt.upper()}">{fmt.upper()} ↓</a>')
    return ''.join(links)


def shell(lang: str, all_docs: dict, current: int | None, title: str, body: str, prefix: str, description: str) -> str:
    t = UI[lang]
    nav_html = nav(lang, all_docs, current, prefix)
    langs = language_options(lang, current, all_docs, prefix)
    download_nav = sidebar_downloads(lang, prefix)
    download_header = header_downloads(lang, prefix)
    home = f"{prefix}{lang}/"
    seo_head = make_head(lang=lang, current=current, title=title, description=description,
                         all_docs=all_docs, langs=LANGS, route=route, repo_url=REPO_URL, license_url=LICENSE_URL)
    # On chapters, the top-bar call-to-action must open that chapter's exact thread.
    # Only the homepage uses the general Discussions index.
    topic = discussion_url(lang, current) if current is not None else None
    community_url = topic or f"{REPO_URL}/discussions"
    community_label = t["discuss_chapter"] if topic else t["change"]
    return f'''<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
{seo_head}
<link rel="stylesheet" href="{e(prefix)}assets/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="topbar"><div class="topbar-inner">
<a class="brand" href="{e(home)}"><img class="brand-logo" src="{e(prefix)}assets/logo.png" alt="" width="42" height="42"><span><strong>¿Nirvana?</strong><small>¡Aguántame el cubata!</small></span></a>
<div class="topbar-actions">{download_header}<span class="version">{e(t["version_label"])} {e(VERSION)}</span><a class="community-link" href="{e(community_url)}" target="_blank" rel="noopener noreferrer">{e(community_label)} ↗</a></div>
</div></header>
<div class="layout"><aside class="sidebar"><div class="languages" aria-label="{e(t['language'])}">{langs}</div>{download_nav}{nav_html}</aside>
<div class="main-column"><main id="main">{body}</main><footer class="footer"><span>{e(t['unfinished'])}</span><span>{e(t['license'])} <a href="{e(LICENSE_URL)}" target="_blank" rel="noopener noreferrer">{e(CONFIG['license'])}</a> · <a href="{e(REPO_LICENSE_URL)}" target="_blank" rel="noopener noreferrer">{e(t['license_repo'])} ↗</a></span></footer></div></div>
</body></html>'''


def home_page(lang: str, all_docs: dict) -> str:
    t = UI[lang]
    pages = all_docs[lang]
    has_chapters = bool(pages)
    first_url = f"../{lang}/{route(next(iter(pages)))}/" if has_chapters else "../es/"
    intro = f'''<div class="eyebrow">{e(t["version_label"])} {e(VERSION)}</div>
<h1 class="hero-title">{e(t['home_title'])}</h1>
<p class="hero-description">{e(t['home_description'])}</p>
<div class="hero-actions"><a class="primary-link" href="{e(first_url)}">{e(t['read'] if has_chapters else t['original'])} <span>→</span></a><a class="secondary-link" href="{e(REPO_URL)}/discussions" target="_blank" rel="noopener noreferrer">{e(t['change'])} ↗</a></div>'''
    edition = BOOKS.get("languages", {}).get(lang)
    if edition:
        titles = {"es": ("Descargar esta edición", "Edición parcial: traducción pendiente"),
                  "en": ("Download this edition", "Partial edition: translation in progress"),
                  "de": ("Diese Ausgabe herunterladen", "Teilausgabe: Übersetzung in Arbeit")}
        section_title, warning = titles.get(lang, titles["en"])
        intro += f'<section class="book-downloads"><h2>{e(section_title)}</h2><div class="download-links">'
        for fmt in ("pdf", "epub"):
            file_name = edition.get(fmt)
            if file_name:
                intro += f'<a class="download-link" href="../downloads/{quote(file_name)}" download>{fmt.upper()} ↓</a>'
        intro += '</div>'
        if edition.get("partial"):
            intro += f'<p class="download-warning">{e(warning)}</p>'
        intro += '</section>'
    if not pages:
        intro += f'<div class="notice"><strong>{e(t["in_progress"])}</strong><p>{e(t["in_progress_text"])}</p></div>'
    else:
        ordinary = [(num, doc) for num, doc in pages.items() if num != 99]
        if ordinary:
            intro += f'<p class="section-heading">{e(t["chapters"])} <span>{len(ordinary)}</span></p><div class="chapter-cards">'
            for num,doc in ordinary:
                intro += f'<a class="chapter-card" href="../{lang}/{route(num)}/"><span class="chapter-number">{("0" if num == -1 else f"{num:02d}")}</span><span>{e(doc["title"])}</span><span class="card-arrow">↗</span></a>'
            intro += '</div>'
        if 99 in pages:
            intro += (f'<p class="section-heading">{e(t["part7"])}</p><div class="chapter-cards">'
                      f'<a class="chapter-card bibliography-card" href="../{lang}/99/">'
                      f'<span>{e(pages[99]["title"])}</span><span class="card-arrow">↗</span></a></div>')
    intro += f'<section class="about-panel"><h2>{e(t["about"])}</h2><p>{e(t["about_text"])}</p><p>{e(t["unfinished"])}</p></section>'
    return shell(lang, all_docs, None, t["home_title"], f'<section class="hero">{intro}</section>', '../', meta_description(lang, None, t["home_title"]))


def chapter_page(lang: str, number: int, all_docs: dict) -> str:
    t = UI[lang]
    pages = all_docs[lang]
    doc = pages[number]
    numbers = list(pages)
    ix = numbers.index(number)
    prev_num = numbers[ix-1] if ix > 0 else None
    next_num = numbers[ix+1] if ix < len(numbers)-1 else None
    prefix = '../../'
    part = part_for(number)
    body = render_markdown(doc['source'], lang, doc['path'], all_docs, prefix)
    target_discussion = discussion_url(lang, number)
    # Only advertise a chapter-specific thread when it actually exists.
    discussion_button = (
        f'<div class="chapter-discussion"><a class="chapter-discuss-link" href="{e(target_discussion)}" '
        f'target="_blank" rel="noopener noreferrer">💬 {e(t["discuss_chapter"])} ↗</a>'
        f'</div>'
        if target_discussion else ""
    )
    # The title is already in Markdown; do not duplicate it.
    body_html = (f'<div class="chapter-meta"><a href="{prefix}{lang}/">{e(t["home"])}</a> / '
                 f'{e(t[f"part{part}"])} <span>· {e(t["version_label"])} {e(VERSION)}</span></div>'
                 f'{discussion_button}<article class="prose">{body}</article>')
    source_path = doc['path'].relative_to(ROOT).as_posix()
    ref = os.environ.get("SOURCE_REF", "main")
    source_url = f'{REPO_URL}/blob/{quote(ref)}/{quote(source_path, safe="/")}'
    feedback_link = (
        f'<a href="{e(target_discussion)}" target="_blank" rel="noopener noreferrer">'
        f'{e(t["discuss_chapter"])} ↗</a>' if target_discussion else ''
    )
    body_html += (f'<div class="feedback-panel"><div class="feedback-icon">↗</div><div>'
                  f'<h2>{e(t["feedback"])}</h2><p>{e(t["feedback_text"])}</p>'
                  f'<div class="feedback-links">{feedback_link}'
                  f'<a href="{e(source_url)}" target="_blank" rel="noopener noreferrer">'
                  f'{e(t["source"])} ↗</a></div></div></div>')
    body_html += '<div class="chapter-pager">'
    if prev_num is not None:
        body_html += f'<a class="pager-link" href="{prefix}{lang}/{route(prev_num)}/"><small>← {e(t["previous"])}</small><strong>{e(pages[prev_num]["title"])}</strong></a>'
    else:
        body_html += '<span></span>'
    if next_num is not None:
        body_html += f'<a class="pager-link right" href="{prefix}{lang}/{route(next_num)}/"><small>{e(t["next"])} →</small><strong>{e(pages[next_num]["title"])}</strong></a>'
    body_html += '</div>'
    description = meta_description(lang, number, doc["title"], doc["source"])
    return shell(lang, all_docs, number, doc['title'], body_html, prefix, description)


def write_page(file: Path, content: str) -> None:
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")


def build() -> None:
    all_docs = collect()
    verify_discussions(all_docs)
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SITE / 'static', OUT / 'assets', dirs_exist_ok=True)
    # Copy the logo regardless of whether it lives at the repository root or in an assets folder.
    shutil.copy2(find_logo(), OUT / 'assets' / 'logo.png')
    if (DOCS / 'assets').is_dir():
        shutil.copytree(DOCS / 'assets', OUT / 'assets' / 'content', dirs_exist_ok=True)
    (OUT / '.nojekyll').write_text('',encoding='utf-8')
    # Expose generated book downloads in the static site.
    for edition in BOOKS.get('languages', {}).values():
        for fmt in ('pdf','epub'):
            name = edition.get(fmt)
            if name:
                src = ROOT / 'dist' / name
                if not src.is_file():
                    raise FileNotFoundError(f'Missing generated book: {src}')
                target = OUT / 'downloads' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, target)
    root_target = base_url(REPO_URL) + DEFAULT_LANG + "/"
    root_html = (
        f'<!doctype html><html lang="{e(DEFAULT_LANG)}"><head><meta charset="utf-8">'
        f'<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<meta http-equiv="refresh" content="0; url={e(DEFAULT_LANG)}/">'
        f'<title>{e(CONFIG["title"])}</title>'
        f'<link rel="canonical" href="{e(root_target)}">{google_verification_meta()}'
        f'</head><body><p><a href="{e(DEFAULT_LANG)}/">Leer en español / Read in Spanish</a></p></body></html>'
    )
    write_page(OUT / 'index.html', root_html)
    for lang in LANGS:
        write_page(OUT / lang / 'index.html', home_page(lang, all_docs))
        for num in all_docs[lang]:
            write_page(OUT / lang / route(num) / 'index.html', chapter_page(lang,num,all_docs))
        print(f'{lang}: {len(all_docs[lang])} chapters')
    write_seo_files(OUT, all_docs=all_docs, langs=LANGS, route=route, repo_url=REPO_URL)
    print(f'Generated static site: {OUT}')


if __name__ == '__main__':
    build()
