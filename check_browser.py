"""Browser checks: what a real visitor's browser actually does with the pages.

check_routes.py proves the server returns the right bytes. This proves the bytes
behave - that the CSS loads, the JavaScript parses, nothing logs an error to the
console, the animations run, the calculator retotals as boxes are ticked, the
kanban card stays where it was dropped, and that a visitor who has asked their
operating system for less motion gets a still page rather than a broken one.

Four passes, because those are the four ways the site gets looked at:

    desktop   1440x900, motion allowed - the full animation set
    mobile    390x844 touch, the drawer and the stacked layouts
    motion    prefers-reduced-motion: reduce - nothing may move
    admin     signed in, the panel's own interactions

    pip install playwright && playwright install chromium
    python app.py            (in another terminal)
    python check_browser.py
    python check_browser.py --headed --slow    watch it happen
"""

from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

BASE = "http://127.0.0.1:8140"
ROOT = Path(__file__).resolve().parent
DB = ROOT / "db" / "aruka.db"
MARK = "Browser"

problems = 0

# Chromium says these to itself. Nothing here is the site's fault, and failing on
# them would make the check useless noise.
IGNORED_CONSOLE = (
    "favicon",
    "Failed to load resource: net::ERR_FILE_NOT_FOUND",
    "Download the React DevTools",
)


def check(label: str, ok: bool, detail: str = "") -> None:
    global problems
    print(f"{'ok  ' if ok else 'FAIL'} {label}")
    if not ok:
        problems += 1
        if detail:
            print("      " + re.sub(r"\s+", " ", str(detail))[:400])


def sql(statement: str, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(statement, args).fetchall()
        conn.commit()
        return rows
    finally:
        conn.close()


def scalar(statement: str, args=()):
    rows = sql(statement, args)
    return rows[0][0] if rows else None


def credentials() -> tuple[str, str]:
    stamp = ROOT / "db" / "first-login.txt"
    if stamp.exists():
        lines = [line.strip() for line in stamp.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
        if len(lines) >= 2:
            return lines[0], lines[1]
    import json
    config = ROOT / "config.json"
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            if data.get("owner_password"):
                return data.get("owner_email", "owner@aruka.local"), data["owner_password"]
        except ValueError:
            pass
    return "owner@aruka.local", "aruka-owner-2026"


class Watcher:
    """Collects everything the browser complains about, per page."""

    def __init__(self, page):
        self.messages: list[str] = []
        page.on("console", self._console)
        page.on("pageerror", lambda exc: self.messages.append(f"pageerror: {exc}"))
        page.on("requestfailed", self._failed)

    def _console(self, message) -> None:
        if message.type not in ("error", "warning"):
            return
        text = message.text
        if any(skip in text for skip in IGNORED_CONSOLE):
            return
        self.messages.append(f"console {message.type}: {text}")

    def _failed(self, request) -> None:
        if any(skip in request.url for skip in IGNORED_CONSOLE):
            return
        self.messages.append(f"failed to load: {request.url}")

    def drain(self) -> list[str]:
        out, self.messages = self.messages, []
        return out


def scroll_to(page, y) -> None:
    """Jump the page, not glide it.

    The site sets scroll-behavior: smooth, so a plain scrollTo animates for the best
    part of a second and anything measured straight afterwards reads a position the
    page is still travelling through. Force the jump, then wait for it to land.
    """
    page.evaluate("(y) => window.scrollTo({top: y === 'end' ?"
                  " document.documentElement.scrollHeight : y, behavior: 'instant'})", y)
    # Clamp before comparing: asking for 4000px on a 3000px page lands at 3000, and
    # a reveal firing mid-scroll can change the page height under us either way.
    page.wait_for_function(
        """(y) => {
            const most = document.documentElement.scrollHeight - innerHeight;
            const want = Math.min(Math.max(0, most), y === 'end' ? most : y);
            return Math.abs(window.scrollY - Math.max(0, want)) < 4;
        }""", arg=y, timeout=5000)


def styled(page) -> bool:
    """Did the stylesheet actually arrive? An unstyled page still passes an HTTP check."""
    return page.evaluate(
        "() => getComputedStyle(document.body).backgroundColor !== 'rgba(0, 0, 0, 0)'"
        " && getComputedStyle(document.querySelector('h1, h2') || document.body).fontSize"
        " !== '16px'")


# ── the desktop pass ────────────────────────────────────────────────────────
def desktop(browser, headed: bool) -> None:
    print("\n-- desktop, 1440x900, motion allowed --")
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    watch = Watcher(page)

    for path in ("/", "/services", "/work", "/about", "/insights", "/pricing", "/contact",
                 "/support", "/legal/privacy-policy"):
        page.goto(BASE + path, wait_until="load")
        page.wait_for_timeout(250)
        noise = watch.drain()
        check(f"{path} loads with a clean console", not noise, "; ".join(noise))

    page.goto(BASE + "/", wait_until="load")
    check("the stylesheet is applied", styled(page))
    check("the script ran, so the no-js fallback is off",
          not page.evaluate("() => document.documentElement.classList.contains('no-js')"))

    # ── the animation set ───────────────────────────────────────────────────
    check("the hero headline was split into words for the rise-in",
          page.locator(".hero [data-split] .w").count() > 2,
          page.locator("[data-split] .w").count())

    rot = page.locator(".rot__i.is-on")
    if page.locator(".rot__i").count() > 1:
        first = rot.first.inner_text()
        page.wait_for_timeout(3200)
        check("the rotating word actually rotates",
              page.locator(".rot__i.is-on").first.inner_text() != first, first)

    # Reveals: what is on screen is already revealed, what is below is not, and
    # scrolling to it reveals it. That is the whole contract of the observer.
    above = page.evaluate("""() => {
        const list = Array.from(document.querySelectorAll('.r'));
        const onScreen = list.filter(el => el.getBoundingClientRect().top < innerHeight);
        const below = list.filter(el => el.getBoundingClientRect().top > innerHeight + 400);
        return {
            total: list.length,
            onScreenHidden: onScreen.filter(el => !el.classList.contains('r-on')).length,
            belowHidden: below.filter(el => !el.classList.contains('r-on')).length,
            below: below.length,
        };
    }""")
    check("there is something to reveal", above["total"] > 4, above)
    check("what is already on screen is visible at once", above["onScreenHidden"] == 0, above)
    check("what is below the fold is still waiting", above["belowHidden"] > 0, above)

    # Walk down rather than teleport. The observer only fires for what crosses the
    # viewport, which is also what a reader does, so a jump to the footer would
    # legitimately leave the middle of the page unrevealed.
    height = page.evaluate("() => innerHeight")
    for step in range(1, 40):
        scroll_to(page, step * int(height * 0.7))
        page.wait_for_timeout(120)
        if page.evaluate("() => window.scrollY + innerHeight >= "
                         "document.documentElement.scrollHeight - 4"):
            break
    page.wait_for_timeout(900)
    check("scrolling down reveals the rest",
          page.evaluate("() => Array.from(document.querySelectorAll('.r'))"
                        ".filter(el => !el.classList.contains('r-on')).length") == 0,
          page.evaluate("() => Array.from(document.querySelectorAll('.r'))"
                        ".filter(el => !el.classList.contains('r-on'))"
                        ".map(el => el.className).slice(0, 4).join(' | ')"))

    check("the header condensed once the page moved",
          page.evaluate("() => document.querySelector('.hdr').classList.contains('is-stuck')"))
    scroll_to(page, 0)
    page.wait_for_timeout(250)
    check("and expanded again at the top",
          not page.evaluate(
              "() => document.querySelector('.hdr').classList.contains('is-stuck')"))

    counted = page.evaluate("""() => {
        const el = document.querySelector('[data-count]');
        if (!el) return {skip: true};
        return {skip: false, shown: el.textContent.trim(), target: el.dataset.count};
    }""")
    if not counted["skip"]:
        check("the counters finished on their real number",
              counted["shown"].replace(",", "").startswith(
                  counted["target"].split(".")[0].replace(",", "")),
              counted)

    check("the marquee was doubled so the loop has no seam",
          page.evaluate("() => { const t = document.querySelector('.marq__t');"
                        " return !t || t.children.length === 2; }"))

    # The stroke is hidden by a dash offset the length of the path itself, so the
    # measuring has to have happened before the reveal or the line never appears.
    flourish = page.locator(".draw").first
    if flourish.count():
        flourish.scroll_into_view_if_needed()
        page.wait_for_timeout(1400)
        drawn = page.evaluate("""() => {
            const shapes = Array.from(document.querySelectorAll('.draw path, .draw line'));
            const off = shapes.map(s => Number(
                getComputedStyle(s).strokeDashoffset.replace('px', '')) || 0);
            return {total: shapes.length,
                    measured: shapes.filter(s => s.style.getPropertyValue('--len')).length,
                    on: document.querySelector('.draw').classList.contains('r-on'),
                    off: off};
        }""")
        check("the SVG paths were measured for the draw-in",
              drawn["measured"] == drawn["total"] and drawn["total"] > 0, drawn)
        check("the drawn line finished at full length",
              drawn["on"] and all(v < 1 for v in drawn["off"]), drawn)

    box = page.locator(".card").first
    if box.count():
        before = box.evaluate("el => el.style.getPropertyValue('--mx')")
        box.scroll_into_view_if_needed()
        box.hover()
        page.wait_for_timeout(150)
        check("the cursor glow follows the pointer across a card",
              box.evaluate("el => el.style.getPropertyValue('--mx')") != before)

    # The reading progress bar only exists where there is something to read.
    post = scalar("SELECT slug FROM posts WHERE is_published = 1 ORDER BY id LIMIT 1")
    if post:
        page.goto(f"{BASE}/insights/{post}", wait_until="load")
        check("a long read has a progress bar", page.locator(".bar").count() == 1)
        scroll_to(page, "end")
        page.wait_for_timeout(400)
        check("the progress bar fills as the article is read",
              page.evaluate("() => parseFloat(document.querySelector('.bar').style.width)") > 80,
              page.evaluate("() => document.querySelector('.bar').style.width"))

    # ── the FAQ accordion ───────────────────────────────────────────────────
    page.goto(BASE + "/pricing", wait_until="load")
    q = page.locator(".faq__q").first
    if q.count():
        check("a closed answer reports itself closed to a screen reader",
              q.get_attribute("aria-expanded") == "false")
        q.click()
        page.wait_for_timeout(450)
        check("clicking a question opens it",
              q.get_attribute("aria-expanded") == "true"
              and page.locator(".faq__i.is-open .faq__a").first.evaluate(
                  "el => el.offsetHeight") > 10)
        others = page.locator(".faq__q").nth(1)
        if others.count():
            others.click()
            page.wait_for_timeout(450)
            check("opening a second question closes the first",
                  page.locator(".faq__i.is-open").count() == 1,
                  page.locator(".faq__i.is-open").count())

    # ── the public calculator ───────────────────────────────────────────────
    calc = page.locator("#calc")
    if calc.count():
        total = page.locator("[data-out=total]")
        page.wait_for_function("() => document.querySelector('[data-out=total]')"
                              ".textContent.replace(/\\D/g, '').length > 2")
        opening = total.inner_text()
        check("the calculator shows a total before anything is touched",
              re.sub(r"\D", "", opening) != "", opening)

        if page.locator("#calc input[name=rush]").count():
            tick(page, "#calc input[name=rush]")
            page.wait_for_timeout(700)
            check("ticking a rush job puts the total up",
                  _rupees(total.inner_text()) > _rupees(opening),
                  f"{opening} -> {total.inner_text()}")
            check("the surcharge line appeared with it",
                  page.locator("[data-row=surcharge]").first.is_visible())

        check("it proposes a payment schedule",
              page.locator("[data-out=milestones] .ms__i").count() >= 2,
              page.locator("[data-out=milestones] .ms__i").count())
        check("the itemised lines are listed",
              page.locator("[data-out=lines] li").count() >= 2)
        # What the panel shows the owner must not reach the public page.
        check("the public calculator never shows the cost or the margin",
              page.evaluate("() => !document.querySelector('[data-calc-cost],"
                            "[data-calc-margin],[data-calc-margin-box]')")
              and not re.search(r"\b(internal cost|costs you|margin:)\b",
                                page.inner_text("body"), re.I))

    noise = watch.drain()
    check("nothing was logged to the console through all of that", not noise, "; ".join(noise))
    if headed:
        page.wait_for_timeout(1200)
    context.close()


def _rupees(text: str) -> float:
    digits = re.sub(r"[^\d.]", "", text or "")
    return float(digits) if digits else 0.0


def tick(page, selector: str, on: bool = True) -> None:
    """Set a checkbox the way a person does: by clicking its label.

    Every tickbox in this project is drawn by a sibling span inside its own label, so
    the input itself is either covered by that span or laid out at zero size. Clicking
    the label is both what a visitor does and the only thing that reliably works.
    """
    box = page.locator(selector).first
    if box.is_checked() == on:
        return
    label = box.locator("xpath=ancestor::label[1]")
    if not label.count():
        label = page.locator(f'label[for="{box.get_attribute("id")}"]')
    target = label.first if label.count() else box
    target.scroll_into_view_if_needed()
    target.click(force=True)
    page.wait_for_function("([sel, on]) => document.querySelector(sel).checked === on",
                           arg=[selector, on], timeout=5000)


def submit(page, form: str) -> None:
    """Submit one named form and wait for the page it lands on.

    Never `button[type=submit]` on an admin page. The sidebar's sign-out sits in its
    own form above the content, so the first submit button on every screen in the
    panel logs you out - which then quietly passes every later check, because a
    sign-in page has no console errors either.
    """
    page.locator(f"{form} button[type=submit], {form} input[type=submit]").first.click()
    page.wait_for_load_state("load")


# ── the mobile pass ─────────────────────────────────────────────────────────
def mobile(browser, headed: bool) -> None:
    print("\n-- mobile, 390x844, touch --")
    context = browser.new_context(
        viewport={"width": 390, "height": 844}, device_scale_factor=3,
        is_mobile=True, has_touch=True,
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
    page = context.new_page()
    watch = Watcher(page)

    for path in ("/", "/services", "/pricing", "/contact", "/work"):
        page.goto(BASE + path, wait_until="load")
        page.wait_for_timeout(200)
        noise = watch.drain()
        check(f"{path} loads clean on a phone", not noise, "; ".join(noise))
        wide = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        check(f"{path} does not scroll sideways", wide <= 1, f"{wide}px over")

    page.goto(BASE + "/", wait_until="load")
    burger = page.locator(".burger")
    check("the menu button is the visible navigation on a phone", burger.is_visible())
    check("the desktop navigation is out of the way",
          not page.locator("header .nav").first.is_visible())

    check("the drawer starts closed", burger.get_attribute("aria-expanded") == "false")
    burger.click()
    page.wait_for_timeout(400)
    check("tapping it opens the drawer",
          page.locator(".drawer.is-open").count() == 1
          and burger.get_attribute("aria-expanded") == "true")
    check("the page behind the drawer cannot scroll",
          page.evaluate("() => getComputedStyle(document.body).overflow") == "hidden")

    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    check("escape closes it again", page.locator(".drawer.is-open").count() == 0)
    check("and the page scrolls once more",
          page.evaluate("() => getComputedStyle(document.body).overflow") != "hidden")

    burger.click()
    page.wait_for_timeout(300)
    page.locator(".drawer a").first.click()
    page.wait_for_load_state("load")
    check("following a link from the drawer closes it",
          page.locator(".drawer.is-open").count() == 0)

    # Tap targets. Anything a thumb has to hit needs to be big enough to hit.
    page.goto(BASE + "/contact", wait_until="load")
    small = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('.btn, button[type=submit]').forEach(el => {
            const box = el.getBoundingClientRect();
            if (box.width === 0 || box.height === 0) return;
            if (box.height < 40) out.push((el.textContent || el.className)
                .trim().slice(0, 28) + ' ' + Math.round(box.height) + 'px');
        });
        return out;
    }""")
    check("every button is big enough for a thumb", not small, "; ".join(small[:6]))

    # The honeypot is deliberately off-screen and a tickbox has its own size rules,
    # so neither belongs in a typing-target measurement.
    typed = ("input:not([type=hidden]):not([type=checkbox]):not([type=radio])"
             ":not(.hp *):not(.hp), textarea, select")
    fields = page.evaluate("""(sel) => {
        const out = [];
        document.querySelectorAll('form ' + sel).forEach(el => {
            if (el.closest('.hp')) return;
            const box = el.getBoundingClientRect();
            if (box.width > 0 && box.height < 38) out.push(el.name + ' ' + Math.round(box.height));
        });
        return out;
    }""", typed)
    check("form fields are tall enough to tap into", not fields, "; ".join(fields[:6]))

    # iOS zooms the page when a field's text is under 16px. Nothing else undoes it.
    tiny = page.evaluate("""(sel) => {
        const out = [];
        document.querySelectorAll(sel).forEach(el => {
            if (el.closest('.hp')) return;
            const size = parseFloat(getComputedStyle(el).fontSize);
            if (size < 16) out.push(el.name + ' ' + size + 'px');
        });
        return out;
    }""", typed)
    check("no field is small enough to make iOS zoom in", not tiny, "; ".join(tiny[:6]))

    noise = watch.drain()
    check("the phone console stayed quiet", not noise, "; ".join(noise))
    if headed:
        page.wait_for_timeout(1200)
    context.close()


# ── the reduced-motion pass ─────────────────────────────────────────────────
def motion(browser, headed: bool) -> None:
    print("\n-- prefers-reduced-motion: reduce --")
    context = browser.new_context(viewport={"width": 1440, "height": 900},
                                  reduced_motion="reduce")
    page = context.new_page()
    watch = Watcher(page)
    page.goto(BASE + "/", wait_until="load")
    page.wait_for_timeout(400)

    # The point of the reduced-motion path is not that things are hidden. It is
    # that everything is already in its finished state.
    check("every reveal is shown at once, none left waiting",
          page.evaluate("() => Array.from(document.querySelectorAll('.r'))"
                        ".filter(el => !el.classList.contains('r-on')).length") == 0)

    check("no element is left transparent",
          page.evaluate("""() => Array.from(document.querySelectorAll('.r, .hero h1, .card'))
              .filter(el => parseFloat(getComputedStyle(el).opacity) < 0.9).length""") == 0)

    check("nothing is left shifted off its own position",
          page.evaluate("""() => Array.from(document.querySelectorAll('.r'))
              .filter(el => {
                  const t = getComputedStyle(el).transform;
                  return t !== 'none' && !t.startsWith('matrix(1, 0, 0, 1, 0, 0)');
              }).length""") == 0)

    durations = page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('*').forEach(el => {
            const style = getComputedStyle(el);
            const move = [style.transitionDuration, style.animationDuration]
                .join(' ').split(/[,\\s]+/).filter(Boolean)
                .some(v => parseFloat(v) > 0.05);
            if (move && style.animationName !== 'none' || (move && el.classList.contains('r'))) {
                out.push(el.tagName.toLowerCase() + '.' + (el.className || '').slice(0, 30));
            }
        });
        return out.slice(0, 8);
    }""")
    check("nothing is still animating", not durations, "; ".join(durations))

    counted = page.evaluate("""() => {
        const el = document.querySelector('[data-count]');
        return el ? {shown: el.textContent.trim(), target: el.dataset.count} : null;
    }""")
    if counted:
        check("counters print their number instead of racing to it",
              counted["shown"].replace(",", "").startswith(
                  counted["target"].split(".")[0]), counted)

    rot_first = page.locator(".rot__i.is-on").first.inner_text() \
        if page.locator(".rot__i.is-on").count() else ""
    page.wait_for_timeout(3200)
    if rot_first:
        check("the rotating headline holds still",
              page.locator(".rot__i.is-on").first.inner_text() == rot_first, rot_first)

    scroll_to(page, 600)
    page.wait_for_timeout(300)
    check("parallax layers do not move",
          page.evaluate("""() => Array.from(document.querySelectorAll('[data-para]'))
              .filter(el => el.style.transform && el.style.transform !== 'none').length""") == 0)

    # The bar is orientation, not decoration, so it is expected to still work.
    check("the reading progress bar still tracks the scroll",
          page.evaluate("() => { const b = document.querySelector('.bar');"
                        " return !b || parseFloat(b.style.width) > 0; }"))

    # And the site still has to work.
    page.goto(BASE + "/pricing", wait_until="load")
    q = page.locator(".faq__q").first
    if q.count():
        q.click()
        page.wait_for_timeout(250)
        check("the accordion still opens with motion off",
              q.get_attribute("aria-expanded") == "true")
    if page.locator("#calc").count():
        page.wait_for_function("() => document.querySelector('[data-out=total]')"
                              ".textContent.replace(/\\D/g, '').length > 2")
        check("the calculator still totals with motion off",
              _rupees(page.locator("[data-out=total]").inner_text()) > 0)

    noise = watch.drain()
    check("the reduced-motion pass logged nothing", not noise, "; ".join(noise))
    if headed:
        page.wait_for_timeout(1200)
    context.close()


# ── the admin pass ──────────────────────────────────────────────────────────
def admin(browser, headed: bool) -> None:
    print("\n-- the panel, signed in --")
    email, password = credentials()
    context = browser.new_context(viewport={"width": 1600, "height": 1000})
    page = context.new_page()
    watch = Watcher(page)

    page.goto(BASE + "/admin/login", wait_until="load")
    page.fill("input[name=email]", email)
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_load_state("load")
    if not page.locator(".side__brand").count():
        check(f"signing in as {email}", False,
              "put the password in config.json, or reset it with "
              f"python app.py user {email} Owner <password> owner")
        context.close()
        return
    check(f"signing in as {email}", True)

    for path in ("/admin/", "/admin/leads/board", "/admin/quotes/new", "/admin/analytics",
                 "/admin/vault", "/admin/settings/theme", "/admin/media",
                 "/admin/documents/new", "/admin/invoices/new", "/admin/tickets/new"):
        page.goto(BASE + path, wait_until="load")
        page.wait_for_timeout(200)
        noise = watch.drain()
        check(f"{path} loads with a clean console", not noise, "; ".join(noise))

    page.goto(BASE + "/admin/", wait_until="load")
    check("the panel is styled", styled(page))

    # ── a lead, so the board and the calculator have something real ─────────
    page.goto(BASE + "/admin/leads/new", wait_until="load")
    page.fill("input[name=name]", f"{MARK} Deshpande")
    page.fill("input[name=email]", "browser@example.invalid")
    page.fill("input[name=phone]", "9800000007")
    submit(page, "form.pan")
    lead_id = scalar("SELECT id FROM leads WHERE name LIKE ? ORDER BY id DESC LIMIT 1",
                     (f"{MARK}%",))
    check("a lead can be created through the form", bool(lead_id),
          "; ".join(page.locator(".flash, .msg--bad").all_inner_texts()) or page.url)
    check("and the panel did not sign us out along the way",
          page.locator(".side__brand").count() == 1)

    # ── the kanban ──────────────────────────────────────────────────────────
    if lead_id:
        page.goto(BASE + "/admin/leads/board", wait_until="load")
        card = page.locator(f'[data-lead="{lead_id}"]')
        check("the new lead is on the board", card.count() == 1, card.count())
        if card.count():
            target = page.locator('[data-stage="qualified"] .col__b, [data-stage="qualified"]').first
            card.hover()
            page.mouse.down()
            target.hover()
            page.mouse.move(*_centre(target.bounding_box()))
            page.mouse.up()
            page.wait_for_timeout(900)
            check("dropping a card in another column moves the lead",
                  scalar("SELECT stage FROM leads WHERE id = ?", (lead_id,)) == "qualified",
                  scalar("SELECT stage FROM leads WHERE id = ?", (lead_id,)))
            page.reload(wait_until="load")
            check("and it is still there after a reload",
                  page.locator(f'[data-stage="qualified"] [data-lead="{lead_id}"]').count() == 1)

    # ── the admin calculator ────────────────────────────────────────────────
    page.goto(BASE + "/admin/quotes/new", wait_until="load")
    if page.locator("form[data-calc]").count():
        page.wait_for_function("() => document.querySelector('[data-calc-total]')"
                              ".textContent.replace(/\\D/g, '').length > 2")
        total = page.locator("[data-calc-total]")
        opening = total.inner_text()
        check("the quote builder prices as soon as it opens", _rupees(opening) > 0, opening)
        check("the owner's own cost and margin are on this one, unlike the public page",
              page.locator("[data-calc-margin]").count() == 1
              and _rupees(page.locator("[data-calc-cost]").inner_text()) > 0,
              page.locator("[data-calc-cost]").inner_text())
        check("the margin is the difference between the two",
              abs((_rupees(opening) - _rupees(page.locator("[data-calc-cost]").inner_text()))
                  - _rupees(page.locator("[data-calc-margin]").inner_text())) < 2,
              f"{opening} - {page.locator('[data-calc-cost]').inner_text()} "
              f"!= {page.locator('[data-calc-margin]').inner_text()}")

        pages_field = page.locator("form[data-calc] input[name=pages]")
        if pages_field.count():
            pages_field.fill("30")
            pages_field.dispatch_event("change")
            page.wait_for_timeout(900)
            check("more pages costs more", _rupees(total.inner_text()) > _rupees(opening),
                  f"{opening} -> {total.inner_text()}")

        if page.locator("form[data-calc] input[name=rush]").count():
            tick(page, "form[data-calc] input[name=rush]")
            page.wait_for_timeout(900)
            check("the rush line appears once a rush job is asked for",
                  page.locator("[data-calc-surcharge]").first.is_visible())

        check("it lays out the payment schedule",
              page.locator("[data-calc-milestones] li, [data-calc-milestones] .ms__i")
              .count() >= 2,
              page.locator("[data-calc-milestones] li").count())

    # ── the vault reveal ────────────────────────────────────────────────────
    # The reveal is the one place in the panel where a decrypted password reaches the
    # browser, so it is worth proving it is not simply sitting in the HTML.
    secret = "not-a-real-password-8x"
    page.goto(BASE + "/admin/clients/new", wait_until="load")
    page.fill("input[name=name]", f"{MARK} Traders")
    if page.locator("input[name=phone]").count():
        page.fill("input[name=phone]", "9800000008")
    submit(page, "form[data-guard]")
    client_id = scalar("SELECT id FROM clients WHERE name LIKE ? ORDER BY id DESC LIMIT 1",
                       (f"{MARK}%",))
    check("a client can be created through the form", bool(client_id),
          "; ".join(page.locator(".flash").all_inner_texts()) or page.url)

    if client_id:
        page.goto(BASE + "/admin/vault", wait_until="load")
        page.locator("summary", has_text="Store a credential").first.click()
        page.select_option("#c-client", str(client_id))
        page.fill("#c-label", f"{MARK} panel")
        page.fill("#c-user", "browser")
        page.fill("#c-secret", secret)
        submit(page, "form[action*='credential']")
        row_id = scalar("SELECT id FROM credentials WHERE label LIKE ? ORDER BY id DESC "
                        "LIMIT 1", (f"{MARK}%",))
        check("a credential saves from the vault form", bool(row_id),
              "; ".join(page.locator(".flash").all_inner_texts()) or page.url)
        if row_id:
            check("the stored password is nowhere in the page source",
                  secret not in page.content())
            page.locator(f'[data-reveal="{row_id}"]').first.click()
            page.wait_for_selector(f'[data-secret-for="{row_id}"]:not([hidden])',
                                   timeout=5000)
            check("asking to see it fetches it in without a page reload",
                  page.locator(f'[data-secret-for="{row_id}"]').inner_text() == secret,
                  page.locator(f'[data-secret-for="{row_id}"]').inner_text())
            check("and looking at it is written to the activity log",
                  bool(scalar("SELECT id FROM audit_log WHERE entity = 'credentials' "
                              "AND entity_id = ? AND action = 'view'", (row_id,))))
            page.locator(f'[data-reveal="{row_id}"]').first.click()
            page.wait_for_timeout(300)
            check("pressing it again puts the password away",
                  page.locator(f'[data-secret-for="{row_id}"]').is_hidden())

    # ── the theme switch, which is what writes html.no-anim ────────────────
    def set_animations(on: bool) -> None:
        page.goto(BASE + "/admin/settings/theme", wait_until="load")
        tick(page, "input[name='theme.animations']", on)
        submit(page, "form[data-guard]")

    page.goto(BASE + "/admin/settings/theme", wait_until="load")
    switch = page.locator("input[name='theme.animations']")
    if switch.count():
        was = switch.first.is_checked()
        set_animations(False)
        public = context.new_page()
        public.goto(BASE + "/", wait_until="load")
        public.wait_for_timeout(400)
        check("turning animations off in the panel stills the public site",
              public.evaluate("() => document.documentElement.classList.contains('no-anim')"))
        check("and every reveal is shown rather than left hidden",
              public.evaluate("() => Array.from(document.querySelectorAll('.r'))"
                              ".filter(el => !el.classList.contains('r-on')).length") == 0)
        rot = public.locator(".rot__i.is-on")
        if rot.count():
            first = rot.first.inner_text()
            public.wait_for_timeout(3200)
            check("and the rotating headline stops rotating",
                  public.locator(".rot__i.is-on").first.inner_text() == first, first)
        public.close()

        set_animations(was)
        check("the switch goes back where it was",
              page.locator("input[name='theme.animations']").first.is_checked() == was)

    noise = watch.drain()
    check("the panel logged nothing through all of that", not noise, "; ".join(noise))

    purge()
    if headed:
        page.wait_for_timeout(1500)
    context.close()


def _centre(box) -> tuple[float, float]:
    return (box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def purge() -> None:
    """Remove what this script made. Everything it makes carries the word Browser."""
    for lead in sql("SELECT id FROM leads WHERE name LIKE ?", (f"{MARK}%",)):
        sql("DELETE FROM lead_events WHERE lead_id = ?", (lead["id"],))
        sql("DELETE FROM quote_lines WHERE quote_id IN "
            "(SELECT id FROM quotes WHERE lead_id = ?)", (lead["id"],))
        sql("DELETE FROM quotes WHERE lead_id = ?", (lead["id"],))
        sql("DELETE FROM leads WHERE id = ?", (lead["id"],))
    for row in sql("SELECT id FROM credentials WHERE label LIKE ?", (f"{MARK}%",)):
        sql("DELETE FROM audit_log WHERE entity = 'credentials' AND entity_id = ?",
            (row["id"],))
    sql("DELETE FROM credentials WHERE label LIKE ?", (f"{MARK}%",))
    for client in sql("SELECT id FROM clients WHERE name LIKE ?", (f"{MARK}%",)):
        sql("DELETE FROM contacts WHERE client_id = ?", (client["id"],))
        sql("DELETE FROM assets WHERE client_id = ?", (client["id"],))
        sql("DELETE FROM clients WHERE id = ?", (client["id"],))
    sql("DELETE FROM notifications WHERE title LIKE ? OR body LIKE ?",
        (f"%{MARK}%", f"%{MARK}%"))
    sql("DELETE FROM audit_log WHERE label LIKE ?", (f"%{MARK}%",))
    sql("DELETE FROM login_attempts WHERE email LIKE ?", ("%example.invalid",))
    print("     (test rows removed)")


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Playwright is not installed. This check is optional:\n"
              "  pip install playwright && playwright install chromium")
        return 0

    headed = "--headed" in sys.argv
    slow = 350 if "--slow" in sys.argv else 0

    import urllib.request
    try:
        urllib.request.urlopen(BASE + "/", timeout=10).read(1)
    except Exception as exc:  # noqa: BLE001
        print(f"the site is not answering on {BASE}: {exc}")
        print("start it with:  python app.py")
        return 1

    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    passes = {"desktop": desktop, "mobile": mobile, "motion": motion, "admin": admin}

    with sync_playwright() as play:
        browser = play.chromium.launch(headless=not headed, slow_mo=slow)
        try:
            for name, fn in passes.items():
                if only and name not in only:
                    continue
                fn(browser, headed)
        finally:
            browser.close()

    print(f"\n{problems} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
