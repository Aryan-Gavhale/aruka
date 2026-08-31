"""Report CSS classes used in templates that the stylesheet those templates load
does not define.

A hand-written stylesheet and hand-written templates drift silently: a typo in a
class name looks fine in the editor and merely renders unstyled in the browser.
Run this after touching either side.

Checked per surface rather than against both sheets pooled, because an admin page
never loads site.css. Pooling them hides exactly the mistake worth catching - an
admin template reaching for a class that only the public stylesheet has.

    python Tools/audit_classes.py            every surface
    python Tools/audit_classes.py admin      one of admin, public, portal
    python Tools/audit_classes.py --unused   the other direction: rules nothing uses

The unused list is advisory rather than a failure. The two honest reasons a live rule
looks unused are both accounted for: names JavaScript builds are read out of the
scripts, and names a template completes from data - chip--{{ status }} - are matched by
their stem. What is left over is usually genuinely dead.
"""

from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Which stylesheet each folder of templates actually links. The portal shares the
# public sheet deliberately, so a client moving between the two sees one design.
SURFACES = {
    "admin": ("static/css/admin.css",),
    "public": ("static/css/site.css",),
    "portal": ("static/css/site.css",),
}

# Templates outside those folders are shared partials, included from a page on one
# surface or another, so they are checked against every sheet at once.
SHARED = tuple(sorted({sheet for sheets in SURFACES.values() for sheet in sheets}))


def js_classes() -> set[str]:
    """Names the scripts add, which a template will never show.

    Read out of the scripts rather than kept in a list here, because a list here goes
    stale the first time someone renames a state class in the JavaScript.
    """
    names: set[str] = set()
    for path in sorted((ROOT / "static" / "js").glob("*.js")):
        text = path.read_text(encoding="utf-8")
        for call in re.findall(r"classList\.(?:add|remove|toggle|contains)\(([^)]*)\)", text):
            names |= {m.group(1) or m.group(2) for m in LITERAL.finditer(call)}
        for value in re.findall(r"className\s*=\s*'([^']*)'|className\s*=\s*\"([^\"]*)\"", text):
            names |= set(" ".join(value).split())
        # Selectors: $('.card__x'), closest('.col'), matches('.in.is-bad')
        for selector in re.findall(r"['\"]([.#][^'\"]*)['\"]", text):
            names |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", selector))
    return names


def defined(sheets) -> set[str]:
    names: set[str] = set()
    for sheet in sheets:
        path = ROOT / sheet
        if not path.exists():
            continue
        text = re.sub(r"/\*.*?\*/", " ", path.read_text(encoding="utf-8"), flags=re.S)
        # Quoted values are content strings and inline SVG data URIs. Both are full of
        # dotted words - w3.org inside an arrow icon reads as a class called .org.
        text = re.sub(r"'[^']*'|\"[^\"]*\"", " ", text)
        text = re.sub(r"url\([^)]*\)", " ", text)
        names |= set(re.findall(r"\.(-?[A-Za-z_][\w-]*)", text))
    return names


LITERAL = re.compile(r"'([^']*)'|\"([^\"]*)\"")
CALL = re.compile(r"(?:\bin\s*|[\w.]+\s*)\(")


def _drop_calls(expression: str) -> str:
    """Remove every call and its arguments, parentheses balanced.

    A regex cannot do this on its own because the arguments themselves contain
    parentheses: key.startswith(('price', 'cost')) is a tuple inside a call, and the
    tuple's contents are column names rather than class names.
    """
    while True:
        match = CALL.search(expression)
        if not match:
            return expression
        depth, end = 0, len(expression)
        for i in range(match.end() - 1, len(expression)):
            if expression[i] == "(":
                depth += 1
            elif expression[i] == ")":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        expression = expression[:match.start()] + " " + expression[end:]


def _literals(expression: str) -> str:
    """The class names inside a Jinja expression, which is where the conditional ones live.

    Everything that is not a class name has to come out first, or the real findings
    are buried under settings keys and column names:

        S('theme.animations')          a settings key, not a class
        key.startswith(('price',))     a column-name test
        item.url | trim('/')           a filter argument
        row.kind == 'invoice'          the value being compared against
    """
    cleaned = _drop_calls(expression)
    cleaned = re.sub(r"[=!]=\s*('[^']*'|\"[^\"]*\")", " ", cleaned)
    # Matched as alternatives rather than one class, so that an empty '' consumes its
    # own pair of quotes instead of pairing with the next literal's opening quote and
    # turning the words between them into class names.
    return " ".join(m.group(1) if m.group(1) is not None else m.group(2)
                    for m in LITERAL.finditer(cleaned))


def _tokens(paths):
    """Every whitespace-separated word of every class attribute in these templates."""
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(r'class="([^"]*)"', text):
            chunk = re.sub(r"\{\{(.*?)\}\}", lambda m: _literals(m.group(1)),
                           match.group(1), flags=re.S)
            chunk = re.sub(r"\{%.*?%\}", " ", chunk, flags=re.S)
            yield from chunk.split()


def used(paths) -> Counter:
    counts: Counter = Counter()
    for token in _tokens(paths):
        # A trailing separator means the name was completed by an interpolation, so
        # the stem alone is not a class.
        if token and not any(c in token for c in "{}~|") \
                and not token.endswith(("-", "_")):
            counts[token] += 1
    return counts


def stems(paths) -> set[str]:
    """The half-written names, where the rest comes from the data.

    chip--{{ row.status }} cannot be resolved without the database, so every rule
    beginning chip-- counts as reachable. Only stems carrying a separator are taken,
    so this widens to a modifier set and never to a whole prefix.
    """
    found: set[str] = set()
    for token in _tokens(paths):
        head = re.split(r"[{}~|]", token, 1)[0]
        if head != token or token.endswith(("-", "_")):
            if head.endswith(("-", "_")) and re.fullmatch(r"-?[A-Za-z_][\w-]*", head):
                found.add(head)
    return found


def _templates(folder: str):
    base = ROOT / "templates"
    if folder:
        return sorted((base / folder).glob("**/*.html"))
    return sorted(p for p in base.glob("*.html"))


def _unused() -> int:
    """Rules nothing reaches, per stylesheet."""
    paths = sorted((ROOT / "templates").glob("**/*.html"))
    everywhere = set(used(paths)) | js_classes()
    prefixes = tuple(sorted(stems(paths)))
    # A numbered set - pan--1 to pan--12 - is written out once and drawn from as
    # layouts need it. If any width is in use the set is in use.
    counted = {re.sub(r"\d+$", "", name) for name in everywhere if name[-1:].isdigit()}
    for sheet in SHARED:
        # Element and pseudo-class selectors are not classes, so only the class part
        # of the sheet is comparable with what the templates say.
        spare = sorted(name for name in defined([sheet]) - everywhere
                       if not name.startswith(prefixes)
                       and re.sub(r"\d+$", "", name) not in counted)
        print(f"\n{Path(sheet).name}: {len(spare)} class(es) nothing reaches")
        for name in spare:
            print(f"  .{name}")
    return 0


def main() -> int:
    if "--unused" in sys.argv:
        return _unused()

    only = sys.argv[1] if len(sys.argv) > 1 else ""
    if only and only not in SURFACES:
        print(f"unknown surface {only!r}: choose one of {', '.join(SURFACES)}")
        return 2

    groups = [(name, sheets) for name, sheets in SURFACES.items()
              if not only or name == only]
    if not only:
        groups.append(("shared partials", SHARED))

    total, problems = 0, 0
    for name, sheets in groups:
        paths = _templates("" if name == "shared partials" else name)
        counts = used(paths)
        total += len(counts)
        unknown = {n: c for n, c in counts.items()
                   if n not in defined(sheets) | js_classes()}
        sheet_names = ", ".join(Path(s).name for s in sheets)
        if not unknown:
            print(f"OK - {name}: all {len(counts)} classes are in {sheet_names}")
            continue
        problems += len(unknown)
        print(f"\n{name}: {len(unknown)} class(es) not in {sheet_names}")
        for cls, n in sorted(unknown.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {n:4}  .{cls}")

    if problems:
        print(f"\n{problems} undefined class(es) across {total} used")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
