# Aruka — agency site + single-owner business panel

A digital agency's website with the entire business behind it. The public site captures
the enquiry, a rules-driven calculator prices it, the document builder puts it in writing
and takes acceptance online, billing raises the invoice and records what actually arrived,
the support desk answers against a published SLA, and the analytics tab says what was left
after costs. Clients see their own side of it in a portal with no password to forget.

Built for one person running an agency in India: a bill-of-supply invoice until the day
GST registration happens, WhatsApp as the channel clients actually reply on, and money
recorded by hand because a gateway is a decision for later, not a dependency now.

Flask 3, stdlib `sqlite3`, Jinja, hand-written CSS and one plain deferred script per
surface. No build step, no JS framework, no npm.

```
python app.py reset      # create the database and load the starting rate card
python app.py            # http://127.0.0.1:8140
```

The first boot generates an owner password, prints it once and writes it to
`db/first-login.txt`. Sign in at `/admin`, change it under **Your account**, delete the
file.

---

## Setup

Python 3.10 or newer (built and checked on 3.12) and four libraries:

```
pip install -r requirements.txt
```

| Command | What it does |
| --- | --- |
| `python app.py` | Dev server on port 8140. Single process, because `debug` is off by default and the reloader follows it |
| `python app.py seed` | Apply the schema and add any seed row that is missing. Safe to run repeatedly — nothing you have edited is touched |
| `python app.py seed --force` | The same, and additionally resets **settings** to their defaults. That is the only thing a re-seed overwrites |
| `python app.py reset` | Delete the database file, then seed |
| `python app.py user <email> <name> <password> [role]` | Add or update an admin account |
| `python app.py vaultkey` | Generate `db/vault.key` up front, and print the warning about backing it up |
| `python app.py digest` | Print today's digest — what a cron job would mail you each morning |

### Configuration

Defaults live in `DEFAULT_CONFIG` in `app.py`, are overridden by `config.json` if you
create one, and then by `ARUKA_*` environment variables (`ARUKA_PORT`,
`ARUKA_SECRET_KEY`, and so on). `config.json` is gitignored, and `config.example.json` is
deliberately never read at runtime, so a placeholder secret can never become the live one
just because nobody copied the file.

The defaults are meant to be safe rather than convenient:

| Setting | Default | Why |
| --- | --- | --- |
| `secret_key` | generated into `db/secret.key` | no two installations share a key, so nobody can forge a session cookie from the source |
| `vault_key` | generated into `db/vault.key` | the credential vault's encryption key; see below |
| `owner_password` | generated, printed once, written to `db/first-login.txt` | there is no password in this repository to try |
| `debug` | `false` | the Werkzeug debugger is a remote shell; it is also forced off if `host` is not loopback |
| `https_only` | `false` | set `true` behind TLS to get `Secure` cookies and HSTS |
| `trusted_proxies` | `0` | how many `X-Forwarded-For` hops are yours; see below |
| `public_base_url` | blank | absolute host for share links and PDF footers; falls back to the request host |

All three generated files are gitignored.

**`db/vault.key` is not a copy of anything.** It encrypts the passwords stored under
**Vault**, and it lives in a file rather than the database precisely so that a stolen
database is not a stolen password list. The other side of that is that a database restored
without its key file has credentials nobody can read, including you. Back it up
separately, once, somewhere the database backup is not.

**`trusted_proxies` matters.** The public form limits, the sign-in lockout and the portal
code limit are only as trustworthy as the address they count against. With `0`, the app
uses `remote_addr` and ignores `X-Forwarded-For` entirely, because a caller can rotate
that header on every request and walk straight through any per-IP limit. Behind nginx or a
load balancer, set it to the number of proxies you control so the real client address is
read from the right position in the chain.

### Deploying

It is a normal WSGI app: `create_app()` in `app.py`. Behind gunicorn or waitress, leave
`debug` false, set `https_only` true, set `trusted_proxies` to your hop count, set
`public_base_url` so proposal links in an email point at the right host, and put
`static/uploads`, `db/aruka.db` and `db/vault.key` on persistent storage. SQLite is the
right call for one agency; the whole database is a single file you can copy.

**PythonAnywhere (free tier):** step-by-step guide in [`deploy/pythonanywhere.md`](deploy/pythonanywhere.md).
Clone the repo, run `bash deploy/setup_pythonanywhere.sh`, point the Web tab at `wsgi.py`,
and reload.

One thing wants a cron job:

```
python app.py digest      # follow-ups due, invoices overdue, SLA at risk, renewals coming
```

Renewal invoices and dunning are raised from **Recurring** and **Invoices → Aging** in the
panel rather than on a timer, on the view that a reminder going out unread at 3am is worse
than one you send having looked at the account first.

---

## The public site

Every page has its copy in the database: home, services index and a page per service, work
and a page per case study, about, insights and a page per post, contact, pricing, support,
and the four legal pages. `pages` holds meta and hero copy, `page_blocks`
holds optional extra sections, and `services`, `case_studies`, `testimonials`, `faqs`,
`posts`, `stats`, `tech_items` and `nav_items` drive everything else. Theme colours, both
fonts and the corner radius are custom properties written from Settings, so rebranding is a
form rather than a code edit.

SEO is per page: title, description, social image, canonical, and JSON-LD that changes with
the page type — `WebSite` and `Organization` on home, `Service`, `Article`, `BlogPosting`,
`FAQPage`, `ContactPage` where each belongs. `sitemap.xml` is generated from published rows
and lists nothing private; `robots.txt` blocks `/admin` and `/portal`, and turns into a
blanket disallow while **SEO → Allow indexing** is off. **SEO checklist** in the panel
scores what is actually in place rather than what was intended.

The animation set is the full one: a mesh-gradient hero, headline words rising in on a
split, a rotating word, `IntersectionObserver` reveals with staggered siblings, counters,
image parallax, card tilt with a cursor glow, magnetic CTAs, an SVG path draw, a seamless
marquee, a header that condenses and a reading progress bar on posts. All of it is behind
one gate: `prefers-reduced-motion: reduce` and the **Look → Animations on** switch both
land on the same still page, where everything is in its finished state rather than hidden.
That is what the `motion` browser pass exists to prove.

Three public forms write to the database — the enquiry, the pricing calculator and a
support ticket — and all three carry a CSRF token, a honeypot, a minimum time-on-page and
a per-IP rate limit, and answer 429 rather than writing another row. The calculator also
totals server-side, so a visitor with JavaScript off gets a real number.

---

## Admin panel

Its own dense layout at `/admin`, deliberately unlike the public skin. 291 routes across
twelve modules.

- **Dashboard** — follow-ups due and overdue, the pipeline by stage and weighted value,
  money in this month against last, receivables by age, tickets at risk of breach,
  renewals in the next 60 days, documents awaiting signature, expiries from the vault.
- **Leads** — kanban with drag-and-drop plus a filterable table, a `lead_events` timeline,
  UTM and source capture, follow-up due dates with snooze, lost reasons, CSV in and out,
  and one-click convert to a client and project.
- **Pricing** — packages, add-ons and rules as editable rows, an internal cost and margin
  column only the owner sees, and a live calculator that saves a quote.
- **Documents** — proposals, quotations, SOWs, NDAs, care-plan contracts and handover
  notes, assembled from a 37-clause versioned library, numbered on the financial year,
  rendered to PDF, shared on a tokenised link with view tracking, and accepted online.
- **Clients, projects and delivery** — clients and contacts, projects with a status and a
  health flag, milestones, a task board, and a launch checklist.
- **Billing** — invoices from quote lines, proforma and advance receipts, part-payments
  with method and reference, numbered receipt PDFs, credit notes, write-offs, refunds,
  aging buckets, a dunning ladder that composes WhatsApp, and recurring hosting, domain,
  AMC and SEO items that generate renewal invoices.
- **Support** — tickets with a category, P1–P4 priority and the Open to Closed workflow,
  per-priority SLA policies with at-risk and breached highlighting, client-visible replies
  versus internal notes, attachments, time logging, and conversion of an out-of-scope
  request into a change request with a quote.
- **Money out** — expenses with categories, vendors, recurring flags, receipts and project
  allocation, plus your own subscription costs.
- **Analytics** — hand-drawn SVG on every chart: revenue against expense, collected against
  invoiced, receivables, revenue by service line and by client, MRR and ARR, lead-source
  ROI and CAC, weighted pipeline forecast, funnel conversion, SLA compliance, renewal rate,
  per-project P&L with margin and effective hourly rate. Indian FY, calendar year and
  quarterly views, a GST and TDS tax summary, and a CSV export of each.
- **Messages** — WhatsApp and email template libraries with variable preview, send-and-log
  from any lead, client, invoice or ticket, a throttled bulk queue, and per-contact opt-out.
- **Content** — pages and blocks, services, case studies, posts, testimonials, FAQs, stats,
  navigation, legal pages, and a media library with WebP variants and a picker modal.
- **Settings** — brand, contact, look, SEO, WhatsApp, email, tax and invoicing, CRM and
  pricing defaults, plus **Vault**, **Renewals**, **Referrals**, **Notifications**,
  **Activity log**, **Backup**, **Team** and global search.

Three roles: **Owner** reaches everything; **Administrator** is the same minus user
management; **Team** sees leads, projects, tickets, messages and media only. Cost, margin,
the analytics tab, billing writes and the vault are owner-and-administrator work, and the
vault reveal is owner-only. Buttons are hidden as well as refused.

Passwords are hashed with `werkzeug.security` and an unknown email is compared against a
dummy hash so response time does not reveal which accounts exist. Sessions are signed
cookies, rotated on sign-in. Every mutating POST carries a CSRF token, including sign-in
and sign-out. Repeated failed sign-ins from one address or against one account lock out for
15 minutes. Every response carries a Content-Security-Policy (`script-src 'self'` plus a
per-request nonce for the few inline admin scripts), `nosniff`, `X-Frame-Options: DENY` and
a referrer policy; `/admin` and `/portal` are additionally `Cache-Control: no-store`. Every
create, update and delete is written to `audit_log` with before and after JSON, which is
what the Activity log reads.

### Adding an admin field

Most admin screens are declarative. A resource is a table plus a list of `Field` specs;
`core/crud.py` generates the list, form, save, delete, toggle and reorder routes from it,
and the same renderer draws the settings screens from the tab definitions in
`blueprints/admin_settings.py`. Adding a field to Services means one `Field` line and one
column in `db/schema.sql`.

---

## Client portal

`/portal`, and there is no client password anywhere in this system. A client types their
email, gets a six-digit code, and that code is single-use and expires. `client_logins`
holds the codes and `portal_attempts` rate-limits the requesting, so the login is not a
way to enumerate which of your clients exist.

Inside: project progress and milestones, invoices with balances and receipt PDFs, the UPI
and bank block, documents to read and accept, and tickets — including raising a new request
or a change request. Statuses are translated on the way out: `CLIENT_VISIBLE_STATUSES` in
`core/projects.py` is why a client never sees a project marked "In trouble" on a Sunday
evening. It shares `site.css` with the public site on purpose, because a client who clicks
"sign in" from the website and lands in a differently-coloured tool assumes they have been
sent somewhere else.

---

## WhatsApp

`services/whatsapp.py` is one provider interface with two implementations, chosen under
**Settings → WhatsApp**:

- **Click to chat** (default, and works today with nothing to set up) builds a
  `wa.me/<number>?text=<rendered template>` link, logs the message as `ready`, and opens
  WhatsApp with the text already typed. You press send. Nothing is claimed as delivered
  that a person did not send.
- **Meta WhatsApp Cloud API** is written and off. Fill in the phone number ID, WABA ID,
  permanent token, webhook verify token and app secret, and switch the provider over.
  Outbound goes through Graph; `/hooks/whatsapp` handles the verification handshake,
  writes delivery statuses back onto the message row, and files inbound replies. Inbound is
  checked against the app secret, so a webhook that did not come from Meta is refused.

Either way the message log, the template library with its variable rendering and preview,
the throttle, the daily cap and the per-contact opt-out are the same. Switching provider
does not rewrite history: a message keeps the provider it went out through.

---

## GST

**Settings → Tax and invoicing → Invoice mode** is the switch, and it has two positions:

- **Bill of supply** — correct while you are not registered. No tax columns, no HSN/SAC, no
  place of supply, and the document says "bill of supply" because that is what it is.
- **Tax invoice** — turns on HSN/SAC, place of supply, and the CGST+SGST versus IGST split
  decided by comparing your state code against the client's. Composition scheme adds the
  mandatory declaration and stops tax being charged.

**Documents already issued keep the mode they were issued under.** Flipping the switch does
not retrospectively add tax to an invoice a client has already paid, which is the whole
reason the mode is stored on the row rather than read from settings at render time.

Numbering is per series and per financial year, in a transaction, because a GST series has
to be consecutive and unbroken within the year:

```
ARK/PRO/2026-27/001     proposal        LD-0004     lead
ARK/INV/2026-27/014     invoice         CL-0011     client
ARK/RCP/2026-27/031     receipt         TKT-0087    ticket
```

Invoice, proforma, receipt and credit note series are strict. `core/numbering.py::gaps()`
lists numbers that were issued and are no longer present, which is the question an auditor
asks — and it stays empty because a cancelled invoice keeps its row rather than being
deleted.

TDS is handled where it actually appears: a client deducting 194J or 194C pays you less
than the invoice, so a payment records an amount and a TDS amount separately, and the
invoice is settled by the sum. The tax summary totals both.

---

## The legal templates are a starting point, not advice

The clause library ships 37 clauses written for an Indian agency — payment terms and late
interest, TDS under 194J and 194C, GST per mode, timelines and deemed acceptance, IP
passing on full payment, confidentiality, the DPDP Act 2023, the IT Act 2000 and the 2021
intermediary guidelines, the E-Commerce Rules 2020, domain and hosting ownership, warranty,
a liability cap, indemnity, force majeure, termination and refunds, jurisdiction,
arbitration under the 1996 Act, and e-signature validity — and the four public legal pages
are drafted in the same spirit.

They are a reasonable first draft and nothing more. **Have a lawyer read them before you
send one to a client**, and read them yourself before you rely on the liability cap. The
document builder says so on screen for the same reason it is being said here, and clauses
are versioned so that getting them reviewed does not mean losing the history of what an
earlier client actually signed.

---

## Data model

59 tables, created idempotently from `db/schema.sql` with a version in `meta`.

- **Content** — `settings`, `pages`, `page_blocks`, `services`, `case_studies`, `posts`,
  `testimonials`, `faqs`, `stats`, `tech_items`, `nav_items`, `legal_pages`, `media`
- **Funnel** — `leads`, `lead_events`, `lead_sources`, `quotes`, `quote_lines`, `packages`,
  `addons`, `pricing_rules`
- **Documents** — `documents`, `clause_library`, `document_shares`, `document_views`
- **Delivery** — `clients`, `contacts`, `projects`, `milestones`, `tasks`,
  `launch_checklist`, `assets`, `credentials`
- **Money in** — `invoices`, `invoice_lines`, `payments`, `credit_notes`, `recurring_items`,
  `number_series`
- **Money out** — `expenses`, `expense_categories`, `subscriptions`
- **Support** — `tickets`, `ticket_messages`, `ticket_time_logs`, `sla_policies`
- **Messaging** — `messages`, `message_templates`, `optouts`, `email_log`,
  `review_requests`, `referral_payouts`, `notifications`
- **Access** — `users`, `login_attempts`, `client_logins`, `portal_attempts`, `audit_log`,
  `meta`

Settings are a typed key/value table read through `core/settings.py`, cached per request and
reachable in any template as `S('brand.name')`.

Vocabulary that both the panel and the portal show is defined once and imported by both —
`core/leads.py` for stages, `core/projects.py` for statuses and health, `core/tickets.py`
for priorities and the ticket workflow, `core/billing.py` for invoice statuses. A project
that reads "In build" on the delivery board and "active" in the portal is the kind of small
inconsistency that generates an email asking which one is true.

No payment gateway is wired up. Payments are recorded by hand with a method and a
reference, which is what actually happens when a client pays by UPI or NEFT. A gateway can
be added on top of `payments` later without touching invoice or receipt logic.

---

## Backup and restore

**Backup** in the sidebar writes a timestamped zip into `backups/` containing a consistent
copy of the database (taken through SQLite's backup API, so it is safe while the app is
running) and everything in `static/uploads`. The same screen downloads or restores one; a
restore moves the current database aside as `backups/pre-restore-<timestamp>.db` before
overwriting it, and signs you out so you come back on the restored data.

Neither `db/secret.key` nor `db/vault.key` is in the zip, and the manifest inside says so.
A backup that contains both the ciphertext and the key protects nothing. Copy the vault key
once, keep it elsewhere, and understand that restoring a database without it leaves the
stored credentials unreadable.

By hand: stop the app, copy `db/aruka.db`, `db/vault.key` and `static/uploads/`, done.

---

## Verification

Two scripts, both of which need the dev server running:

```
python app.py                        # in one terminal
python check_routes.py               # in another
python check_browser.py
```

`check_routes.py` is stdlib only, and 182 checks. It GETs every public, portal and admin
route, then drives one job the whole way through: an enquiry becomes a lead, the calculator
prices it, a proposal is written and shared, a client accepts it on the share link, the
lead converts to a client and a project, an invoice goes out, a part-payment and a receipt
come back, an overpayment is refused, a credit note is raised, a ticket is opened and
breaches its SLA and is answered, an out-of-scope request becomes a change request with a
quote, the client signs into the portal with a real one-time code, a credential goes into
the vault and comes back out, WhatsApp messages are composed and an opt-out is honoured,
the analytics exports download, and a backup is taken. It reads the generated PDFs rather
than just checking their size, so "the UPI ID is on the invoice" means the text is
genuinely in the file. It also asserts the hardening holds: an admin post without a CSRF
token is refused, a malformed JSON write is a 400 rather than a 500, sign-out cannot be a
GET, the CSP and `no-store` headers are present, `robots.txt` keeps crawlers out of the
panel and the portal, and the sitemap lists no private URL. Every row it writes is removed
at the end.

`check_browser.py` needs Playwright (`pip install playwright && playwright install
chromium`) and is 103 checks in four passes:

| Pass | What it drives |
| --- | --- |
| `desktop` | 1440×900, motion allowed — the whole animation set, the FAQ accordion, the public calculator, and that the cost and margin never reach the page |
| `mobile` | 390×844 with touch — the drawer, sideways overflow, tap-target size, and that no field is under 16px, because iOS zooms in on tap and does not zoom back out |
| `motion` | `prefers-reduced-motion: reduce` — nothing transparent, nothing shifted, nothing animating, counters printed rather than raced |
| `admin` | Signed in — creating a lead and a client, dragging a kanban card and checking it stayed after a reload, the quote builder's margin arithmetic, the vault reveal, and that turning **Animations on** off in the panel actually stills the public site |

Every pass fails on a console error, a page error or a failed request, so a broken script
is a failure rather than something you find later. Pass one of `desktop`, `mobile`,
`motion` or `admin` to run a single pass, `--headed` to watch it, `--slow` to watch it
slowly.

Both report `0 problem(s)` on the seeded database.

Three smaller scripts under `Tools/` answer maintenance questions rather than pass or fail:
`audit_endpoints.py` lists routes nothing links to and `url_for` calls with no endpoint,
`audit_templates.py` lists templates a route renders that do not exist and files nothing
renders, and `audit_classes.py` checks the stylesheets both ways — classes a template uses
that its own sheet does not define, and with `--unused`, rules nothing reaches. The second
direction reads the scripts for names JavaScript adds and matches `chip--{{ status }}` by
its stem, so what it lists is genuinely dead rather than merely dynamic. All three are
silent on a clean tree.

---

## Layout

```
aruka/
├── app.py                  # factory, config, Jinja globals, CLI, error pages
├── db/schema.sql           # 59 tables, idempotent
├── db/seed.py              # the rate card, the clause library, the starting copy
├── core/                   # db, auth, settings, crud, media, audit, util, numbering,
│                           # crypto, notify, leads, pricing, documents, billing,
│                           # tickets, projects
├── services/               # whatsapp.py (two providers), pdf.py (ReportLab), mailer.py
├── blueprints/             # public.py, portal.py, webhooks.py, admin.py,
│                           # admin_{leads,pricing,documents,projects,billing,tickets,
│                           #        messages,analytics,content,media,settings}.py
├── templates/public/       # base, home, page types, document, legal
├── templates/portal/       # base, dashboard, project, invoices, documents, tickets, login
├── templates/admin/        # base, dashboard, crud_list, crud_form, and one per screen
├── static/                 # css/site.css, css/admin.css, js/site.js, js/admin.js, uploads/
├── Tools/                  # audit_endpoints.py, audit_templates.py, audit_classes.py
├── check_routes.py         # 182 route and write checks
└── check_browser.py        # 103 browser checks in four passes
```

The seeded agency, its case studies and its posts are fictional, and the rate card is a
plausible starting point rather than your prices. Rename it in **Settings → Brand** and the
name, contact details, document headers and structured data follow everywhere; reprice it
in **Pricing** and both calculators follow.
