#!/usr/bin/env python3
"""tokw - weigh files in tokens before you paste them into an agent's context.

Usage:
    tokw file1 file2 ...
    tokw -r dir [--ext .py,.md] [--budget 200000] [--json]

Token estimate heuristic (approximate, not a real tokenizer):
    - each CJK / CJK-punctuation character counts as 1 token
    - every other character counts as 1/4 token
The per-file total is rounded to the nearest whole token.

Exit codes: 0 always (informational); 2 on an unreadable path.
"""

import argparse
import json
import os
import sys

# Unicode blocks treated as "CJK-ish": each character ~= 1 token.
_CJK_RANGES = (
    (0x2E80, 0x2EFF),    # CJK Radicals Supplement
    (0x2F00, 0x2FDF),    # Kangxi Radicals
    (0x2FF0, 0x2FFF),    # Ideographic Description Characters
    (0x3000, 0x303F),    # CJK Symbols and Punctuation
    (0x3040, 0x309F),    # Hiragana
    (0x30A0, 0x30FF),    # Katakana
    (0x3100, 0x312F),    # Bopomofo
    (0x3130, 0x318F),    # Hangul Compatibility Jamo
    (0x3190, 0x319F),    # Kanbun
    (0x31A0, 0x31BF),    # Bopomofo Extended
    (0x31C0, 0x31EF),    # CJK Strokes
    (0x31F0, 0x31FF),    # Katakana Phonetic Extensions
    (0x3200, 0x32FF),    # Enclosed CJK Letters and Months
    (0x3300, 0x33FF),    # CJK Compatibility
    (0x3400, 0x4DBF),    # CJK Unified Ideographs Extension A
    (0x4E00, 0x9FFF),    # CJK Unified Ideographs
    (0xA960, 0xA97F),    # Hangul Jamo Extended-A
    (0xAC00, 0xD7AF),    # Hangul Syllables
    (0xD7B0, 0xD7FF),    # Hangul Jamo Extended-B
    (0xF900, 0xFAFF),    # CJK Compatibility Ideographs
    (0xFE30, 0xFE4F),    # CJK Compatibility Forms
    (0xFF00, 0xFFEF),    # Halfwidth and Fullwidth Forms
    (0x20000, 0x2A6DF),  # CJK Unified Ideographs Extension B
    (0x2A6E0, 0x2B73F),  # Extension C
    (0x2B740, 0x2B81F),  # Extension D
    (0x2B820, 0x2CEAF),  # Extensions E/F
    (0x2CEB0, 0x2EBEF),  # Extensions G/H/I
    (0x30000, 0x3134F),  # Extensions J/K
)

_SKIP_DIRS = {"__pycache__", "node_modules", ".git"}


def is_cjk(ch):
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in _CJK_RANGES)


def estimate_tokens(text):
    """Return the rounded token estimate for a text string."""
    total = 0.0
    for ch in text:
        total += 1.0 if is_cjk(ch) else 0.25
    return int(round(total))


def read_text(path):
    """Read a file, skipping binaries (null-byte sniffing). Returns None for binary."""
    with open(path, "rb") as f:
        raw = f.read()
    if b"\x00" in raw:
        return None
    # No UTF-16 fallback: almost any even-length byte string "successfully"
    # decodes as UTF-16 into garbage CJK, inflating token estimates for
    # latin-1 files by ~40%. (Genuine UTF-16 text has null bytes and is
    # already skipped as binary above.)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def collect_files(paths, exts):
    """Expand CLI path args into a list of files (recursive walk for -r)."""
    files = []
    for path in paths:
        if os.path.isfile(path):
            if exts is None or os.path.splitext(path)[1].lower() in exts:
                files.append(path)
        elif os.path.isdir(path):
            for root, dirs, names in os.walk(path):
                # Skip hidden dirs, __pycache__, node_modules, .git
                dirs[:] = [
                    d for d in dirs
                    if not d.startswith(".") and d not in _SKIP_DIRS
                ]
                for name in names:
                    if name.startswith("."):
                        continue
                    fp = os.path.join(root, name)
                    if exts is None or os.path.splitext(name)[1].lower() in exts:
                        files.append(fp)
        else:
            print("tokw: cannot read %r: not a file or directory" % path,
                  file=sys.stderr)
            sys.exit(2)
    return files


def weigh(paths, exts):
    """Return [(path, chars, tokens), ...] for readable text files, skipping binaries."""
    rows = []
    for path in collect_files(paths, exts):
        try:
            text = read_text(path)
        except OSError as exc:
            print("tokw: cannot read %r: %s" % (path, exc), file=sys.stderr)
            sys.exit(2)
        if text is None:  # binary, skipped
            continue
        rows.append((path, len(text), estimate_tokens(text)))
    return rows


def render_table(rows, budget):
    rows = sorted(rows, key=lambda r: r[2], reverse=True)
    total = sum(r[2] for r in rows)
    width = max([len(r[0]) for r in rows] + [len("path")])
    lines = []
    header = "%-*s  %10s  %10s" % (width, "path", "chars", "est. tokens")
    lines.append(header)
    lines.append("-" * len(header))
    for path, chars, tokens in rows:
        warn = "  << over 10% of budget" if tokens > budget * 0.10 else ""
        lines.append("%-*s  %10d  %10d%s" % (width, path, chars, tokens, warn))
    lines.append("-" * len(header))
    pct = (100.0 * total / budget) if budget > 0 else 0.0
    lines.append("TOTAL: %d est. tokens = %.1f%% of budget (%d)" % (total, pct, budget))
    if total > budget:
        lines.append("WARNING: total exceeds budget")
    return lines, total


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="tokw",
        description="Weigh files in tokens before pasting them into an agent's context.",
    )
    ap.add_argument("paths", nargs="+", help="files or directories")
    ap.add_argument("-r", "--recursive", action="store_true",
                    help="walk directories recursively")
    ap.add_argument("--ext", default=None,
                    help="comma-separated extensions to include, e.g. .py,.md")
    ap.add_argument("--budget", type=int, default=200000,
                    help="context budget in tokens (default 200000)")
    ap.add_argument("--json", action="store_true",
                    help="machine-readable JSON output")
    args = ap.parse_args(argv)

    paths = args.paths
    if not args.recursive:
        bad = [p for p in paths if os.path.isdir(p)]
        if bad:
            print("tokw: %r is a directory; use -r to walk it" % bad[0],
                  file=sys.stderr)
            sys.exit(2)

    exts = None
    if args.ext:
        exts = {e.strip().lower() for e in args.ext.split(",") if e.strip()}
        exts = {e if e.startswith(".") else "." + e for e in exts}

    rows = weigh(paths, exts)
    total = sum(r[2] for r in rows)

    if args.json:
        payload = {
            "budget": args.budget,
            "total_est_tokens": total,
            "percent_of_budget": round(100.0 * total / args.budget, 2)
            if args.budget > 0 else 0.0,
            "files": [
                {
                    "path": path,
                    "chars": chars,
                    "est_tokens": tokens,
                    "over_10pct_of_budget": tokens > args.budget * 0.10,
                }
                for path, chars, tokens in
                sorted(rows, key=lambda r: r[2], reverse=True)
            ],
        }
        print(json.dumps(payload, indent=2))
    else:
        lines, _ = render_table(rows, args.budget)
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
