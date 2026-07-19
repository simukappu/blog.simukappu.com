#!/usr/bin/env python3
"""Refresh the `posts:` series mapping in series.yml from the Hashnode GraphQL API.

Each post's series membership is read from Hashnode's GraphQL API
(https://gql-beta.hashnode.com), which returns cuid, slug, and series slug in a
single query. This replaced the old headless-browser scraping of the live blog:
the API needs a paid-plan Personal Access Token, but it does not sit behind the
Vercel security checkpoint, needs no post backups on disk, and resolves every
post in one round trip. History note: gql.hashnode.com (the old free endpoint)
now redirects to a paid-offering announcement.

PAT sources, in order of precedence:
  1. env HASHNODE_PAT (this is what CI uses, from the repository secret)
  2. ~/.config/career-box-metrics/hashnode-pat (local runs)

Every run is a full sync: the API is authoritative, one query covers all
posts, so there is no incremental mode. Posts are written in cuid ascending
order (stable, diff-friendly). Standalone posts are recorded as
`<cuid>: null`. Only the `posts:` block is rewritten; the hand-maintained
`series:` metadata block (names and URLs) is preserved.

Usage:
    python tools/update-series.py            # sync posts: block from the API
    python tools/update-series.py --check    # exit 1 if series.yml is stale
                                             #   (does not write)

Dependencies: pyyaml (stdlib urllib for HTTP).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SERIES_FILE = REPO_ROOT / "series.yml"
BLOG_HOST = "blog.simukappu.com"
ENDPOINT = os.environ.get("HASHNODE_GQL_ENDPOINT", "https://gql-beta.hashnode.com")
PAT_PATH = Path.home() / ".config" / "career-box-metrics" / "hashnode-pat"

QUERY = """
query Series($host: String!, $after: String) {
  publication(host: $host) {
    posts(first: 50, after: $after) {
      pageInfo { hasNextPage endCursor }
      edges { node { cuid slug series { slug } } }
    }
  }
}
"""


def get_pat() -> str:
    pat = os.environ.get("HASHNODE_PAT")
    if pat:
        return pat.strip()
    if PAT_PATH.exists():
        return PAT_PATH.read_text().strip()
    print(
        "error: no Hashnode PAT (set env HASHNODE_PAT or create "
        f"{PAT_PATH}); a paid-plan token is required for the GraphQL API",
        file=sys.stderr,
    )
    raise SystemExit(1)


def gql(pat: str, variables: dict) -> dict:
    req = urllib.request.Request(
        ENDPOINT,
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={
            "Content-Type": "application/json",
            "Authorization": pat,
            "User-Agent": "blog-mirror-series-sync/1.0",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as res:
        data = json.load(res)
    if data.get("errors"):
        print(f"error: GraphQL errors: {data['errors']}", file=sys.stderr)
        raise SystemExit(1)
    return data["data"]


def fetch_posts(pat: str) -> list[dict]:
    """Return [{cuid, slug, series}] for every published post, cuid ascending."""
    posts: list[dict] = []
    after: str | None = None
    while True:
        data = gql(pat, {"host": BLOG_HOST, "after": after})
        pub = data.get("publication")
        if not pub:
            print("error: publication not found in API response", file=sys.stderr)
            raise SystemExit(1)
        page = pub["posts"]
        for edge in page["edges"]:
            node = edge["node"]
            series = node.get("series") or {}
            posts.append({
                "cuid": node["cuid"],
                "slug": node["slug"],
                "series": series.get("slug"),
            })
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    posts.sort(key=lambda p: p["cuid"])
    return posts


def extract_series_meta_block(text: str) -> str:
    """Return the text from the top through the end of the `series:` block."""
    lines = text.splitlines()
    out: list[str] = []
    for line in lines:
        if re.match(r"^posts:\s*$", line):
            break
        out.append(line)
    return "\n".join(out)


def render_series_yaml(series_meta_block: str, posts: list[dict]) -> str:
    """Render series.yml: preserve the `series:` block, rewrite `posts:`."""
    lines = [series_meta_block.rstrip(), "", "posts:"]
    for post in posts:
        lines.append(f"  # {post['slug']}")
        if post["series"]:
            lines.append(f"  {post['cuid']}: {post['series']}")
        else:
            lines.append(f"  {post['cuid']}: null")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
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
    valid_series = set((series_data.get("series") or {}).keys())

    pat = get_pat()
    posts = fetch_posts(pat)
    if not posts:
        print("error: API returned no posts; refusing to empty series.yml",
              file=sys.stderr)
        return 1

    for post in posts:
        label = post["series"] if post["series"] else "(standalone)"
        print(f"  {post['slug']} -> {label}")
        if post["series"] and post["series"] not in valid_series:
            print(
                f"warning: {post['slug']} belongs to unknown series "
                f"'{post['series']}' (add it to the series: block)",
                file=sys.stderr,
            )

    meta_block = extract_series_meta_block(current_text)
    new_text = render_series_yaml(meta_block, posts)

    if args.check:
        if new_text != current_text:
            print("series.yml is stale (run update-series.py to refresh)",
                  file=sys.stderr)
            return 1
        print("series.yml is up to date.")
        return 0

    if new_text != current_text:
        SERIES_FILE.write_text(new_text, encoding="utf-8")
        mapped = sum(1 for p in posts if p["series"])
        print(f"wrote {SERIES_FILE.relative_to(REPO_ROOT)} "
              f"({mapped} post(s) in a series, {len(posts) - mapped} standalone)")
    else:
        print("series.yml is already up to date.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
