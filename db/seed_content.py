"""Starting website copy, services, FAQs, insights and the message template library.

This is a real first draft of the site rather than lorem ipsum, so the studio can
be online the day it installs this and edit its way to something better. Every row
here is editable in the panel.
"""

from __future__ import annotations

# ── pages ───────────────────────────────────────────────────────────────────
PAGES = [
    {
        "slug": "home", "title": "Home", "nav_label": "Home", "is_system": 1, "sort_order": 0,
        "kicker": "Digital studio, India",
        "heading": "Your brand, properly online",
        "intro": (
            "Websites, software, automation and search - built once, built well, and handed "
            "over with the keys. Fixed scope, a written quote, and support that answers."
        ),
        "meta_title": "Aruka - websites, SaaS, AI automation and SEO for Indian brands",
        "meta_description": (
            "A digital studio that builds websites, SaaS products, AI automations and SEO for "
            "Indian brands. Fixed scope, written quotes, support that answers. From 4,999."
        ),
        "seo_keyword": "digital agency india",
    },
    {
        "slug": "services", "title": "Services", "nav_label": "Services", "is_system": 1,
        "sort_order": 1, "kicker": "What we do",
        "heading": "Four things, done properly",
        "intro": (
            "We would rather be genuinely good at a few things than available for everything. "
            "Here is the whole list, with what each one includes and what it costs."
        ),
        "meta_description": (
            "Website design and development, SaaS product builds, AI automation and SEO. "
            "Scope, timelines and prices for each, written down before you commit."
        ),
        "seo_keyword": "website development services india",
    },
    {
        "slug": "work", "title": "Work", "nav_label": "Work", "is_system": 1, "sort_order": 2,
        "kicker": "Selected work",
        "heading": "Things we shipped",
        "intro": (
            "Every project here went live, stayed live, and did the thing it was built to do. "
            "Where a client let us publish numbers, the numbers are theirs, not ours."
        ),
        "meta_description": "Case studies from Aruka: what the brief was, what we built, "
                            "and what changed afterwards.",
    },
    {
        "slug": "pricing", "title": "Pricing", "nav_label": "Pricing", "is_system": 1,
        "sort_order": 3, "kicker": "No hidden numbers",
        "heading": "What it costs, before you ask",
        "intro": (
            "Our whole rate card is on this page, and the calculator uses exactly the same "
            "numbers we quote from. Build an estimate, save it, and we will confirm it in "
            "writing - nothing is charged until you accept."
        ),
        "meta_title": "Pricing - website, SaaS, automation and SEO costs",
        "meta_description": (
            "Transparent pricing from 4,999 for a website with a year of hosting and a domain. "
            "Build your own estimate with the same rate card we quote from."
        ),
        "seo_keyword": "website design cost india",
    },
    {
        "slug": "about", "title": "About", "nav_label": "About", "is_system": 1,
        "sort_order": 4, "kicker": "Who you would be working with",
        "heading": "Small studio, long memory",
        "intro": (
            "Aruka exists because too much digital work is sold by people who will not be "
            "there when it breaks. We build it, we hand it over properly, and we stay on for "
            "the part everyone else calls out of scope."
        ),
        "meta_description": "The studio behind Aruka: how we work, what we believe about "
                            "scope, and why the domain is always registered in your name.",
    },
    {
        "slug": "insights", "title": "Insights", "nav_label": "Insights", "is_system": 1,
        "sort_order": 5, "kicker": "Notes from the work",
        "heading": "Insights",
        "intro": (
            "What we have learned building and running things for Indian businesses. Written "
            "for the person paying for the website, not for other agencies."
        ),
        "meta_description": "Practical notes on websites, SEO, automation and digital "
                            "delivery for Indian businesses.",
    },
    {
        "slug": "contact", "title": "Contact", "nav_label": "Contact", "is_system": 1,
        "sort_order": 6, "kicker": "Start here",
        "heading": "Tell us what you need",
        "intro": (
            "One form, one working day, a real reply from a person who read it. If you would "
            "rather talk, WhatsApp is usually faster."
        ),
        "meta_description": "Get in touch with Aruka. We reply to every enquiry within one "
                            "working day, usually sooner.",
    },
]

# ── services ────────────────────────────────────────────────────────────────
SERVICES = [
    {
        "slug": "websites", "name": "Websites", "icon": "layout", "is_featured": 1,
        "sort_order": 0, "price_from": 4999, "timeline": "2 to 5 weeks",
        "tagline": "Static or dynamic, fast, and yours to run",
        "summary": (
            "A site that loads quickly, reads well on a phone, and sends every enquiry "
            "somewhere you will actually see it. Domain, hosting and SSL included for the "
            "first year."
        ),
        "body": """We build two kinds of website, and we will tell you honestly which one you need.

A **static site** is right for most businesses. It is a set of pages, hand-built,
served fast from a CDN, with nothing to hack and nothing to break. If your content
changes a few times a year, this is what you want, and it is what the 4,999 package
is.

A **dynamic site** is right when the content changes weekly or when someone on your
team needs to publish without calling us. That means an admin panel, a database,
and a blog or catalogue you control.

Either way you get the same foundations: mobile-first design from your own brand
colours, page titles and descriptions written for search, structured data so Google
understands what you do, an enquiry form that stores every submission and emails you,
a WhatsApp button wired to your number, and analytics set up so you can see what is
happening.

### How it goes

We start with your content, because a website is mostly writing. You send what you
have, we tell you what is missing. Then design, one screen at a time, with you seeing
it as it happens rather than in a big reveal at the end. Then build, then a staging
link you can share with whoever needs to approve it, then launch, then thirty days
where anything wrong is our problem.

### What you own at the end

The domain, registered in your name. The hosting account, in your name. The design
files, the content and the code. A recording of the walkthrough. Everything, in
short - we do not hold anything hostage, and we will not be the reason you cannot
leave.""",
        "features": "\n".join([
            "Mobile-first design from your brand",
            "Up to 5, 12 or 25 pages depending on the package",
            "Domain and hosting for one year",
            "Enquiry capture with every submission stored",
            "WhatsApp click-to-chat wired to your number",
            "Analytics and Search Console configured",
            "On-page SEO and schema markup",
            "Speed pass on real mobile hardware",
            "Staging link before anything goes live",
            "30 to 180 days of support depending on the package",
        ]),
        "deliverables": "\n".join([
            "Live website on your domain",
            "Admin access, on dynamic builds",
            "Analytics and Search Console access",
            "Handover document and walkthrough recording",
            "All credentials, in your name",
        ]),
        "ideal_for": "New brands, businesses with an outdated site, and anyone whose current "
                     "site does not bring in enquiries.",
        "meta_description": "Website design and development from 4,999 including a domain, "
                            "hosting and enquiry capture for a year.",
    },
    {
        "slug": "saas-products", "name": "SaaS and software", "icon": "rocket",
        "is_featured": 1, "sort_order": 1, "price_from": 89999,
        "timeline": "8 to 16 weeks",
        "tagline": "A product with accounts, data and billing behind it",
        "summary": (
            "When a spreadsheet has stopped coping and an off-the-shelf tool does not fit, "
            "we build the thing itself: accounts, the core workflow, an admin panel, "
            "reporting and billing."
        ),
        "body": """Most software projects fail on scope, not on code. So we start by writing
down exactly what the first version does - and, more usefully, what it does not.

### Discovery comes first

A week or two, paid, at the start. We map the user journeys, the data model and the
permissions, and we produce a scope document you can read and disagree with. If at
the end of it the honest answer is that an existing tool would do the job for a
tenth of the money, we will say so. We have said so before.

### Then we build in slices

Each slice is something you can log in and use, not a status update. Accounts and
permissions first, then the workflow the product exists to do, then the admin panel
for your own team, then reporting, then billing if the model needs it.

### What comes with it

Deployment, backups, monitoring and error alerts, because an application that nobody
is watching is an application that is already broken. Handover documentation written
for a developer who has never seen it. And six months of support, so the period where
real users find real problems is covered.

### What we will not do

We will not promise a mobile app on both stores as part of a first build. We will not
integrate with your ERP on the strength of a phone call. And we will not quote a fixed
price for something nobody has scoped - we will quote the discovery, and then the
build.""",
        "features": "\n".join([
            "Paid discovery with a signed scope",
            "Accounts, roles and permissions",
            "The core workflow, built properly",
            "Admin panel for your own team",
            "Reporting and CSV exports",
            "Subscription billing where the model needs it",
            "Deployment, backups, monitoring, error alerts",
            "Handover documentation and recorded walkthrough",
            "Six months of post-launch support",
        ]),
        "deliverables": "\n".join([
            "Running application on your own infrastructure",
            "Source code in your repository",
            "Scope document and data model",
            "Runbook for operating it",
        ]),
        "ideal_for": "Founders with customers already waiting, and businesses whose internal "
                     "process has outgrown spreadsheets.",
        "meta_description": "Custom SaaS and software development from 89,999. Discovery, "
                            "scoped build, deployment and six months of support.",
    },
    {
        "slug": "ai-automation", "name": "AI and automation", "icon": "spark",
        "is_featured": 1, "sort_order": 2, "price_from": 24999,
        "timeline": "2 to 4 weeks",
        "tagline": "Stop retyping things between tools",
        "summary": (
            "We find the parts of your week that are a person copying data from one screen "
            "to another, and remove them. Plus assistants that answer from your own "
            "documents rather than making things up."
        ),
        "body": """Automation is worth doing when it removes work that is repetitive, rule-based
and currently done by a person who could be doing something better. It is not worth
doing to say you use AI.

### We map before we build

A short session where we watch what actually happens, rather than what the process
document says happens. Usually two or three obvious wins appear in the first hour:
the enquiry that gets retyped into a spreadsheet, the invoice reminder nobody sends,
the report someone builds by hand every Monday.

### What we typically build

Lead capture that goes straight into your CRM with its source attached. WhatsApp
confirmations and reminders that fire on their own. A daily digest of what needs a
human today. A support assistant trained on your own manuals and policies, which
hands over to a person when it does not know - because a confident wrong answer to
a customer is worse than no answer.

### And we make it visible

Every automation reports when it runs and shouts when it fails. Silent automation is
how businesses discover in March that something stopped working in November. You get
a runbook, so your team can operate and pause things without us.

### Honest about cost

Model and API usage is billed at actuals and we will estimate it before we start.
An assistant that costs more per month than the person it replaces is not a saving,
and we would rather tell you that at the quote stage.""",
        "features": "\n".join([
            "Process mapping session, watching the real work",
            "Up to three automations built and monitored",
            "Support or sales assistant on your own documents",
            "WhatsApp, email or Slack notifications",
            "Dashboards for anything counted by hand",
            "Failure alerts on every flow",
            "Runbook for your own team",
            "90 days of tuning after go-live",
        ]),
        "deliverables": "\n".join([
            "Live automations in your own accounts",
            "Process map, before and after",
            "Runbook and failure playbook",
            "Estimated monthly running cost",
        ]),
        "ideal_for": "Teams of 3 to 50 losing hours a week to copy-paste, and anyone "
                     "answering the same customer question twenty times a day.",
        "meta_description": "AI automation and workflow integration from 24,999. Process "
                            "mapping, built automations, monitoring and a runbook.",
    },
    {
        "slug": "seo", "name": "SEO", "icon": "trend", "sort_order": 3, "price_from": 14999,
        "timeline": "Ongoing, 3 months minimum",
        "tagline": "Be found by people already looking for you",
        "summary": (
            "Technical fixes, content that answers real questions, and local search done "
            "properly. Reported monthly, in plain numbers, with no promises about "
            "positions."
        ),
        "body": """SEO is a habit, not a project. Anyone selling it as a one-off is selling you
an audit.

### What we actually do

A technical pass first: speed, crawlability, structured data, internal linking, and
the broken things that quietly cap everything else. Then keyword research that starts
from what your customers type, not from search volume - "emergency plumber Kothrud"
beats "plumbing solutions" every time.

Then content, two pieces a month, written to answer one question properly. Then local:
Google Business Profile filled in completely, categories right, photos current, reviews
requested from happy clients at the moment they are happiest.

### What we report

Positions on twenty tracked terms, organic traffic, which pages gained and lost, and
what we are doing next month. One page, in plain language, and we will get on a call
to go through it.

### What we will not promise

A position. Nobody controls Google's ranking, and anyone who tells you they can
guarantee number one is either lying or planning to rank you for a term nobody
searches. What we will promise is the work, honestly reported, and the judgement to
stop doing something that is not moving.

### How long

Three months before you should judge it, six before it compounds. If after three
months nothing has moved and we cannot explain why, stop paying us.""",
        "features": "\n".join([
            "Monthly technical audit and fixes",
            "Keyword research and mapping to pages",
            "Two optimised pages or articles a month",
            "Internal linking and content refresh",
            "Local SEO and Google Business Profile upkeep",
            "Quality backlink outreach",
            "Position tracking on twenty terms",
            "Monthly report and a call",
        ]),
        "deliverables": "\n".join([
            "Monthly report with positions and traffic",
            "Published content, yours to keep",
            "Technical fix log",
            "Keyword map",
        ]),
        "ideal_for": "Businesses with a working site that nobody finds, and local service "
                     "businesses competing on a handful of high-intent searches.",
        "meta_description": "SEO retainer from 14,999 a month. Technical fixes, content, "
                            "local search and honest monthly reporting.",
    },
]

# ── case studies ────────────────────────────────────────────────────────────
CASE_STUDIES = [
    {
        "slug": "sample-clinic-website", "title": "A dental clinic that stopped losing calls",
        "client_name": "Sample Dental Care", "sector": "Healthcare",
        "service_line": "Websites", "is_featured": 1, "sort_order": 0,
        "summary": "A three-chair clinic replaced a directory listing with a real site and "
                   "started taking appointment requests overnight.",
        "challenge": (
            "The clinic existed online only as a listing on two aggregator sites, both of "
            "which charged for leads and showed a competitor's advert beside their name. "
            "Patients rang during working hours or not at all, and the receptionist was "
            "writing appointments on paper."
        ),
        "approach": (
            "A five-page static site built from their own photographs, with a treatments "
            "page per service so each one could rank on its own. Appointment requests go to "
            "a form that stores every submission and sends a WhatsApp message to the "
            "receptionist's phone. Google Business Profile claimed, filled in properly, and "
            "wired to a review link the dentist could send after an appointment."
        ),
        "outcome": (
            "Appointment requests arrive at all hours, including several a week outside "
            "clinic time that would previously have gone to a competitor. The aggregator "
            "subscription was cancelled after two months. Review count went from 4 to 60 in "
            "the first quarter, which moved them into the local map pack."
        ),
        "metrics": "\n".join([
            "60 | Google reviews in the first quarter",
            "4x | Enquiries per month versus the listing",
            "0 | Aggregator lead fees, after month two",
            "14 | Days from brief to live",
        ]),
        "stack": "Static site, CDN hosting, WhatsApp notifications, Google Business Profile",
        "meta_description": "How a dental clinic replaced paid directory listings with its "
                            "own site and quadrupled enquiries.",
    },
    {
        "slug": "sample-logistics-portal", "title": "A logistics firm off spreadsheets",
        "client_name": "Sample Freight", "sector": "Logistics",
        "service_line": "SaaS and software", "is_featured": 1, "sort_order": 1,
        "summary": "Twelve shared spreadsheets became one application with accounts, "
                   "permissions and a client-facing tracking page.",
        "challenge": (
            "Consignments were tracked in a workbook that four people edited at once. Two "
            "of them kept private copies because the shared one kept breaking. Clients rang "
            "to ask where their shipment was, and the answer depended on who picked up."
        ),
        "approach": (
            "Two weeks of paid discovery produced a data model and a scope both sides signed. "
            "Then four slices: accounts and permissions, consignment entry with status "
            "history, a tracking page clients could open without logging in, and billing "
            "exports for their accountant. Deployed with backups, monitoring and error "
            "alerts from day one."
        ),
        "outcome": (
            "One source of truth. Status calls dropped because clients check the tracking "
            "page themselves. The monthly invoicing run went from two days of "
            "reconciliation to an export."
        ),
        "metrics": "\n".join([
            "12 | Spreadsheets retired",
            "2 days | Saved on every invoicing run",
            "70% | Fewer where-is-my-shipment calls",
            "11 | Weeks from discovery to launch",
        ]),
        "stack": "Python, SQLite, server-rendered UI, nightly backups, uptime monitoring",
        "meta_description": "How a logistics firm replaced twelve spreadsheets with one "
                            "application, and cut its invoicing run from two days to minutes.",
    },
    {
        "slug": "sample-retail-automation", "title": "A retailer that stopped retyping orders",
        "client_name": "Sample Retail", "sector": "Retail",
        "service_line": "AI and automation", "sort_order": 2,
        "summary": "Orders from three channels now land in one place, with confirmations "
                   "and reminders sending themselves.",
        "challenge": (
            "Orders came in by WhatsApp, phone and an online form. All three were retyped "
            "into a billing system by hand, twice a day, by someone who had better things to "
            "do. Around one in twenty orders was mistyped or missed entirely."
        ),
        "approach": (
            "Three automations. Form and WhatsApp orders parse into the billing system "
            "directly. A confirmation goes back to the customer on WhatsApp within seconds. "
            "Anything unpaid after 48 hours gets one reminder, automatically. Every flow "
            "alerts on failure, and a daily digest lands at 8am with anything needing a human."
        ),
        "outcome": (
            "Two hours a day of retyping gone. Mistyped orders effectively eliminated, "
            "because nothing is typed twice. Payment collection improved on the strength of "
            "the reminder alone."
        ),
        "metrics": "\n".join([
            "2 hours | Saved every day",
            "95% | Fewer order entry errors",
            "18% | Faster payment collection",
            "3 | Automations, all monitored",
        ]),
        "stack": "WhatsApp Business API, webhook automations, scheduled digests",
        "meta_description": "How a retailer automated order entry across three channels and "
                            "recovered two hours a day.",
    },
]

# ── testimonials ────────────────────────────────────────────────────────────
TESTIMONIALS = [
    {"author": "Sample Client", "role": "Owner", "company": "Sample Dental Care", "rating": 5,
     "sort_order": 0, "source": "google",
     "quote": "They asked better questions than the two agencies before them, and the site "
              "was live in a fortnight. Enquiries come in overnight now, which never used "
              "to happen."},
    {"author": "Sample Founder", "role": "Director", "company": "Sample Freight", "rating": 5,
     "sort_order": 1, "source": "direct",
     "quote": "The discovery week was the best money we spent. They talked us out of half "
              "of what we asked for, and the half we built actually gets used."},
    {"author": "Sample Manager", "role": "Operations", "company": "Sample Retail", "rating": 5,
     "sort_order": 2, "source": "direct",
     "quote": "Two hours a day back. And when something did break, someone replied the "
              "same morning with what had happened and what they had done about it."},
]

# ── FAQs ────────────────────────────────────────────────────────────────────
FAQS = [
    {"category": "general", "sort_order": 0,
     "question": "How long does a website take?",
     "answer": "Two weeks for the Starter package if your content is ready, three for "
               "Growth, five for Business. The clock starts when we have your content, "
               "not when you sign - waiting on copy is the single biggest cause of a "
               "website slipping."},
    {"category": "general", "sort_order": 1,
     "question": "Do I own the website?",
     "answer": "Entirely, once it is paid for. The domain is registered in your name from "
               "day one, the hosting account is yours, and the design and code transfer to "
               "you on final payment. We will not be the reason you cannot leave."},
    {"category": "general", "sort_order": 2,
     "question": "What happens after the first year?",
     "answer": "Hosting, domain and SSL renew - we will quote the renewal in advance, and "
               "you can pay us to keep managing it or take it over yourself. Either is "
               "fine, and taking it over does not require our permission."},
    {"category": "pricing", "sort_order": 3,
     "question": "Is 4,999 the real price?",
     "answer": "Yes, for up to five pages with a domain, hosting and SSL for a year and "
               "enquiry capture. What pushes a project above it is extra pages, ecommerce, "
               "logins, copywriting or photography - all priced on the pricing page so you "
               "can see it coming."},
    {"category": "pricing", "sort_order": 4,
     "question": "How do payments work?",
     "answer": "In milestones, so you never pay far ahead of the work. Typically 40% on "
               "acceptance, 40% at staging approval and 20% at go-live. UPI or bank "
               "transfer, with a numbered invoice and a receipt for every payment."},
    {"category": "pricing", "sort_order": 5,
     "question": "Do you charge GST?",
     "answer": "Only if we are registered, and the invoice will say clearly which it is. "
               "While we are not registered we issue a bill of supply and charge no tax. "
               "Either way the number you were quoted is the number you pay."},
    {"category": "process", "sort_order": 6,
     "question": "What do you need from me to start?",
     "answer": "Your content - text and images - your logo files, and access to your domain "
               "if you already have one. One person who can approve things. That is genuinely "
               "it, and we will send a checklist so nothing is a surprise."},
    {"category": "process", "sort_order": 7,
     "question": "What if I do not like the design?",
     "answer": "You will see it as it is built rather than in one big reveal, so the "
               "situation rarely arises. Each package includes revision rounds, and a round "
               "means one consolidated set of feedback rather than a stream of messages."},
    {"category": "support", "sort_order": 8,
     "question": "What if something breaks after launch?",
     "answer": "Raise a ticket and the clock starts immediately. Faults in what we built are "
               "fixed free during your support period. Response and resolution targets by "
               "priority are published on the support page, and we report against them."},
    {"category": "support", "sort_order": 9,
     "question": "Can I get changes made later?",
     "answer": "Yes. Small things during your support period we usually just do. Beyond "
               "that, a care plan gives you monthly hours at a lower rate, or we bill "
               "hourly. We tell you the cost before doing the work, every time."},
    {"category": "services", "sort_order": 10,
     "question": "Do you work with clients outside your city?",
     "answer": "Most of our work is remote and always has been. Calls on WhatsApp or "
               "Google Meet, files where you can see them, and a staging link you can share "
               "with anyone who needs to approve it."},
    {"category": "services", "sort_order": 11,
     "question": "Can you fix or take over an existing site?",
     "answer": "Often, yes - we will look first and tell you honestly whether fixing it is "
               "cheaper than rebuilding it. Sometimes it is not, and we would rather say so "
               "than bill you for propping something up."},
]

# ── insights ────────────────────────────────────────────────────────────────
POSTS = [
    {
        "slug": "what-a-website-should-cost-in-india",
        "title": "What a website should actually cost in India",
        "excerpt": "Why quotes for the same brief range from 3,000 to 3,00,000, and how to "
                   "tell which end you are being sold.",
        "tags": "pricing, websites",
        "seo_keyword": "website cost india",
        "meta_description": "An honest breakdown of website pricing in India, what drives "
                            "the cost, and the questions that reveal a bad quote.",
        "body": """Ask five people to quote the same five-page website in India and you will
get 3,000, 15,000, 45,000, 90,000 and "let's discuss". All five are quoting different
things, and only some of them know it.

## What you are actually paying for

A website has four costs inside it, and every quote is a different mix of them.

**Design.** Someone deciding what it looks like. A template costs nothing and looks
like a template. A design made from your brand takes days.

**Build.** Turning the design into pages that load fast and work on a five-year-old
Android. This is where corners get cut invisibly.

**Content.** The writing. Most quotes assume you supply it, and most clients do not
realise that until week three.

**Running it.** Domain, hosting, SSL, backups, and someone to call. Cheap quotes
usually exclude all of it, or include it for a year and stay quiet about year two.

## The 3,000 quote

Somebody will install a template, paste in your logo, and hand you a login. It is
not a scam - you get a website. But the pages will be slow, the SEO will be whatever
the template shipped with, and when it breaks the person who built it will have moved
on. It is worth what it costs.

## The 3,00,000 quote

Sometimes justified: many pages, several languages, ecommerce, integrations. Often
not: the same five pages with a project manager, an account manager and a strategy
deck between you and the person actually building it.

## The questions that tell you which you are looking at

Ask **in whose name the domain will be registered.** The only right answer is yours.

Ask **what happens in year two.** A quote that cannot answer this is hiding the
renewal.

Ask **what is not included.** A supplier who has thought about the work can list
exclusions immediately. One who cannot will discover them mid-project and bill you.

Ask **who fixes it when it breaks, and how fast.** If there is no answer with a
number of hours in it, there is no answer.

Ask **to see something they built two years ago.** Anyone can show you last month.

## What we charge, and why

Our Starter package is 4,999 for up to five pages with a domain, hosting and SSL for
a year and enquiry capture that stores every submission. That number is what it costs
us to do that work properly plus a margin we can live on. It is on our pricing page
along with everything that pushes it higher, because a client who is surprised by an
invoice is a client we have lost.

The honest summary: below about 4,000 someone is cutting something you cannot see.
Above about 50,000 for a simple brochure site, someone is selling you process. In
between, ask the questions above and the answers will sort the quotes for you.""",
    },
    {
        "slug": "how-scope-creep-actually-happens",
        "title": "How scope creep actually happens, and how to stop it",
        "excerpt": "It is never one big request. It is fourteen small ones, each of which "
                   "would have been rude to refuse.",
        "tags": "process, delivery",
        "seo_keyword": "scope creep",
        "meta_description": "Why fixed-price digital projects overrun, and the specific "
                            "habits that keep scope honest for both sides.",
        "body": """Nobody ever asks for a second website halfway through the first one. That is
not how projects overrun.

## What it actually looks like

Week two: "could the logo be slightly bigger." Week three: "can we add a page for the
new service." Week four: "my brother-in-law says the blue is wrong." Week five: "just
one more section." Each one takes twenty minutes. None of them feels like a change
request. Together they are a week of unpaid work and a launch date that has quietly
moved.

## Why suppliers let it happen

Because saying no feels like bad service, and because the first three requests genuinely
were twenty minutes. By request eight the pattern is established, and re-opening the
conversation now looks petty. So the supplier absorbs it, resents it, and either cuts
quality somewhere invisible or delivers late.

## Why clients do not realise

Because from the client's side each request is small and reasonable - which it is. The
client cannot see the accumulation. Nobody is showing them a running total.

## What actually fixes it

**Write down what is excluded, not just what is included.** An included list is
aspirational. An excluded list is a boundary. Ours names copywriting, logo design,
stock photography and anything a visitor logs into, because those are the four that
come up every time.

**Define a revision round.** One consolidated set of feedback, not a stream of
messages. This single definition removes most of the problem, because it forces
feedback to be gathered rather than dripped.

**Price small changes visibly, then often waive them.** "That is about 900 rupees of
work - I will do it as part of this round" is a completely different conversation from
silently absorbing it. The client learns what things cost. You keep the goodwill and
the boundary.

**Have a deemed-acceptance clause and actually use it.** Seven days to accept or list
defects. Not to punish anyone - to stop a project sitting in limbo while a decision
maker is on holiday.

**Show a running total.** We keep a change log on every project. Nothing motivates a
client to bundle their requests like seeing the last four itemised.

## The thing nobody says

Scope creep is usually a symptom of a scope that was never specific enough to creep
away from. If your document says "modern, professional design" then every opinion is
in scope, forever. If it says "five pages, layouts approved at staging, two revision
rounds", there is something to point at.

Write the boring document. It is the kindest thing you can do for both sides.""",
    },
    {
        "slug": "local-seo-that-works-for-indian-businesses",
        "title": "Local SEO that actually works for Indian businesses",
        "excerpt": "Most of the ranking is decided by a profile you already own and have "
                   "probably never filled in.",
        "tags": "seo, local",
        "seo_keyword": "local seo india",
        "meta_description": "A practical local SEO checklist for Indian service businesses, "
                            "starting with the free thing that moves the needle most.",
        "body": """If you sell to people within twenty kilometres of you, most of your search
result is decided by something free that takes an afternoon.

## Start with the profile, not the website

Google Business Profile decides the map pack, and the map pack is what people actually
tap. Before touching your website:

- Claim it, if you have not. Somebody may have claimed it for you.
- Set the **primary category** precisely. "Dentist" and "Dental clinic" rank
  differently. Pick the one your customers would say.
- Fill in every field. Hours, including holidays. Services, each one separately.
  Attributes. Payment methods.
- Add real photographs, not stock, and add more every month. Profiles with recent
  photos get more taps.
- Use the products or services section as free real estate for keywords.

## Then reviews, systematically

Reviews are the second-biggest local factor, and the mistake everyone makes is asking
too late. Ask at the moment the customer is happiest - immediately after the work,
not a week later by email.

Send a direct link to the review form on WhatsApp. Not "please review us on Google" -
a link that opens the box. That change alone typically triples the response rate.

Reply to every review, including the bad ones, in public, without arguing. The reply
is for the next reader, not the reviewer.

## Then the website, and only these bits

**One page per service.** "Root canal treatment in Kothrud" beats a single services
page listing fourteen things. Each page can rank for its own search.

**Name, address and phone identical everywhere** - website footer, Google profile,
Justdial, Facebook. Google cross-references these, and a mismatched address costs you.

**LocalBusiness schema** with your address, hours and geo-coordinates.

**Speed on mobile, on a real Indian connection.** Not your office wifi. Most of your
traffic is on a mid-range Android on 4G.

## What to ignore

Buying backlinks. Directory submission packages. Anyone guaranteeing a position.
Keyword stuffing your footer with every locality in the city - Google has understood
that trick for a decade.

## How long

Profile changes can move things in weeks, sometimes days. Content and links take
three to six months to compound. Anyone promising faster is either lucky or lying.""",
    },
]

# ── stats and marquee ───────────────────────────────────────────────────────
STATS = [
    {"label": "Projects delivered", "value": 40, "suffix": "+", "sort_order": 0},
    {"label": "Average build time, days", "value": 18, "sort_order": 1},
    {"label": "Client retention", "value": 92, "suffix": "%", "sort_order": 2},
    {"label": "First reply, hours", "value": 4, "prefix": "<", "sort_order": 3},
]

TECH = [
    {"label": "Python", "category": "backend", "sort_order": 0},
    {"label": "Flask", "category": "backend", "sort_order": 1},
    {"label": "PostgreSQL", "category": "data", "sort_order": 2},
    {"label": "SQLite", "category": "data", "sort_order": 3},
    {"label": "JavaScript", "category": "frontend", "sort_order": 4},
    {"label": "React", "category": "frontend", "sort_order": 5},
    {"label": "Tailwind", "category": "frontend", "sort_order": 6},
    {"label": "Cloudflare", "category": "infra", "sort_order": 7},
    {"label": "Razorpay", "category": "commerce", "sort_order": 8},
    {"label": "WhatsApp Business API", "category": "comms", "sort_order": 9},
    {"label": "OpenAI", "category": "ai", "sort_order": 10},
    {"label": "Google Analytics 4", "category": "growth", "sort_order": 11},
    {"label": "Search Console", "category": "growth", "sort_order": 12},
    {"label": "Docker", "category": "infra", "sort_order": 13},
]

# ── navigation ──────────────────────────────────────────────────────────────
NAV = [
    {"location": "header", "label": "Services", "url": "/services", "sort_order": 0},
    {"location": "header", "label": "Work", "url": "/work", "sort_order": 1},
    {"location": "header", "label": "Pricing", "url": "/pricing", "sort_order": 2},
    {"location": "header", "label": "About", "url": "/about", "sort_order": 3},
    {"location": "header", "label": "Insights", "url": "/insights", "sort_order": 4},
    {"location": "header", "label": "Start a project", "url": "/contact", "is_button": 1,
     "sort_order": 5},
    {"location": "footer", "label": "Support", "url": "/support", "sort_order": 0},
    {"location": "footer", "label": "Client portal", "url": "/portal", "sort_order": 1},
    {"location": "footer", "label": "Contact", "url": "/contact", "sort_order": 2},
]

# ── message templates ───────────────────────────────────────────────────────
WHATSAPP_TEMPLATES = [
    {"code": "lead-first-reply", "name": "First reply to an enquiry", "category": "followup",
     "sort_order": 0,
     "body": "Hi {{ name }}, this is {{ sender }} from {{ brand }}. Thank you for the "
             "enquiry about {{ service }} - I have read it properly.\n\n"
             "Could I ask two quick things: roughly when do you want it live, and do you "
             "have the content ready?\n\nYour reference is {{ ref }}."},
    {"code": "lead-followup", "name": "Nudge after no reply", "category": "followup",
     "sort_order": 1,
     "body": "Hi {{ name }}, following up on your enquiry with {{ brand }} ({{ ref }}). "
             "No pressure at all - just let me know if it is still live or if the timing "
             "has moved, and I will stop chasing either way."},
    {"code": "quote-sent", "name": "Quote sent", "category": "sales", "sort_order": 2,
     "body": "Hi {{ name }}, the quote for {{ service }} is ready: {{ amount }}.\n\n"
             "Everything included, everything excluded, and the timeline are all written "
             "down here: {{ link }}\n\nYou can accept it on that page. Happy to talk it "
             "through first if easier."},
    {"code": "proposal-sent", "name": "Proposal sent", "category": "sales", "sort_order": 3,
     "body": "Hi {{ name }}, the proposal {{ document_no }} is ready: {{ link }}\n\n"
             "It covers scope, price, timeline and terms. Read it, ask me anything, and "
             "accept on the page when you are happy."},
    {"code": "proposal-nudge", "name": "Proposal nudge", "category": "sales", "sort_order": 4,
     "body": "Hi {{ name }}, just checking the proposal reached you: {{ link }}\n\n"
             "Anything in it you would like changed? Easier to adjust now than later."},
    {"code": "invoice-sent", "name": "Invoice sent", "category": "payment", "sort_order": 5,
     "body": "Hi {{ name }}, invoice {{ invoice_no }} for {{ amount }} is attached, due "
             "{{ due_date }}.\n\nUPI: {{ upi }}\n\nPlease quote {{ invoice_no }} with the "
             "transfer so I can match it the same day. Thank you."},
    {"code": "payment-reminder-1", "name": "Gentle payment reminder", "category": "payment",
     "sort_order": 6,
     "body": "Hi {{ name }}, a gentle reminder that invoice {{ invoice_no }} "
             "({{ balance }}) was due {{ due_date }}.\n\nUPI: {{ upi }}\n\nIf it has "
             "already gone, send me the reference and I will find it."},
    {"code": "payment-reminder-2", "name": "Firmer payment reminder", "category": "payment",
     "sort_order": 7,
     "body": "Hi {{ name }}, invoice {{ invoice_no }} for {{ balance }} is now past due.\n\n"
             "Could you let me know when it will be settled? If something is holding it up, "
             "tell me and we will sort it out.\n\nUPI: {{ upi }}"},
    {"code": "payment-received", "name": "Payment received", "category": "payment",
     "sort_order": 8,
     "body": "Received, thank you {{ name }} - {{ amount }} against {{ invoice_no }}. "
             "The receipt is attached.\n\n{{ balance }} outstanding on the account."},
    {"code": "renewal-due", "name": "Renewal coming up", "category": "renewal",
     "sort_order": 9,
     "body": "Hi {{ name }}, your {{ service }} renews on {{ due_date }} - {{ amount }} "
             "for the year.\n\nHappy to keep it running, or to hand it over to you if you "
             "would rather manage it yourself. Just say which."},
    {"code": "ticket-received", "name": "Ticket received", "category": "support",
     "sort_order": 10,
     "body": "Hi {{ name }}, I have your report - logged as {{ ticket_ref }}. Looking at "
             "it now, and I will come back to you with what I find."},
    {"code": "ticket-resolved", "name": "Ticket resolved", "category": "support",
     "sort_order": 11,
     "body": "Hi {{ name }}, {{ ticket_ref }} is sorted. {{ subject }}\n\nHave a look and "
             "tell me if anything is still off - the ticket stays open until you are happy."},
    {"code": "project-live", "name": "Project is live", "category": "delivery",
     "sort_order": 12,
     "body": "{{ name }}, {{ project }} is live.\n\n{{ link }}\n\nEverything is in your "
             "name - domain, hosting, analytics. The handover note has each login. "
             "Congratulations, and thank you for trusting us with it."},
    {"code": "review-request", "name": "Review request", "category": "delivery",
     "sort_order": 13,
     "body": "{{ name }}, it has been a pleasure. If you have two minutes, a review would "
             "genuinely help us: {{ link }}\n\nAnd if anything fell short, tell me first - "
             "I would rather fix it than read it."},
    {"code": "portal-code", "name": "Portal sign-in code", "category": "support",
     "sort_order": 14,
     "body": "Hi {{ name }}, your {{ brand }} portal code is {{ ref }}. It works once and "
             "expires shortly."},
]

EMAIL_TEMPLATES = [
    {"code": "email-lead-ack", "name": "Enquiry acknowledgement", "category": "followup",
     "subject": "We have your enquiry - {{ ref }}",
     "sort_order": 0,
     "body": "Hi {{ name }},\n\nThank you for getting in touch with {{ brand }}. A real "
             "person has read your enquiry and will reply within one working day.\n\n"
             "Your reference is {{ ref }} - quote it if you follow up.\n\n"
             "If it is urgent, WhatsApp is faster: {{ phone }}"},
    {"code": "email-invoice", "name": "Invoice", "category": "payment",
     "subject": "Invoice {{ invoice_no }} from {{ brand }}",
     "sort_order": 1,
     "body": "Hi {{ name }},\n\nInvoice {{ invoice_no }} for {{ amount }} is attached, due "
             "{{ due_date }}.\n\nUPI: {{ upi }}\n\nPlease quote the invoice number with your "
             "transfer so it can be matched the same day.\n\nThank you."},
    {"code": "email-receipt", "name": "Payment receipt", "category": "payment",
     "subject": "Receipt for {{ amount }} - thank you",
     "sort_order": 2,
     "body": "Hi {{ name }},\n\nWe have received {{ amount }} against {{ invoice_no }}. The "
             "receipt is attached.\n\nOutstanding on the account: {{ balance }}\n\nThank you."},
    {"code": "email-document", "name": "Document to review", "category": "sales",
     "subject": "{{ document_no }} for your review",
     "sort_order": 3,
     "body": "Hi {{ name }},\n\n{{ document_no }} is ready for you: {{ link }}\n\nIt sets "
             "out scope, price, timeline and terms. You can read it, download a PDF, and "
             "accept it on that page.\n\nAsk me anything before you do."},
    {"code": "email-portal-code", "name": "Portal sign-in code", "category": "support",
     "subject": "Your {{ brand }} sign-in code",
     "sort_order": 4,
     "body": "Your code is {{ ref }}.\n\nIt works once and expires shortly. If you did not "
             "ask for it, ignore this email - nothing has changed on your account."},
    {"code": "email-ticket-ack", "name": "Ticket acknowledgement", "category": "support",
     "subject": "We have your request - {{ ticket_ref }}",
     "sort_order": 5,
     "body": "Hi {{ name }},\n\nYour request is logged as {{ ticket_ref }}: {{ subject }}\n\n"
             "We will reply within our published target for this priority. Quote the "
             "reference if you follow up."},
]
