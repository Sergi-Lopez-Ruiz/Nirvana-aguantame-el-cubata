#!/usr/bin/env python3
"""Generate PDF + EPUB editions from docs/<lang>/<NN>[-_]*.md.

Required: pandoc, XeLaTeX, DejaVu fonts.
Usage: python book/build.py --version v0.2.0
Output: dist/*.pdf, dist/*.epub, dist/manifest.json.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BOOK = ROOT / "book"
CONFIG = json.loads((ROOT / "site/config.json").read_text(encoding="utf-8"))
LABELS = {
    "es": {
        "prologue": "Prólogo", "parts": ["Aprender a mirar", "Un mapa del Dharma", "Aprender a caminar", "Explorar la experiencia", "Más allá del mapa"],
        "appendices": "Apéndices", "draft": "Edición en desarrollo", "partial": "Edición parcial: traducción en curso",
        "online": "Debatir este capítulo", "contents": "Índice",
    },
    "en": {
        "prologue": "Prologue", "parts": ["Learning to observe", "A map of the Dharma", "Learning the path", "Exploring experience", "Beyond the map"],
        "appendices": "Appendices", "draft": "Work in progress", "partial": "Partial edition: translation in progress",
        "online": "Discuss this chapter", "contents": "Contents",
    },
    "de": {
        "prologue": "Prolog", "parts": ["Wahrnehmen lernen", "Eine Karte des Dharma", "Den Weg gehen lernen", "Erfahrung erkunden", "Jenseits der Karte"],
        "appendices": "Anhänge", "draft": "Ausgabe in Bearbeitung", "partial": "Teilausgabe: Übersetzung in Arbeit",
        "online": "Dieses Kapitel diskutieren", "contents": "Inhalt",
    },
}


def group(num: int) -> int:
    if num == -1: return -1
    if num == 0: return 0
    if 1 <= num <= 6: return 1
    if 7 <= num <= 13: return 2
    if 14 <= num <= 18: return 3
    if 19 <= num <= 25: return 4
    if 26 <= num <= 29: return 5
    if 90 <= num <= 99: return 6
    raise ValueError(f"Chapter number {num:02d} is outside the established structure")


def discover(lang: str) -> dict[int, Path]:
    result = {}
    for path in sorted((DOCS / lang).glob("*.md")):
        match = re.match(r"^(\d{2})[-_]", path.name)
        if not match:
            if path.name not in ("0-agradecimientos.md", "agradecimientos.md"):
                print(f"Note: ignoring unnumbered Markdown: {path.relative_to(ROOT)}", file=sys.stderr)
            continue
        number = int(match.group(1))
        group(number)
        if number in result:
            raise ValueError(f"Duplicate chapter number {number:02d} for {lang}")
        result[number] = path
    canonical = DOCS / lang / "0-agradecimientos.md"
    legacy = DOCS / lang / "agradecimientos.md"
    if canonical.is_file() and legacy.is_file():
        raise ValueError(f"Both {canonical} and {legacy} exist. Delete the old one.")
    acknowledgements = canonical if canonical.is_file() else legacy
    if acknowledgements.is_file():
        result[-1] = acknowledgements
    return dict(sorted(result.items()))


def assemble(lang: str, docs: dict[int, Path], version: str, reference: set[int], *, for_pdf: bool = False) -> str:
    """Generate the book; PDF uses real LaTeX chapters, EPUB retains the nested navigation."""
    lbl = LABELS.get(lang, LABELS["en"])
    complete = set(docs) == reference
    # In a PDF, content before the first chapter would create a nearly empty page.
    # Place edition metadata under the first chapter title instead.
    text = [] if for_pdf else [f"*{lbl['draft']} · {version}*\n",
                               f"*{CONFIG.get('license', 'CC BY-NC-SA 4.0')}*\n"]
    partial_note = ""
    if not complete:
        missing = ", ".join(f"{x:02d}" for x in sorted(reference - set(docs)))
        partial_note = f"> **{lbl['partial']}**. {missing}\n"
        if not for_pdf:
            text.append(partial_note)
    group_seen = set()
    for num, path in docs.items():
        section = group(num)
        if section not in group_seen and section > 0:
            if section <= 5:
                label = f"{['I','II','III','IV','V'][section-1]} · {lbl['parts'][section-1]}"
            else:
                label = lbl["appendices"]
            if for_pdf:
                # In the PDF, parts and chapters are real LaTeX divisions.
                # This gives each chapter a new page without forcing odd-page starts.
                text.append(f"\n\\part{{{label}}}\n")
            else:
                text.append(f"\n# {label}\n")
        group_seen.add(section)
        original = path.read_text(encoding="utf-8-sig").strip()
        lines = original.splitlines()
        title_ix = next((i for i, line in enumerate(lines) if re.match(r"^#\s+\S", line)), None)
        title = path.stem.replace("_", " ").replace("-", " ")
        if title_ix is not None:
            title = re.sub(r"\s+#+\s*$", "", re.sub(r"^#\s+", "", lines[title_ix])).strip()
            del lines[title_ix]
        depth = 1 if for_pdf or num in (-1, 0) else 2
        text.append(f"\n{'#'*depth} {title} {{#chapter-{'0' if num == -1 else f'{num:02d}'}}}\n")
        chapter_url = (f"https://sergi-lopez-ruiz.github.io/"
                       f"Nirvana-aguantame-el-cubata/{lang}/"
                       f"{'0' if num == -1 else f'{num:02d}'}/")
        if for_pdf:
            if num == min(docs):
                text.append(f"*{lbl['draft']} · {version} · {CONFIG.get('license', 'CC BY-NC-SA 4.0')}*\n")
                if partial_note:
                    text.append(partial_note)
            # Put the web discussion link near the title, not on a nearly empty final page.
            if num != -1:
                text.append(f"[{lbl['online']}]({chapter_url})\n")
        # Shift existing subheadings down one level to keep headings nested under the chapter.
        # Prevent changing fenced code contents.
        in_fence = False
        for line in lines:
            if re.match(r"^\s*(```|~~~)", line):
                in_fence = not in_fence
            if not for_pdf and not in_fence and re.match(r"^#{2,5}\s+", line):
                line = "#" + line
            text.append(line)
        if not for_pdf and num != -1:
            text.append(f"\n[{lbl['online']}]({chapter_url})\n")
    return "\n".join(text) + "\n"


def metadata_args(lang: str, version: str, partial: bool) -> list[str]:
    lbl = LABELS.get(lang, LABELS["en"])
    subtitle = lbl["partial"] if partial else CONFIG.get("subtitle", "")
    author = CONFIG.get("author", "Sergio López Ruiz")
    entries = {
        "title": CONFIG["title"], "subtitle": subtitle,
        "author": author, "lang": lang, "date": version,
        "rights": CONFIG.get("license", "CC BY-NC-SA 4.0"),
        "description": f"{lbl['draft']} · {version}",
    }
    args = []
    for k, v in entries.items():
        args.extend(["--metadata", f"{k}={v}"])
    return args


def run(args: list[str]) -> None:
    print("$", " ".join(map(str, args[:8])), "...", flush=True)
    env = os.environ.copy()
    env["LANG"] = "C.UTF-8"
    env["LC_ALL"] = "C.UTF-8"
    subprocess.run(args, check=True, cwd=ROOT, env=env)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--version", default=os.environ.get("BOOK_VERSION", "Borrador"))
    parser.add_argument("--only", nargs="*", help="Restrict generation to one or more configured languages")
    options = parser.parse_args()
    if not shutil.which("pandoc"):
        raise SystemExit("Pandoc is not installed. See README-BOOKS.md")
    if not shutil.which("xelatex"):
        raise SystemExit("XeLaTeX is not installed. See README-BOOKS.md")
    configured = CONFIG["languages"]
    langs = [l for l in configured if not options.only or l in options.only]
    reference = set(discover(CONFIG["default_language"]))
    if not reference:
        raise SystemExit("The original language has no chapters")
    out = ROOT / "dist"
    out.mkdir(exist_ok=True)
    version = options.version.strip() or "Borrador"
    safe_version = re.sub(r"[^a-z0-9.-]+", "-", version.casefold()).strip("-.") or "borrador"
    manifest = {"version": version, "languages": {}}
    with tempfile.TemporaryDirectory(prefix="nirvana-book-") as tempdir:
        temp = Path(tempdir)
        for lang in langs:
            docs = discover(lang)
            if not docs:
                print(f"{lang}: skipped (no translations)")
                continue
            partial = set(docs) != reference
            suffix = "-parcial" if partial else ""
            stem = f"nirvana-{lang}-{safe_version}{suffix}"
            md = temp / f"{lang}.md"
            md_pdf = temp / f"{lang}-pdf.md"
            pdf = out / f"{stem}.pdf"
            epub = out / f"{stem}.epub"
            md.write_text(assemble(lang, docs, version, reference), encoding="utf-8")
            md_pdf.write_text(assemble(lang, docs, version, reference, for_pdf=True), encoding="utf-8")
            meta = metadata_args(lang, version, partial)
            common = ["pandoc", str(md), "--from=markdown+raw_html", "--standalone", "--toc", "--toc-depth=2", "--resource-path", f"{DOCS / lang}:{DOCS / 'assets'}:{ROOT}"]
            run(["pandoc", str(md_pdf), "--from=markdown+raw_tex+raw_html", "--standalone", "--toc", "--toc-depth=1", "--resource-path", f"{DOCS / lang}:{DOCS / 'assets'}:{ROOT}"] + ["--to=pdf", "--pdf-engine=xelatex", "-V", "documentclass=book", "-V", "classoption=oneside,openany",
                "-V", "papersize=a5", "-V", "mainfont=DejaVu Serif",
                "-V", "sansfont=DejaVu Sans", "-V", "geometry:margin=17mm",
                "-V", "fontsize=10pt", "--include-in-header", str(BOOK / "header.tex"),
                "--output", str(pdf)] + meta)
            run(common + ["--to=epub3", "--split-level=2", "--css", str(BOOK / "epub.css"), "--output", str(epub)] + meta)
            manifest["languages"][lang] = {
                "pdf": pdf.name, "epub": epub.name, "chapters": len(docs),
                "partial": partial, "missing": sorted(reference - set(docs)),
            }
            print(f"{lang}: {len(docs)} documents -> {pdf.name}, {epub.name}", flush=True)
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Created {len(manifest['languages'])} language editions in {out}")


if __name__ == "__main__":
    main()
