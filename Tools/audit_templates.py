"""Report templates a route renders that do not exist, and files nothing renders.

    python Tools/audit_templates.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Rendered by name built at runtime, or included from another template rather than
# by a route.
INDIRECT = {"admin/_fields.html", "admin/_icons.html", "admin/_picker.html",
            "admin/base.html", "admin/crud_form.html", "admin/crud_list.html",
            "public/base.html", "portal/base.html"}


def python_files():
    yield ROOT / "app.py"
    for folder in ("blueprints", "core", "services"):
        yield from (ROOT / folder).rglob("*.py")


def rendered() -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for path in python_files():
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"""render_template\(\s*\n?\s*['"]([\w/._-]+)['"]""", text):
            out.setdefault(match.group(1), set()).add(
                str(path.relative_to(ROOT)).replace("\\", "/"))
    return out


def existing() -> set[str]:
    base = ROOT / "templates"
    return {str(p.relative_to(base)).replace("\\", "/")
            for p in base.rglob("*.html")}


def extended() -> set[str]:
    """Templates named by extends/include/import, which a route never mentions."""
    out: set[str] = set()
    for path in (ROOT / "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r"""\{%-?\s*(?:extends|include|from|import)\s+['"]([\w/._-]+)['"]""",
                                 text):
            out.add(match.group(1))
    return out


def main() -> int:
    have = existing()
    want = rendered()
    linked = extended()

    missing = {name: files for name, files in want.items() if name not in have}
    orphan = sorted(have - set(want) - linked - INDIRECT)

    if missing:
        print(f"{len(missing)} template(s) a route renders but no file exists:")
        for name, files in sorted(missing.items()):
            print(f"  {name}")
            for file in sorted(files):
                print(f"      {file}")
    else:
        print(f"OK - all {len(want)} rendered templates exist ({len(have)} files)")

    if orphan:
        print(f"\n{len(orphan)} file(s) nothing renders or includes:")
        for name in orphan:
            print(f"  {name}")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
