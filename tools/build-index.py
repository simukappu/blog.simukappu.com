#!/usr/bin/env python3
"""Regenerate README.md from Hashnode-mirrored markdown backups.

Reads YAML frontmatter from each *.md file in the repository root (other
than README.md), joins it with `series.yml`, and renders an article
index into README.md.

Usage:
    python tools/build-index.py                  # regenerate README.md
    python tools/build-index.py --list-unmapped  # print post cuids that
                                                 #   series.yml does not map

--list-unmapped writes nothing. CI uses it to decide whether to call the
Hashnode API: a post present in the backups but absent from the `posts:` map
has not been resolved yet, which is the state a newly published post leaves
behind. See tools/MAINTAINING.md, "CI behavior".

Dependencies:
    pyyaml
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SERIES_FILE = REPO_ROOT / "series.yml"
README_FILE = REPO_ROOT / "README.md"
BLOG_BASE_URL = "https://blog.simukappu.com"
BLOG_TITLE = "Build at Scale"
BLOG_TAGLINE_HTML = (
    "architecture in production, from distributed systems to agentic AI, "
    "and the organizations that ship them"
)

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n", re.DOTALL)

# A top-level `key: "value"` line, capturing the value between the outer quotes.
QUOTED_SCALAR_RE = re.compile(r'^([ \t]*)([A-Za-z_][\w-]*):[ \t]*"(.*)"[ \t]*$')


class FrontmatterError(Exception):
    """Frontmatter exists but cannot be parsed even after repair."""

    def __init__(self, path: Path, cause: Exception) -> None:
        super().__init__(f"cannot parse frontmatter in {path.name}: {cause}")
        self.path = path


def repair_quoted_scalars(block: str) -> str:
    """Escape inner double quotes in `key: "value"` lines.

    Hashnode's backup export writes the title as a double-quoted YAML scalar
    without escaping double quotes inside it. A title such as
    `Defining "Good Enough" at National Scale` therefore produces invalid YAML,
    which PyYAML reports as `expected <block end>, but found '<scalar>'`. Re-emit
    those lines with the inner quotes escaped so the value survives intact.

    Only called after a parse failure, so frontmatter that is already valid, and
    in particular values that escape their quotes properly, is never rewritten.
    """
    out: list[str] = []
    for line in block.split("\n"):
        match = QUOTED_SCALAR_RE.match(line)
        if match and '"' in match.group(3):
            indent, key, value = match.groups()
            escaped = value.replace("\\", "\\\\").replace('"', '\\"')
            out.append(f'{indent}{key}: "{escaped}"')
        else:
            out.append(line)
    return "\n".join(out)


def parse_frontmatter(path: Path) -> dict | None:
    """Return the frontmatter dict, or None when the file has no frontmatter."""
    text = path.read_text(encoding="utf-8-sig")
    match = FRONTMATTER_RE.match(text)
    if not match:
        return None
    block = match.group(1)
    try:
        return yaml.safe_load(block)
    except yaml.YAMLError as first_error:
        try:
            data = yaml.safe_load(repair_quoted_scalars(block))
        except yaml.YAMLError:
            raise FrontmatterError(path, first_error) from first_error
        print(
            f"note: repaired unescaped double quotes in {path.name} frontmatter",
            file=sys.stderr,
        )
        return data


def collect_posts(repo_root: Path) -> list[dict]:
    posts: list[dict] = []
    for path in sorted(repo_root.glob("*.md")):
        if path.name == "README.md":
            continue
        fm = parse_frontmatter(path)
        if not fm:
            print(f"warning: no frontmatter in {path.name}", file=sys.stderr)
            continue
        fm["__filename__"] = path.name
        posts.append(fm)
    posts.sort(key=lambda p: str(p.get("datePublished", "")), reverse=True)
    return posts


def unmapped_cuids(posts: list[dict], series_map: dict) -> list[str]:
    """Return cuids present in the backups but absent from the `posts:` map.

    Membership is tested on the key, not the value. A standalone post is
    recorded as `<cuid>: null`, which is mapped, not missing.

    A backup with no cuid in its frontmatter cannot be mapped at all, and no
    API refresh would change that, so it is warned about rather than reported
    as missing. Reporting it would ask CI to call the API on every push forever.
    """
    missing: list[str] = []
    for post in posts:
        cuid = str(post.get("cuid", "")).strip()
        if not cuid:
            print(
                f"warning: {post['__filename__']} has no cuid in frontmatter, "
                "so it cannot be mapped to a series",
                file=sys.stderr,
            )
            continue
        if cuid not in series_map:
            missing.append(cuid)
    return missing


def date_short(value: object) -> str:
    if not value:
        return ""
    s = str(value)
    return s[:10]


def md_escape_pipe(text: str) -> str:
    return text.replace("|", r"\|")


def render_table(posts: list[dict], series_map: dict, series_meta: dict) -> str:
    lines = [
        "| Published | Title | Series | Post | Markdown |",
        "|---|---|---|---|---|",
    ]
    for p in posts:
        cuid = str(p.get("cuid", ""))
        slug = str(p.get("slug", ""))
        title = md_escape_pipe(str(p.get("title", "(untitled)")))
        published = date_short(p.get("datePublished"))
        canonical = f"{BLOG_BASE_URL}/{slug}" if slug else ""
        canonical_link = f"[Read on Hashnode]({canonical})" if canonical else ""
        backup_name = p["__filename__"]
        backup_link = f"[`{backup_name}`](./{backup_name})"
        series_slug = series_map.get(cuid)
        if series_slug and series_slug in series_meta:
            s = series_meta[series_slug]
            series_link = f"[{s['name']}]({s['url']})"
        else:
            series_link = "—"
        lines.append(
            f"| {published} | {title} | {series_link} | {canonical_link} | {backup_link} |"
        )
    return "\n".join(lines)


def render_readme(posts: list[dict], series_map: dict, series_meta: dict) -> str:
    table = render_table(posts, series_map, series_meta)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""# {BLOG_TITLE} (Blog Mirror)

[{BLOG_TITLE}]({BLOG_BASE_URL}) is a blog on {BLOG_TAGLINE_HTML}. This repository is an automated mirror, synced from Hashnode and maintained for machine-readable access. The canonical version of every post lives at the blog.

## Posts

{table}

## How to read this mirror

If you're an AI assistant or a feed reader, the markdown files in this repository contain the full text of each post with YAML frontmatter (title, slug, publish date, tags, ogImage). The canonical URL for each post is `{BLOG_BASE_URL}/{{slug}}` where `slug` comes from the frontmatter. Filenames use Hashnode-internal CUIDs and aren't human-readable on their own; use the table above to navigate by date or title.

## How this mirror is maintained

- Posts are synced automatically from Hashnode whenever they're published or edited.
- This README is regenerated by `tools/build-index.py` whenever a `.md` file or `series.yml` changes.
- Series mapping in `series.yml` is updated manually by the author when a new series-tagged post ships.

Last regenerated: {today}
"""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--list-unmapped",
        action="store_true",
        help="print the cuid of every post absent from the posts: map in "
             "series.yml, one per line, and exit without writing README.md",
    )
    args = parser.parse_args()

    if not SERIES_FILE.exists():
        print(f"error: {SERIES_FILE} not found", file=sys.stderr)
        return 1
    series_data = yaml.safe_load(SERIES_FILE.read_text(encoding="utf-8")) or {}
    series_meta = series_data.get("series", {}) or {}
    series_map = series_data.get("posts", {}) or {}

    try:
        posts = collect_posts(REPO_ROOT)
    except FrontmatterError as exc:
        # Fail loudly rather than dropping the post: an index that silently
        # omits an article is worse than a red build.
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not posts:
        print("error: no posts found in repo root", file=sys.stderr)
        return 1

    if args.list_unmapped:
        for cuid in unmapped_cuids(posts, series_map):
            print(cuid)
        return 0

    README_FILE.write_text(
        render_readme(posts, series_map, series_meta), encoding="utf-8"
    )
    print(f"wrote {README_FILE.relative_to(REPO_ROOT)} ({len(posts)} posts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
