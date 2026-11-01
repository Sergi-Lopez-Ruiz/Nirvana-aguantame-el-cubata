#!/usr/bin/env python3
"""Verify PDF/EPUB are embedded in the built GitHub Pages site, by language.
Run after book/build.py and site/build.py; no external packages required.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
manifest_file = ROOT / 'dist' / 'manifest.json'
site_root = ROOT / '_site'
if not manifest_file.is_file():
    raise SystemExit('ERROR: dist/manifest.json missing. Generate books before the website.')
manifest = json.loads(manifest_file.read_text(encoding='utf-8'))
langs = manifest.get('languages', {})
if not langs:
    raise SystemExit('ERROR: no PDF/EPUB editions in dist/manifest.json.')

for lang, edition in langs.items():
    home_file = site_root / lang / 'index.html'
    if not home_file.is_file():
        raise SystemExit(f'ERROR: missing site language homepage: {home_file}')
    html = home_file.read_text(encoding='utf-8')
    for fmt, signature in [('pdf', b'%PDF-'), ('epub', b'PK')]:
        name = edition.get(fmt)
        if not name:
            raise SystemExit(f'ERROR: {lang}: missing {fmt} entry in manifest')
        safe_name = Path(name).name
        if safe_name != name:
            raise SystemExit(f'ERROR: unsafe filename for {lang}: {name}')
        path = site_root / 'downloads' / name
        if not path.is_file() or path.stat().st_size < 100:
            raise SystemExit(f'ERROR: {lang}: missing or empty {fmt} in site: {path}')
        with path.open('rb') as f:
            if f.read(len(signature)) != signature:
                raise SystemExit(f'ERROR: {lang}: invalid {fmt} file signature: {path}')
        target = f'../downloads/{name}'
        if target not in unquote(html):
            raise SystemExit(f'ERROR: {lang}: missing {fmt} link in {home_file}: {target}')
        chapter_files = sorted((site_root / lang).glob('[0-9][0-9]/index.html'))
        if not chapter_files:
            raise SystemExit(f'ERROR: {lang}: no chapters, but a book edition exists.')
        chapter_html = chapter_files[0].read_text(encoding='utf-8')
        chapter_target = f'../../downloads/{name}'
        if chapter_target not in unquote(chapter_html):
            raise SystemExit(f'ERROR: {lang}: missing {fmt} in chapter page: {chapter_files[0]}')
        print(f'OK {lang}: {fmt.upper()} {path.stat().st_size:,} bytes; linked on homepage and chapter')

print('SUCCESS: every available PDF/EPUB edition is downloadable on GitHub Pages.')
