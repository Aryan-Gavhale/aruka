"""Report url_for() targets that no route answers, and routes nothing points at.

A misspelled endpoint is invisible until someone opens the page that mentions it,
and in a nav bar that means every page. Run this after adding or renaming routes.

    python Tools/audit_endpoints.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Endpoints reached only by a redirect or a fetch() in JavaScript, so no template
# names them - listed here rather than reported as dead every run.
REACHED_IN_CODE = {"static", "admin.static", "public.static", "portal.static"}

# crud.register() builds these six per resource, and the shared templates reach them
# by concatenating the resource key, so a literal name never appears.
CRUD_SUFFIXES = ("_list", "_new", "_edit", "_delete", "_toggle", "_reorder")


def endpoints() -> set[str]:
    from app import create_app

    app = create_app()
    return {rule.endpoint for rule in app.url_map.iter_rules()}


def nav_targets() -> dict[str, set[str]]:
    """The sidebar names its endpoints as bare strings, so url_for scanning misses them -
    and a typo there breaks every single page rather than one."""
    from blueprints.admin import NAV_GROUPS

    found: dict[str, set[str]] = {}
    for _group, items in NAV_GROUPS:
        for endpoint, *_rest in items:
            found.setdefault(endpoint, set()).add("blueprints/admin.py (NAV_GROUPS)")
    return found


def used() -> dict[str, set[str]]:
    """endpoint -> the files that name it."""
    found: dict[str, set[str]] = {}
    for folder in ("templates", "blueprints", "core", "services"):
        for path in (ROOT / folder).rglob("*"):
            if path.suffix not in (".html", ".py"):
                continue
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r"""url_for\(\s*['"]([\w.]+)['"]""", text):
                name = match.group(1)
                if name.endswith("."):
                    continue      # url_for('admin.' ~ res.key ~ '_list'), resolved at render
                found.setdefault(name, set()).add(
                    str(path.relative_to(ROOT)).replace("\\", "/"))
    return found


def main() -> int:
    known = endpoints()
    wanted = used()
    for name, files in nav_targets().items():
        wanted.setdefault(name, set()).update(files)

    missing = {name: files for name, files in wanted.items() if name not in known}
    unused = sorted(name for name in known - set(wanted) - REACHED_IN_CODE
                    if not name.endswith(CRUD_SUFFIXES))

    if missing:
        print(f"{len(missing)} url_for target(s) with no route:")
        for name, files in sorted(missing.items()):
            print(f"  {name}")
            for file in sorted(files):
                print(f"      {file}")
    else:
        print(f"OK - all {len(wanted)} url_for targets resolve ({len(known)} routes registered)")

    if unused:
        print(f"\n{len(unused)} route(s) nothing links to (may be fine - "
              f"POST-only, JSON or reached by redirect):")
        for name in unused:
            print(f"  {name}")

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
