#!/usr/bin/env python3
"""Find or create one GitHub Discussion per published chapter and language.

Requires repository Discussions enabled, a category named 'Capítulos', and a token
with the GitHub Actions `discussions: write` permission. The script is idempotent:
it identifies existing threads using stable hidden markers in their descriptions.
Writes dist/discussions.json, which site/build.py uses for exact discussion links.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from build import CONFIG, ROOT, collect, route

CATEGORY_NAME = os.getenv("DISCUSSIONS_CATEGORY", "Capítulos").strip()
GITHUB_GRAPHQL_URL = os.getenv("GITHUB_GRAPHQL_URL", "https://api.github.com/graphql")
MARKER = re.compile(r"<!--\s*nirvana-chapter:([a-z]{2}/(?:0|\d{2}))\s*-->")

# GitHub may refuse rapid successive discussion creations (anti-spam / secondary limit).
# Only creation calls are delayed; existing discussions are always reused immediately.
CREATE_DELAY_SECONDS = max(0.0, float(os.getenv("DISCUSSIONS_CREATE_DELAY_SECONDS", "12")))
RETRY_BASE_SECONDS = max(1.0, float(os.getenv("DISCUSSIONS_RETRY_BASE_SECONDS", "30")))
MAX_RETRIES = max(1, int(os.getenv("DISCUSSIONS_MAX_RETRIES", "6")))


def create_with_retry(variables: dict, token: str) -> dict:
    """Retry only temporary throttling errors, not validation/authentication failures."""
    for attempt in range(MAX_RETRIES):
        try:
            return graphql(CREATE, variables, token)
        except RuntimeError as exc:
            description = str(exc).lower()
            throttled = any(phrase in description for phrase in (
                "was submitted too quickly", "secondary rate limit",
                "rate limit", "abuse detection", "http 429",
            ))
            if not throttled:
                raise
            if attempt + 1 >= MAX_RETRIES:
                raise RuntimeError(
                    f"GitHub still blocks discussion creation after {MAX_RETRIES} attempts. "
                    "Already created discussions remain saved on GitHub. "
                    "Rerun the workflow later; existing discussions will be reused. "
                    f"Last error: {exc}"
                ) from exc
            wait = min(240.0, RETRY_BASE_SECONDS * (2 ** attempt))
            print(
                f"GitHub temporarily throttled createDiscussion; "
                f"waiting {wait:g}s before retry {attempt+2}/{MAX_RETRIES}...",
                file=sys.stderr, flush=True,
            )
            time.sleep(wait)
    raise AssertionError("unreachable")


def graphql(query: str, variables: dict, token: str) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    req = Request(GITHUB_GRAPHQL_URL, data=payload, headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/vnd.github+json",
        "User-Agent": "nirvana-discussions-sync",
    }, method="POST")
    try:
        with urlopen(req, timeout=30) as response:
            result = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:450]
        raise RuntimeError(f"GitHub API HTTP {exc.code}: {detail}. Check Discussions and token permissions.") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot contact GitHub API: {exc}") from exc
    if result.get("errors"):
        raise RuntimeError("GitHub GraphQL: " + json.dumps(result["errors"], ensure_ascii=False))
    return result["data"]


QUERY = """
query($owner: String!, $name: String!, $cursor: String) {
  repository(owner: $owner, name: $name) {
    id
    discussionCategories(first: 100) { nodes { id name } }
    discussions(first: 100, after: $cursor) {
      nodes { url body category { id } }
      pageInfo { hasNextPage endCursor }
    }
  }
}
"""
CREATE = """
mutation($input: CreateDiscussionInput!) {
  createDiscussion(input: $input) { discussion { url } }
}
"""


def sync() -> None:
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    repository = os.getenv("GITHUB_REPOSITORY", "")
    if not token or not re.fullmatch(r"[^/]+/[^/]+", repository):
        raise RuntimeError("Requires GITHUB_TOKEN and GITHUB_REPOSITORY=owner/repo.")
    owner, repo = repository.split("/")
    all_docs = collect()
    existing = {}
    cursor = None
    repo_id = None
    category_id = None
    while True:
        data = graphql(QUERY, {"owner": owner, "name": repo, "cursor": cursor}, token)
        repository_info = data.get("repository")
        if not repository_info:
            raise RuntimeError(f"Repository not found or token access denied: {repository}")
        repo_id = repository_info["id"]
        categories = repository_info["discussionCategories"]["nodes"]
        matches = [c for c in categories if c["name"].casefold() == CATEGORY_NAME.casefold()]
        if not matches:
            names = ", ".join(c["name"] for c in categories) or "(none)"
            raise RuntimeError(
                f"Missing GitHub Discussions category '{CATEGORY_NAME}'. Enable Discussions "
                f"in Settings → General → Features, create an open discussion category "
                f"named '{CATEGORY_NAME}' (existing categories: {names}), then rerun.")
        category_id = matches[0]["id"]
        connection = repository_info["discussions"]
        for discussion in connection["nodes"]:
            for marker in MARKER.findall(discussion.get("body") or ""):
                if marker in existing and existing[marker] != discussion["url"]:
                    raise RuntimeError(f"Duplicate existing Discussions for {marker}: "
                                       f"{existing[marker]} and {discussion['url']}")
                existing[marker] = discussion["url"]
        if not connection["pageInfo"]["hasNextPage"]:
            break
        cursor = connection["pageInfo"]["endCursor"]
        if not cursor:
            raise RuntimeError("Invalid GitHub Discussions pagination cursor")

    website = CONFIG.get("site_url") or f"https://{owner.lower()}.github.io/{repo}/"
    website = website.rstrip("/") + "/"
    links: dict[str, dict[str, str]] = {}
    created = 0
    reused = 0
    for language, chapters in all_docs.items():
        links[language] = {}
        for number, chapter in chapters.items():
            chapter_id = route(number)
            key = f"{language}/{chapter_id}"
            url = existing.get(key)
            if not url:
                title = re.sub(r"^\d+\.?\s*[-–:.]?\s*", "", chapter["title"]).strip()
                number_label = chapter_id
                discussion_title = f"[{language.upper()} · {number_label}] {title}"
                chapter_url = website + key + "/"
                body = (
                    f"Conversación abierta sobre **{title}** ({language.upper()}, {number_label}).\n\n"
                    f"📖 [Leer el capítulo]({chapter_url})\n\n"
                    "¿Qué preguntas, objeciones, matices o mejoras propondrías? "
                    "Las críticas razonadas y las perspectivas diferentes son bienvenidas. "
                    "Se puede participar en cualquier idioma, con respeto y curiosidad.\n\n"
                    "El texto puede cambiar entre versiones; este hilo conserva el debate.\n\n"
                    f"<!-- nirvana-chapter:{key} -->"
                )
                if created:
                    print(f"Pacing GitHub Discussions: waiting {CREATE_DELAY_SECONDS:g}s...", flush=True)
                    time.sleep(CREATE_DELAY_SECONDS)
                created_discussion = create_with_retry({"input": {
                    "repositoryId": repo_id, "categoryId": category_id,
                    "title": discussion_title, "body": body,
                }}, token)["createDiscussion"]["discussion"]
                url = created_discussion["url"]
                created += 1
                print(f"Created {key}: {url}")
            else:
                reused += 1
                print(f"Reused  {key}: {url}")
            links[language][chapter_id] = url
    target = ROOT / "dist" / "discussions.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"repository": repository, "category": CATEGORY_NAME,
                                  "pages": links}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Discussions: {created} created, {reused} reused. Mapping: {target}")


if __name__ == "__main__":
    try:
        sync()
    except RuntimeError as exc:
        sys.exit(f"ERROR syncing GitHub Discussions: {exc}")
