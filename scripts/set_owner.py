"""
Repoint the project at a different GitHub account.

The case-study footer, the README and SETUP.md all reference the owner's
GitHub username and Pages URL. This rewrites every occurrence and rebuilds
the page so nothing is left pointing at the old account.

    python3 scripts/set_owner.py <github-username> [repo-name]

Example:

    python3 scripts/set_owner.py amshu-example
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILES = ["README.md", "SETUP.md", "site/template.html", "docs/architecture.md"]

OLD_OWNER = "Vishal-bhandary"
OLD_REPO = "composio-app-research"


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    owner = sys.argv[1].strip().strip("/")
    repo = (sys.argv[2] if len(sys.argv) > 2 else OLD_REPO).strip().strip("/")

    if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner):
        sys.exit(f"{owner!r} is not a valid GitHub username")

    changed = []
    for rel in FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        before = p.read_text()
        after = (before
                 .replace(f"{OLD_OWNER}.github.io/{OLD_REPO}", f"{owner.lower()}.github.io/{repo}")
                 .replace(f"{OLD_OWNER.lower()}.github.io/{OLD_REPO}", f"{owner.lower()}.github.io/{repo}")
                 .replace(f"github.com/{OLD_OWNER}/{OLD_REPO}", f"github.com/{owner}/{repo}"))
        if after != before:
            p.write_text(after)
            changed.append(rel)

    print("rewrote:", ", ".join(changed) if changed else "nothing (already repointed?)")
    subprocess.run([sys.executable, "site/build.py"], cwd=ROOT, check=True)
    print(f"\nPages URL is now https://{owner.lower()}.github.io/{repo}/")
    print("Commit and push, then enable Pages in Settings -> Pages (branch main, folder /).")


if __name__ == "__main__":
    main()
