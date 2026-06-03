#!/usr/bin/env python3
"""Refresh the `posts:` series mapping in series.yml from the live blog.

Hashnode does not write series membership into the synced markdown frontmatter, and its GraphQL API now requires a paid plan, so the only machine-readable source for "which series does this post belong to" is the rendered article page. The blog is hosted behind a Vercel security checkpoint that requires JavaScript, so a plain HTTP fetch is bounced to a challenge page; a headless browser is needed to reach the real content.

Where to run this
-----------------
The Vercel checkpoint gates by IP reputation: it clears from a residential IP but blocks datacenter IPs (GitHub Actions / cloud runners), where even a real headless browser is held on the "Vercel Security Checkpoint" page. So:

  * Authoritative runs happen LOCALLY (residential IP). After publishing a post on Hashnode and assigning its series, run this script once and commit the updated series.yml. No CUID hunting, no hand-edited YAML.
  * CI does NOT run this by default; it only regenerates README.md from the committed series.yml. A manual dispatch can attempt it best-effort, but that usually fails from CI's datacenter IP.

Incremental by design
---------------------
Resolving a post needs a headless hit that must clear the checkpoint, which is slow. To avoid paying that cost for posts whose series we already know, every post is recorded in `posts:` once resolved:

    <cuid>: <series-slug>   # belongs to a series
    <cuid>: null            # resolved, standalone (no series)

"key present" means "already resolved"; only posts missing from `posts:` are fetched. Run with --full to re-resolve every post (e.g. after adding an already-published post to a series on Hashnode).

This script rewrites only the `posts:` block; the hand-maintained `series:` metadata block (names and URLs) is preserved. build-index.py is untouched.

Usage:
    python tools/update-series.py            # incremental: resolve new posts
    python tools/update-series.py --full      # re-resolve every post
    python tools/update-series.py --check     # exit 1 if series.yml is stale
                                              #   (incremental semantics)

Dependencies:
    pyyaml, playwright (+ `playwright install chromium`)
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SERIES_FILE = REPO_ROOT / "series.yml"
BLOG_BASE_URL = "https://blog.simukappu.com"

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)
# The series link that marks the post's own series is rendered with a
# "Part of series" label, distinguishing it from header navigation links
# that point at other series.
PART_OF_SERIES_RE = re.compile(r"part of series", re.IGNORECASE)
# The Vercel anti-bot interstitial renders this title until the browser
# clears the JS challenge and the real article hydrates.
CHECKPOINT_TITLE_RE = re.compile(r"security checkpoint", re.IGNORECASE)

PAGE_TIMEOUT_MS = 60_000
CONTENT_TIMEOUT_MS = 60_000
CHECKPOINT_SETTLE_MS = 90_000
NAV_RETRIES = 3
RETRY_BACKOFF_S = 5
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Sentinel used in series.yml to mean "resolved, standalone (no series)".
STANDALONE = None


def parse_frontmatter(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    return yaml.safe_load(match.group(1))


def collect_posts(repo_root: Path) -> list[dict]:
    """Return [{cuid, slug, filename}] for every backup that has both keys."""
    posts: list[dict] = []
    for path in sorted(repo_root.glob("*.md")):
        if path.name == "README.md":
            continue
        fm = parse_frontmatter(path)
        if not fm:
            print(f"warning: no frontmatter in {path.name}", file=sys.stderr)
            continue
        cuid = fm.get("cuid")
        slug = fm.get("slug")
        if not cuid or not slug:
            print(f"warning: missing cuid/slug in {path.name}", file=sys.stderr)
            continue
        posts.append({"cuid": str(cuid), "slug": str(slug), "filename": path.name})
    return posts


def load_existing_mapping(series_data: dict) -> dict[str, str | None]:
    """Return the existing posts mapping (cuid -> series slug or None)."""
    posts = series_data.get("posts")
    if not isinstance(posts, dict):
        return {}
    return dict(posts)


def _wait_past_checkpoint(page) -> None:
    """Block until the real article has hydrated past the Vercel checkpoint.

    The checkpoint page and the article both eventually render an <h1>, so
    we cannot key purely off that. Instead we wait until the document title
    is no longer the checkpoint title AND the article body is present.
    """
    deadline = time.monotonic() + CHECKPOINT_SETTLE_MS / 1000
    last_title = ""
    while time.monotonic() < deadline:
        last_title = page.title() or ""
        if not CHECKPOINT_TITLE_RE.search(last_title):
            # Past the interstitial; make sure article content is in the DOM.
            try:
                page.wait_for_selector(
                    "article, main h1, a[href*='/series/']",
                    timeout=CONTENT_TIMEOUT_MS,
                )
                return
            except Exception:  # noqa: BLE001
                break
        page.wait_for_timeout(1000)
    raise RuntimeError(
        f"still on checkpoint/blank page (last title: {last_title!r})"
    )


def detect_series_for_slug(page, slug: str, valid_series: set[str]) -> str | None:
    """Open an article and return its series slug, or None if standalone."""
    url = f"{BLOG_BASE_URL}/{slug}"
    last_exc: Exception | None = None
    for attempt in range(1, NAV_RETRIES + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
            _wait_past_checkpoint(page)
            links = page.eval_on_selector_all(
                "a[href*='/series/']",
                "els => els.map(e => ({href: e.getAttribute('href'),"
                " text: (e.textContent || '').trim()}))",
            )
            for link in links:
                if PART_OF_SERIES_RE.search(link.get("text", "")):
                    series_slug = link["href"].rstrip("/").split("/series/")[-1]
                    if series_slug not in valid_series:
                        print(
                            f"warning: {slug} marked 'Part of series' -> "
                            f"unknown series '{series_slug}'",
                            file=sys.stderr,
                        )
                    return series_slug
            return STANDALONE
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < NAV_RETRIES:
                print(
                    f"  retry {attempt}/{NAV_RETRIES - 1} for {slug}: {exc}",
                    file=sys.stderr,
                )
                time.sleep(RETRY_BACKOFF_S)
    raise RuntimeError(f"content did not render for {url}: {last_exc}")


def resolve_mapping(
    posts: list[dict],
    existing: dict[str, str | None],
    valid_series: set[str],
    full: bool,
) -> tuple[dict[str, str | None], list[str]]:
    """Return (mapping, unresolved_slugs).

    Incremental (default): only posts whose cuid is absent from `existing`
    are fetched; known posts keep their recorded value. With --full every
    post is re-fetched. A post that fails to resolve keeps its existing
    value (if any) and is reported as unresolved; a brand-new post that
    fails to resolve is left out of the mapping entirely.
    """
    mapping: dict[str, str | None] = {}
    to_fetch: list[dict] = []
    for post in posts:
        cuid = post["cuid"]
        if not full and cuid in existing:
            mapping[cuid] = existing[cuid]
            label = existing[cuid] if existing[cuid] else "(standalone)"
            print(f"  {post['slug']} -> {label} (cached)")
        else:
            to_fetch.append(post)

    unresolved: list[str] = []
    if not to_fetch:
        return mapping, unresolved

    from playwright.sync_api import sync_playwright

    print(f"fetching series for {len(to_fetch)} post(s) via headless browser...")
    with sync_playwright() as p:
        # Reduce obvious automation fingerprints. This helps on borderline
        # checks but cannot defeat a pure IP-reputation block (datacenter
        # IPs), which is why CI treats this step as best-effort.
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
        ctx = browser.new_context(
            user_agent=USER_AGENT,
            locale="en-US",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1280, "height": 800},
            extra_http_headers={
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        ctx.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"
        )
        page = ctx.new_page()
        for post in to_fetch:
            cuid, slug = post["cuid"], post["slug"]
            try:
                series_slug = detect_series_for_slug(page, slug, valid_series)
            except Exception as exc:  # noqa: BLE001
                print(f"error: {exc}", file=sys.stderr)
                unresolved.append(slug)
                if cuid in existing:
                    mapping[cuid] = existing[cuid]  # keep last known value
                continue
            mapping[cuid] = series_slug
            print(f"  {slug} -> {series_slug if series_slug else '(standalone)'}")
        browser.close()
    return mapping, unresolved


def extract_series_meta_block(text: str) -> str:
    """Return the text from the top through the end of the `series:` block."""
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if re.match(r"^posts:\s*$", line):
            break
        out.append(line)
    return "\n".join(out)


def render_series_yaml(series_meta_block: str, posts: list[dict],
                       mapping: dict[str, str | None]) -> str:
    """Render series.yml: preserve the `series:` block, rewrite `posts:`.

    Every resolved post gets a line. Standalone posts are written as
    `<cuid>: null` so a later incremental run treats them as resolved and
    does not re-fetch them. A post still unresolved (absent from mapping)
    is left as a comment so the next run retries it.
    """
    lines = [series_meta_block.rstrip(), "", "posts:"]
    for post in posts:
        cuid, slug = post["cuid"], post["slug"]
        if cuid not in mapping:
            lines.append(f"  # {slug} (unresolved; will retry next run)")
            continue
        series_slug = mapping[cuid]
        lines.append(f"  # {slug}")
        if series_slug:
            lines.append(f"  {cuid}: {series_slug}")
        else:
            lines.append(f"  {cuid}: null")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--full",
        action="store_true",
        help="re-resolve every post (default: only posts not yet in series.yml)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 if series.yml would change (do not write)",
    )
    args = parser.parse_args()

    if not SERIES_FILE.exists():
        print(f"error: {SERIES_FILE} not found", file=sys.stderr)
        return 1

    current_text = SERIES_FILE.read_text(encoding="utf-8")
    series_data = yaml.safe_load(current_text) or {}
    series_meta = series_data.get("series", {}) or {}
    valid_series = set(series_meta.keys())
    existing = load_existing_mapping(series_data)

    posts = collect_posts(REPO_ROOT)
    if not posts:
        print("error: no posts found in repo root", file=sys.stderr)
        return 1

    mode = "full refresh" if args.full else "incremental"
    print(f"resolving series for {len(posts)} post(s) [{mode}]...")
    mapping, unresolved = resolve_mapping(posts, existing, valid_series, args.full)

    meta_block = extract_series_meta_block(current_text)
    new_text = render_series_yaml(meta_block, posts, mapping)

    if args.check:
        if new_text != current_text:
            print("series.yml is stale (run update-series.py to refresh)",
                  file=sys.stderr)
            return 1
        print("series.yml is up to date.")
        return 0

    if new_text != current_text:
        SERIES_FILE.write_text(new_text, encoding="utf-8")
        mapped = sum(1 for v in mapping.values() if v)
        print(f"wrote {SERIES_FILE.relative_to(REPO_ROOT)} "
              f"({mapped} post(s) in a series, "
              f"{len(mapping) - mapped} standalone)")
    else:
        print("series.yml is already up to date.")

    # A failure to resolve a NEW post (one with no prior value) is worth a
    # non-zero exit so CI surfaces it; transient failures on already-known
    # posts kept their cached value and are only warnings.
    new_failures = [s for s in unresolved
                    if all(p["slug"] != s or p["cuid"] not in existing
                           for p in posts)]
    if new_failures:
        print(
            "error: could not resolve series for new post(s): "
            + ", ".join(new_failures),
            file=sys.stderr,
        )
        return 1
    if unresolved:
        print(
            "warning: kept cached series for transiently-unresolved post(s): "
            + ", ".join(unresolved),
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
