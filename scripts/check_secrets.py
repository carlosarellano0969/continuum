#!/usr/bin/env python3
"""Scan for hardcoded secrets in the codebase."""

from __future__ import annotations

import re
import sys
from pathlib import Path


PATTERNS = [
    # MongoDB connection strings with real structure (password part)
    (r"mongodb\+srv://[a-zA-Z0-9_\-]+:[a-zA-Z0-9!@#$%^&*()_\-\.~]+@[a-zA-Z0-9_\-\.]+\.mongodb\.net", "MongoDB connection string"),
    # OpenRouter API keys (sk-or-v1- followed by 40+ chars)
    (r"sk-or-v1-[A-Za-z0-9]{30,}", "OpenRouter API key"),
]

EXCLUDE_DIRS = {
    "node_modules",
    ".venv",
    ".git",
    ".claude",
    "docs",
    ".archive",
}

EXCLUDE_FILES = {".env", ".env.local", ".env.*.local"}


def should_exclude(path: Path) -> bool:
    """Check if path should be excluded from scanning."""
    # Check if any part of the path is in exclude list
    for part in path.parts:
        if part in EXCLUDE_DIRS:
            return True

    # Check filename against exclude patterns
    for pattern in EXCLUDE_FILES:
        if path.name == pattern or (pattern.startswith(".") and path.name.startswith(pattern)):
            return True

    return False


def scan_file(path: Path) -> list[tuple[int, str, str]]:
    """Scan a file for secrets. Returns list of (line_number, pattern_name, line_content)."""
    findings = []
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return findings

    for line_num, line in enumerate(content.split("\n"), 1):
        for pattern, name in PATTERNS:
            if re.search(pattern, line):
                findings.append((line_num, name, line.strip()))

    return findings


def main() -> int:
    cwd = Path.cwd()
    found_secrets = False

    for path in cwd.rglob("*"):
        if should_exclude(path):
            continue

        if path.is_file() and not path.name.startswith("."):
            findings = scan_file(path)
            for line_num, pattern_name, line_content in findings:
                print(f"{path.relative_to(cwd)}:{line_num}: {pattern_name}")
                print(f"  {line_content[:100]}")
                found_secrets = True

    if found_secrets:
        print("Secrets found!", file=sys.stderr)
        return 1

    print("No secrets found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
