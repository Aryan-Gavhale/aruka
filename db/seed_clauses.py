"""The India clause set and the four public legal pages.

Written for a small Indian studio selling website and software work to Indian
businesses. It is a solid, honest starting point - not legal advice, and the panel
says so on every screen that touches it. Have a lawyer read it once before you sign
anything that matters.

Every clause carries a code and a version. Editing a clause in the panel creates
version 2 rather than overwriting version 1, so a proposal issued last year can
still be reproduced with the wording that was actually agreed.

Placeholders in braces are filled from Settings at render time: {brand},
{jurisdiction_city}, {arbitration_seat}, {late_fee_pct}, {terms_days}, {validity_days}.
"""

from __future__ import annotations

ALL = "proposal,sow,amc,quotation,agreement"
CONTRACTS = "proposal,sow,amc,agreement"

CLAUSES = [
    # ── money ───────────────────────────────────────────────────────────────
    {
        "code": "payment-schedule", "title": "Payment schedule", "category": "commercial",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 0,
        "body": (
            "Fees are payable against the milestones set out in this document. Work on a "
            "milestone begins only after the amount due for the preceding milestone has been "
            "received. Each invoice is payable within {terms_days} days of its date. All "
            "amounts are in Indian Rupees and exclude any third-party costs, which are "
            "billed at actuals with proof of expense."
        ),
    },
    {
        "code": "late-payment", "title": "Late payment", "category": "commercial",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 1,
        "body": (
            "Interest at {late_fee_pct}% per month, or part month, is payable on any amount "
            "outstanding beyond its due date. Where an invoice remains unpaid for thirty days "
            "beyond its due date, {brand} may suspend work and withhold deliverables and "
            "access credentials until the account is settled. Suspension on this ground does "
            "not extend any timeline commitment and does not constitute a breach by {brand}."
        ),
    },
    {
        "code": "tds", "title": "Tax deducted at source", "category": "commercial",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 2,
        "body": (
            "Where the Client is required to deduct tax at source under section 194J or "
            "section 194C of the Income-tax Act, 1961, the deduction shall be made at the "
            "prescribed rate and the balance remitted to {brand}. The Client shall furnish "
            "Form 16A within the timeline prescribed under the Act. TDS deducted is credited "
            "against the invoice and does not reduce the amount due; an invoice is treated as "
            "settled only when the net payment and the corresponding TDS certificate have "
            "both been received."
        ),
    },
    {
        "code": "gst", "title": "Goods and Services Tax", "category": "commercial",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 3,
        "body": (
            "Where {brand} is registered under the Central Goods and Services Tax Act, 2017, "
            "GST is charged at the applicable rate in addition to the fees stated and is shown "
            "separately on every tax invoice. Where {brand} is not registered, documents are "
            "issued as a bill of supply and no tax is charged or collected. If {brand} becomes "
            "registered during the term, GST becomes payable on invoices raised from the date "
            "of registration, and the fees quoted here are treated as exclusive of it."
        ),
    },
    {
        "code": "expenses", "title": "Third-party costs", "category": "commercial",
        "applies_to": CONTRACTS, "sort_order": 4,
        "body": (
            "Domain registration, hosting, licences, plugins, fonts, stock assets, payment "
            "gateway charges, cloud infrastructure and model or API usage are third-party "
            "costs. Where they are included in a package, the inclusion is for the stated "
            "period only. Beyond that period, or beyond the stated quantity, they are billed "
            "at actuals. {brand} does not mark up a third-party cost without saying so on the "
            "invoice."
        ),
    },
    {
        "code": "validity", "title": "Validity of this quotation", "category": "commercial",
        "applies_to": "proposal,quotation", "is_required": 1, "sort_order": 5,
        "body": (
            "This document is valid for {validity_days} days from its date. After that, "
            "prices, timelines and availability are subject to reconfirmation. Nothing in "
            "this document is a binding commitment on either side until it is accepted in "
            "writing or electronically and the first payment is received."
        ),
    },

    # ── scope and delivery ──────────────────────────────────────────────────
    {
        "code": "scope", "title": "Scope of work", "category": "delivery",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 10,
        "body": (
            "The scope of this engagement is exactly what is listed as included in this "
            "document. Anything not listed is out of scope, including items listed as "
            "excluded. This is not a formality: a clear boundary is what allows a fixed price "
            "to be honoured, and it protects both sides equally."
        ),
    },
    {
        "code": "change-control", "title": "Changes to scope", "category": "delivery",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 11,
        "body": (
            "Either party may request a change. {brand} will provide a written estimate of "
            "the effect on cost and timeline, and the change proceeds only once that estimate "
            "is approved in writing. Work already completed to an approved specification is "
            "chargeable even if it is subsequently changed."
        ),
    },
    {
        "code": "client-obligations", "title": "What the Client provides", "category": "delivery",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 12,
        "body": (
            "The Client shall provide content, logo and brand files, product data, and access "
            "credentials for domains, hosting and third-party accounts, in usable form and in "
            "good time. The Client shall nominate one person authorised to give approvals. "
            "Timelines are calculated from the date the last item needed to start is received, "
            "and pause for the period {brand} is waiting on the Client."
        ),
    },
    {
        "code": "timeline", "title": "Timelines", "category": "delivery",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 13,
        "body": (
            "Timelines stated in this document are working-day estimates made in good faith "
            "on the assumption of timely feedback and content. They are not guarantees, and "
            "they exclude any period during which {brand} is waiting on the Client, on a "
            "third party, or on an approval. {brand} will tell the Client promptly if a date "
            "is at risk, with the reason."
        ),
    },
    {
        "code": "revisions", "title": "Revisions", "category": "delivery",
        "applies_to": CONTRACTS, "sort_order": 14,
        "body": (
            "The number of revision rounds included is stated in this document. A round means "
            "one consolidated set of feedback, not a series of individual instructions. "
            "Revisions beyond the included rounds, and any change of direction after a design "
            "has been approved, are chargeable at the prevailing hourly rate."
        ),
    },
    {
        "code": "deemed-acceptance", "title": "Deemed acceptance", "category": "delivery",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 15,
        "body": (
            "On notification that a milestone or deliverable is ready for review, the Client "
            "has seven days to accept it or to raise specific written defects. If neither "
            "happens within that period, the deliverable is deemed accepted and the "
            "corresponding payment becomes due. This clause exists so a project cannot stall "
            "indefinitely without either party knowing where it stands."
        ),
    },
    {
        "code": "support-window", "title": "Support after launch", "category": "delivery",
        "applies_to": CONTRACTS, "sort_order": 16,
        "body": (
            "The support period stated in this document begins on the day the work goes live "
            "and covers correction of defects in what {brand} delivered. It does not cover new "
            "features, content changes, third-party breakages, changes made by others, or "
            "training. Beyond that period, support is available under a care plan or at the "
            "prevailing hourly rate."
        ),
    },
    {
        "code": "third-party-services", "title": "Third-party services", "category": "delivery",
        "applies_to": CONTRACTS, "sort_order": 17,
        "body": (
            "The work may depend on services operated by others - hosting, payment gateways, "
            "email providers, mapping, analytics or model APIs. {brand} is not responsible for "
            "their availability, pricing, policy changes or discontinuation. Where such a "
            "change requires rework, that rework is chargeable."
        ),
    },

    # ── ownership ───────────────────────────────────────────────────────────
    {
        "code": "ip-transfer", "title": "Ownership of the work", "category": "ip",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 20,
        "body": (
            "On receipt of all amounts due, all rights in the deliverables created "
            "specifically for the Client, including designs, content written by {brand} and "
            "custom source code, transfer to the Client. Until then, {brand} retains "
            "ownership and grants only a revocable licence to review the work. {brand} "
            "retains ownership of its own pre-existing tools, libraries, internal frameworks "
            "and know-how, and grants the Client a perpetual, non-exclusive licence to use "
            "them as embedded in the deliverables."
        ),
    },
    {
        "code": "third-party-ip", "title": "Third-party materials", "category": "ip",
        "applies_to": CONTRACTS, "sort_order": 21,
        "body": (
            "Open-source components remain under their own licences. Stock images, fonts and "
            "plugins are licensed on the terms of their vendors, and where a licence is "
            "purchased on the Client's behalf it is registered in the Client's name wherever "
            "the vendor permits it. The Client warrants that any material it supplies is "
            "either owned by it or properly licensed."
        ),
    },
    {
        "code": "domain-hosting-ownership", "title": "Domains, hosting and accounts",
        "category": "ip", "applies_to": CONTRACTS, "is_required": 1, "sort_order": 22,
        "body": (
            "Domains are registered in the Client's name and remain the Client's property "
            "regardless of who pays the renewal. Where {brand} manages hosting or a "
            "third-party account on the Client's behalf, the Client is the account owner and "
            "may take over administrative access at any time on request. {brand} does not hold "
            "a domain or an account hostage over a commercial dispute; unpaid invoices are "
            "pursued as a debt, not by withholding what the Client owns."
        ),
    },
    {
        "code": "portfolio", "title": "Credit and portfolio use", "category": "ip",
        "applies_to": CONTRACTS, "sort_order": 23,
        "body": (
            "{brand} may name the Client, describe the work and show screenshots in its "
            "portfolio, case studies and marketing, unless the Client asks in writing that it "
            "does not. Confidential figures are never published without express written "
            "permission."
        ),
    },

    # ── data and privacy ────────────────────────────────────────────────────
    {
        "code": "confidentiality", "title": "Confidentiality", "category": "data",
        "applies_to": ALL, "is_required": 1, "sort_order": 30,
        "body": (
            "Each party shall keep confidential all non-public information received from the "
            "other, use it only for this engagement, and protect it with at least the care it "
            "applies to its own confidential information. This obligation survives the end of "
            "the engagement by three years, and indefinitely for anything that is a trade "
            "secret. It does not apply to information that is public, independently developed, "
            "or required to be disclosed by law or a court."
        ),
    },
    {
        "code": "dpdp", "title": "Personal data and the DPDP Act", "category": "data",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 31,
        "body": (
            "In respect of personal data collected through the deliverables, the Client is the "
            "Data Fiduciary and {brand} acts as a Data Processor on the Client's instructions, "
            "within the meaning of the Digital Personal Data Protection Act, 2023. {brand} "
            "shall process personal data only as needed to provide the services, apply "
            "reasonable security safeguards, not retain it longer than necessary, assist the "
            "Client with Data Principal requests, and notify the Client without undue delay on "
            "becoming aware of a personal data breach. The Client is responsible for its own "
            "privacy notice, for obtaining consent where the Act requires it, and for the "
            "lawfulness of the data it asks to have processed."
        ),
    },
    {
        "code": "it-act", "title": "Information Technology Act compliance", "category": "data",
        "applies_to": CONTRACTS, "sort_order": 32,
        "body": (
            "The Client is responsible for the content published through the deliverables and "
            "for compliance with the Information Technology Act, 2000 and the Information "
            "Technology (Intermediary Guidelines and Digital Media Ethics Code) Rules, 2021, "
            "including publication of the required policies and grievance officer details "
            "where the Client operates as an intermediary. {brand} will implement the "
            "technical means to display them, but does not determine what the Client is "
            "obliged to publish."
        ),
    },
    {
        "code": "ecommerce-rules", "title": "Consumer protection for online sales",
        "category": "data", "applies_to": CONTRACTS, "sort_order": 33,
        "body": (
            "Where the deliverables sell goods or services to consumers, the Client is "
            "responsible for compliance with the Consumer Protection (E-Commerce) Rules, 2020, "
            "including display of seller details, country of origin, total price with all "
            "charges, grievance redressal contact and a clear returns, refunds and "
            "cancellation policy. {brand} will build these into the site as instructed and "
            "will point out an obvious omission, but the content of those disclosures is the "
            "Client's responsibility."
        ),
    },
    {
        "code": "data-location", "title": "Backups and data handling", "category": "data",
        "applies_to": CONTRACTS, "sort_order": 34,
        "body": (
            "Where {brand} manages hosting, backups are taken on the schedule stated in this "
            "document and retained for the stated period. {brand} will restore from the most "
            "recent usable backup on request. {brand} is not a substitute for the Client's own "
            "records, and the Client should keep an independent copy of anything it cannot "
            "afford to lose."
        ),
    },

    # ── liability ───────────────────────────────────────────────────────────
    {
        "code": "warranty", "title": "Warranty", "category": "liability",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 40,
        "body": (
            "{brand} warrants that the work will be performed with reasonable skill and care "
            "and will materially conform to what this document describes. Defects reported "
            "during the support period are corrected at no charge. Beyond that warranty, the "
            "deliverables are provided as they are, and no other warranty, express or implied, "
            "is given - in particular, no result, ranking, conversion rate or revenue figure "
            "is promised, because no honest supplier can promise one."
        ),
    },
    {
        "code": "liability-cap", "title": "Limitation of liability", "category": "liability",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 41,
        "body": (
            "The total aggregate liability of {brand} arising out of this engagement, whether "
            "in contract, tort or otherwise, shall not exceed the total fees actually paid by "
            "the Client to {brand} under this document in the twelve months preceding the "
            "claim. Neither party is liable for indirect, incidental or consequential loss, "
            "including loss of profit, revenue, goodwill, data or anticipated savings. Nothing "
            "in this clause limits liability for fraud, wilful misconduct, or anything that "
            "cannot be limited under Indian law."
        ),
    },
    {
        "code": "indemnity", "title": "Indemnity", "category": "liability",
        "applies_to": CONTRACTS, "sort_order": 42,
        "body": (
            "The Client shall indemnify {brand} against any claim arising from content, data "
            "or materials supplied by the Client, from the Client's use of the deliverables in "
            "breach of law, and from any allegation that material supplied by the Client "
            "infringes the rights of a third party. {brand} shall indemnify the Client against "
            "any claim that a deliverable created by {brand} infringes a third party's "
            "intellectual property rights in India."
        ),
    },
    {
        "code": "force-majeure", "title": "Force majeure", "category": "liability",
        "applies_to": CONTRACTS, "sort_order": 43,
        "body": (
            "Neither party is liable for a failure or delay caused by an event beyond its "
            "reasonable control, including act of God, flood, fire, epidemic, war, civil "
            "unrest, government action, failure of power or telecommunications, or the failure "
            "of a third-party platform. The affected party shall notify the other promptly and "
            "use reasonable efforts to resume. If the event continues beyond sixty days, "
            "either party may terminate and the Client pays for work completed up to that date."
        ),
    },

    # ── ending it ───────────────────────────────────────────────────────────
    {
        "code": "termination", "title": "Termination", "category": "exit",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 50,
        "body": (
            "Either party may terminate on fifteen days' written notice. Either party may "
            "terminate immediately if the other commits a material breach and fails to remedy "
            "it within fifteen days of written notice. On termination the Client pays for all "
            "work completed and all third-party costs committed up to the date of termination, "
            "and {brand} hands over the work in its then-current state together with the "
            "credentials for anything the Client owns."
        ),
    },
    {
        "code": "refunds", "title": "Refunds and cancellation", "category": "exit",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 51,
        "body": (
            "Amounts paid for work already performed are not refundable, because the time has "
            "been spent. Where the Client cancels before work on a milestone has begun, any "
            "amount paid for that milestone is refunded in full within fifteen working days, "
            "less third-party costs already committed on the Client's instruction. Domain "
            "registrations, licences and subscriptions are non-refundable once purchased, as "
            "those vendors do not refund them."
        ),
    },
    {
        "code": "suspension-abandonment", "title": "Dormant projects", "category": "exit",
        "applies_to": CONTRACTS, "sort_order": 52,
        "body": (
            "If a project is inactive for sixty days for reasons attributable to the Client, "
            "{brand} may invoice for the work completed to that point and treat the engagement "
            "as closed. Restarting afterwards is quoted afresh, since the team, the tooling "
            "and the third-party landscape will have moved on."
        ),
    },

    # ── law ─────────────────────────────────────────────────────────────────
    {
        "code": "jurisdiction", "title": "Governing law and jurisdiction", "category": "legal",
        "applies_to": ALL, "is_required": 1, "sort_order": 60,
        "body": (
            "This document is governed by the laws of India. Subject to the arbitration "
            "clause below, the courts at {jurisdiction_city} shall have exclusive jurisdiction "
            "over any dispute arising out of it."
        ),
    },
    {
        "code": "arbitration", "title": "Dispute resolution", "category": "legal",
        "applies_to": CONTRACTS, "is_required": 1, "sort_order": 61,
        "body": (
            "The parties shall first attempt to resolve any dispute by discussion in good "
            "faith for thirty days. Failing that, the dispute shall be referred to "
            "arbitration by a sole arbitrator appointed by agreement between the parties, "
            "under the Arbitration and Conciliation Act, 1996. The seat of arbitration shall "
            "be {arbitration_seat}, the proceedings shall be conducted in English, and the "
            "award shall be final and binding. Nothing here prevents either party from "
            "seeking interim relief from a court."
        ),
    },
    {
        "code": "esignature", "title": "Electronic acceptance", "category": "legal",
        "applies_to": ALL, "is_required": 1, "sort_order": 62,
        "body": (
            "Acceptance of this document by clicking to accept on the link provided, by "
            "replying in writing by email or WhatsApp, or by making the first payment, "
            "constitutes valid acceptance and is treated as an electronic record under the "
            "Information Technology Act, 2000. The name typed, the date, time and IP address "
            "recorded at acceptance are retained as evidence of it."
        ),
    },
    {
        "code": "entire-agreement", "title": "Entire agreement", "category": "legal",
        "applies_to": CONTRACTS, "sort_order": 63,
        "body": (
            "This document, together with any annexure referred to in it, is the entire "
            "agreement between the parties on this engagement and supersedes earlier "
            "discussions, proposals and correspondence. No variation is effective unless "
            "agreed in writing. If any provision is held unenforceable, the rest continues in "
            "force. Neither party may assign this agreement without the other's written "
            "consent, except to a successor of its whole business."
        ),
    },
    {
        "code": "notices", "title": "Notices", "category": "legal",
        "applies_to": CONTRACTS, "sort_order": 64,
        "body": (
            "A notice under this document is validly given if sent by email to the addresses "
            "stated in it, and is treated as received on the next working day. A change of "
            "address takes effect only once notified in the same way."
        ),
    },
    {
        "code": "independent-contractor", "title": "Relationship of the parties",
        "category": "legal", "applies_to": CONTRACTS, "sort_order": 65,
        "body": (
            "{brand} is an independent contractor. Nothing in this document creates an "
            "employment relationship, partnership, joint venture or agency between the "
            "parties, and neither party may hold itself out as able to bind the other."
        ),
    },
    {
        "code": "nda-mutual", "title": "Mutual non-disclosure", "category": "legal",
        "applies_to": "nda", "is_required": 1, "sort_order": 66,
        "body": (
            "Each party may disclose confidential information to the other for the purpose of "
            "evaluating and carrying out a possible engagement. The receiving party shall use "
            "it only for that purpose, disclose it only to those of its personnel who need it "
            "and are under equivalent obligations, and return or destroy it on request. This "
            "obligation lasts three years from the date of disclosure. Neither party is "
            "obliged by this document to proceed with any engagement."
        ),
    },
]


# ── the four public legal pages ─────────────────────────────────────────────
LEGAL_PAGES = [
    {
        "slug": "privacy-policy", "title": "Privacy policy", "sort_order": 0,
        "intro": "What we collect, why, and what you can ask us to do about it.",
        "body": """## Who we are

{brand} is a digital studio based in {city}, {state}, India. This policy explains
how we handle personal data on this website, and it is written to meet the Digital
Personal Data Protection Act, 2023.

Our contact for anything on this page is {email}.

## What we collect

**When you send an enquiry or build an estimate.** Your name, company, email,
phone number, city, and whatever you write in the message. We also record which
page you arrived from and any campaign tag on the link, so we know which of our
efforts actually reach people.

**When you raise a support ticket.** Your name, email, phone number, and the
description and screenshots you send us.

**When you sign in to the client portal.** Your email address, and a record of
each sign-in attempt with its time and IP address.

**Automatically.** Your IP address and browser user-agent for each form
submission, which is how we stop automated spam.

We do not collect payment card details on this site. Where you pay us, you do so
through your own bank, UPI app or a payment gateway, and we see only that the
payment arrived.

## Why we collect it

To reply to you, to prepare a quotation, to carry out work you have engaged us
for, to raise and collect invoices, to provide support, and to keep the records
that Indian tax and company law require us to keep. We do not sell personal data,
and we do not use it to train anything.

## Consent, and withdrawing it

Where we rely on your consent, you gave it by submitting a form on this site
having read this notice. You can withdraw it at any time by emailing {email},
and we will stop processing on that basis. Withdrawal does not affect records we
are legally required to retain, such as issued invoices.

## Marketing messages

We message you on WhatsApp or email only about work you have enquired about or
engaged us for. Reply STOP on WhatsApp, or ask us by email, and we will add you
to our opt-out list, after which our system will not message you again.

## How long we keep it

Enquiries that do not become projects: two years, then deleted. Client records,
invoices and documents: eight years from the end of the relevant financial year,
because that is what tax law requires. Support tickets: three years. Sign-in
attempt logs: ninety days.

## Who else sees it

Only the people who need to: our own team, our hosting provider, our email
provider, and where relevant an accountant. We do not transfer personal data
outside India except where a service provider we have named to you operates
there. Every provider we use is bound to process data only on our instructions.

## Your rights

Under the DPDP Act you may ask us for a copy of the personal data we hold about
you, ask us to correct or complete it, ask us to erase it where we are not
required to keep it, and nominate someone to exercise these rights if you cannot.
Write to {email} and we will respond within thirty days.

If you are not satisfied with our response, you may complain to the Data
Protection Board of India.

## Cookies

This site uses a session cookie so forms work and so you stay signed in to the
portal. If analytics is enabled, it also sets analytics cookies to count visits
in aggregate. Nothing here follows you across other websites, and we run no
advertising trackers.

## Security

Passwords are stored hashed, never in readable form. Sign-in is rate limited.
Stored client credentials, where we hold any, are encrypted with a key kept
outside the database. We will tell you without undue delay if a breach affects
your data.

## Changes

If we change this policy we will update the date below. Material changes will be
notified to clients by email.
""",
    },
    {
        "slug": "terms-of-service", "title": "Terms of service", "sort_order": 1,
        "intro": "The terms on which we work together.",
        "body": """## These terms

These terms govern your use of this website and, unless a signed proposal or
agreement says otherwise, our engagements. Where a proposal and these terms
conflict, the proposal wins for that engagement.

"We" and "us" mean {brand}, {city}, {state}, India. "You" means the person or
business engaging us.

## Using this site

You may read, print and share the content here. Please do not copy our copy, our
designs or our code for your own commercial use, scrape the site, attempt to
break into it, or use it to send anything unlawful.

Estimates produced by the calculator on this site are real numbers from our real
rate card, but they are estimates. A written quotation is what binds us, and it
is valid for the period stated on it.

## How an engagement starts

We send a written proposal setting out scope, price, timeline and terms. You
accept it - by clicking accept on the link, by replying in writing, or by making
the first payment. Work begins once the first milestone payment is received.

## What you provide

Content, brand files, product data and access to your domain, hosting and
accounts, in usable form. One named person who can give approvals. Timelines run
from when we have what we need, and pause while we are waiting on you.

## Scope and changes

Our proposal states what is included and what is not. Anything else is a change:
we will price it and tell you what it does to the timeline before we do it.

## Payment

Milestones as stated in the proposal, each invoice due within {terms_days} days.
Interest of {late_fee_pct}% per month applies to overdue amounts, and we may pause
work on an account that is thirty days overdue. Where you are required to deduct
TDS, deduct it and send us the certificate.

Third-party costs - domains, hosting, licences, gateway fees, model usage - are
billed at actuals unless the proposal includes them for a stated period.

## Ownership

Once you have paid in full, the work we made for you is yours: designs, content
we wrote, custom code. Our own reusable tools and know-how remain ours, licensed
to you as part of what we delivered. Your domain is registered in your name and
stays yours whatever happens between us.

## What we promise, and what we do not

We do the work with reasonable skill and care, and we fix defects free during the
support period stated in your proposal. We do not promise a search ranking, a
conversion rate or a revenue figure, and you should be suspicious of anyone who
does.

Our total liability is capped at the fees you have paid us in the preceding twelve
months. Neither of us is liable to the other for indirect or consequential loss.

## Support

Support during the stated period covers faults in what we built. New features,
content changes, training, and problems caused by changes made by others are
chargeable. Our response and resolution targets by priority are published on the
support page.

## Ending it

Either of us can stop with fifteen days' written notice, or immediately for an
unremedied material breach. You pay for work done and costs committed; we hand
over the work as it stands and the credentials for anything you own.

## Disputes

Indian law applies. We talk first, for thirty days. If that fails, a sole
arbitrator under the Arbitration and Conciliation Act, 1996, seated at
{arbitration_seat}, in English. Courts at {jurisdiction_city} otherwise.

## Getting in touch

{email} or {phone}. We answer.
""",
    },
    {
        "slug": "refund-policy", "title": "Refund and cancellation policy", "sort_order": 2,
        "intro": "What happens to money already paid if a project stops.",
        "body": """## The short version

You pay in milestones, so at any point you have only paid for work that is either
done or about to start. If you cancel before a milestone begins, that milestone's
money comes back. Money for work already done does not, because the time has
already been spent.

## Cancelling before work starts

Cancel before we start work on a milestone and we refund what you paid for it in
full, within fifteen working days, to the account it came from. We deduct only
third-party costs already committed on your instruction - a domain we registered,
a licence we bought, a subscription we started.

## Cancelling mid-milestone

We stop, tell you honestly how far the milestone got, and invoice for that
proportion. If you have paid more than that, the balance is refunded within
fifteen working days. If you have paid less, the difference is due.

## What is never refundable

Domain registrations, third-party licences, plugins, stock assets, hosting
already consumed, and payment gateway charges. Those vendors do not refund them
to us, so we cannot refund them to you. We will always tell you before committing
one of these on your behalf.

Advance payments for support hours or a care plan are refundable pro rata for the
unused portion, less any hours already used.

## If we are the ones who stop

If we cannot finish - for any reason - we refund every rupee for work not yet
delivered, hand over what exists in usable form, and transfer the credentials for
anything registered in your name. We do not keep money for work we did not do.

## Deemed acceptance

When we tell you a deliverable is ready, you have seven days to accept it or to
list specific defects. After that it counts as accepted and the milestone payment
becomes due. This is not a trick to close things early; it exists so a project
cannot sit in limbo with neither of us knowing where it stands.

## Chargebacks

Please talk to us before raising a dispute with your bank. Every case we have
seen was a misunderstanding that a phone call would have fixed in five minutes.

## How to ask

Email {email} with your invoice number and what you would like to happen. We will
reply within three working days, and refunds are processed within fifteen working
days of being agreed.
""",
    },
    {
        "slug": "sla", "title": "Support and service levels", "sort_order": 3,
        "intro": "What we promise on response and resolution, and what counts as what.",
        "body": """## How to reach us

Raise a ticket on the support page. You get a reference immediately, and the clock
starts the moment it is logged. WhatsApp and email work too, but a ticket is the
only channel with a promise attached, because it is the only one that cannot get
buried.

For anything down and losing money, raise a P1 ticket and then call. Do both.

## Priorities

**P1 - down.** The site or application is unreachable, or payments are failing.
Nothing else we are doing matters until this is fixed.

**P2 - broken.** Something important does not work - a form, a login, a key page -
but you can operate around it for now.

**P3 - normal.** A change, a question, a cosmetic fault. Most requests belong
here, and being honest about that is what protects the P1 promise.

**P4 - whenever.** A nice-to-have, batched with other work.

## Our targets

Response and resolution targets for each priority are shown live on the support
page, because they are configurable and we would rather you read the current
numbers than a copy of them. Response means a human has looked at it and replied
with what is happening - not an automated acknowledgement.

Targets are measured in hours from when the ticket is logged, and the resolution
clock pauses while we are waiting on you for information or access. It restarts
when you reply.

## What support covers

Faults in what we built, during your support period or under a care plan. That
includes things that stopped working, things that never worked as specified, and
security or availability problems on hosting we manage.

## What is chargeable

New features and changes of scope, content updates outside a care plan, training,
problems caused by changes someone else made, third-party services breaking or
changing their terms, and recovery of data you deleted. We will always tell you it
is chargeable and what it will cost before doing it, and if it is small we will
often just do it.

## Care plans

A care plan converts support from something you buy in a crisis into something
that is already there: updates, backups, monitoring, and a bank of hours each
month for small changes. Plans and prices are on the pricing page.

## When we miss

If we miss a target we say so, explain why, and where a care plan is in force we
credit the following month's fee proportionately. We would rather do that than
argue about a definition.

## Hours

{hours_note} Outside those hours, P1 tickets are still monitored and answered.
""",
    },
]
