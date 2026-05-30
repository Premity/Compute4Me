#!/usr/bin/env python3
"""Check that all relative markdown links in the repo resolve.

Scans every `.md` file (excluding `.git/`, `.venv/`, `node_modules/`) for links
of the form `[text](path)` where `path` is a relative file reference. Asserts
that the referenced file exists. Anchor fragments (`#section-name`) are checked
for presence but not validated against actual headings (lightweight).

External links (`http://`, `https://`, `mailto:`) are skipped — they're checked
by a CI-only job, not on every pre-commit run.

Exit code 0 if all links resolve; 1 with a report of broken links otherwise.

Usage:
    python scripts/check_md_links.py             # scan whole repo
    python scripts/check_md_links.py FILE...     # scan specific files (used by pre-commit)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# [text](target) — capture target. Greedy on text, lazy on target.
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")

# Backtick-delimited inline code (single or multiple backticks); content inside is not
# parsed for links.
INLINE_CODE_RE = re.compile(r"(`+)[^`]*?\1")

EXCLUDE_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".mypy_cache"}


def is_external(target: str) -> bool:
    return target.startswith(("http://", "https://", "mailto:", "tel:", "//"))


def split_anchor(target: str) -> tuple[str, str | None]:
    if "#" in target:
        path, anchor = target.split("#", 1)
        return path, anchor
    return target, None


def find_md_files(root: Path) -> list[Path]:
    out: list[Path] = []
    for p in root.rglob("*.md"):
        if any(part in EXCLUDE_DIRS for part in p.parts):
            continue
        out.append(p)
    return out


def check_file(md_file: Path, repo_root: Path) -> list[str]:
    """Return list of broken-link error messages for this file."""
    errors: list[str] = []
    text = md_file.read_text(encoding="utf-8")
    in_fenced_block = False
    for lineno, line in enumerate(text.splitlines(), 1):
        # Track fenced code blocks (```); links inside aren't real.
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fenced_block = not in_fenced_block
            continue
        if in_fenced_block:
            continue
        # Strip inline code spans before scanning for links.
        scrubbed = INLINE_CODE_RE.sub("", line)
        for match in LINK_RE.finditer(scrubbed):
            target = match.group(1).strip()
            if is_external(target):
                continue
            if target.startswith("<") and target.endswith(">"):
                # angle-bracket wrapped — strip
                target = target[1:-1]
            if is_external(target) or not target:
                continue
            path, _anchor = split_anchor(target)
            if not path:
                # pure-anchor link like (#section) — same-file; assume valid
                continue
            # Resolve relative to the md file's directory
            resolved = (md_file.parent / path).resolve()
            if not resolved.exists():
                rel = md_file.relative_to(repo_root)
                errors.append(f"{rel}:{lineno}: broken link → {target}")
    return errors


def main(argv: list[str]) -> int:
    repo_root = Path(__file__).resolve().parent.parent
    if len(argv) > 1:
        files = [Path(a).resolve() for a in argv[1:] if a.endswith(".md")]
    else:
        files = find_md_files(repo_root)

    all_errors: list[str] = []
    for f in files:
        if not f.exists():
            continue
        all_errors.extend(check_file(f, repo_root))

    if all_errors:
        print(f"Found {len(all_errors)} broken markdown link(s):", file=sys.stderr)
        for e in all_errors:
            print(f"  {e}", file=sys.stderr)
        return 1

    print(f"All {sum(1 for f in files if f.exists())} markdown file(s) — links OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
