"""The document builder: clause library, drafting, PDF, share links, acceptance."""

from __future__ import annotations

from flask import (Response, abort, current_app, flash, redirect, render_template,
                   request, url_for)

from blueprints.admin import bp
from core import audit, crud, db, documents, pricing, settings
from core.auth import require_role, verify_csrf
from core.crud import Field, Resource
from core.util import load_json, parse_int, slugify
from services import pdf


# ── clause library ──────────────────────────────────────────────────────────
CLAUSES = Resource(
    key="clauses", table="clause_library", label="Clause", label_plural="Clause library",
    area="documents", row_label="title", activatable=True, sortable=True,
    searchable=("code", "title", "body"), icon="shield", deletable=True,
    intro="The wording that goes into your proposals and contracts. Every clause carries a "
          "version - editing the text of one a client already accepted would rewrite history, "
          "so raise the version instead and the old document keeps rendering the old words.",
    list_columns=[("title", "Clause"), ("code", "Code"), ("category", "Category"),
                  ("version", "Version"), ("is_required", "Always")],
    fields=[
        Field("title", "Heading", "text", required=True, span=8,
              help="Appears as the numbered heading in the terms section."),
        Field("code", "Code", "text", required=True, span=4,
              help="Groups the versions of one clause together. Keep it stable."),
        Field("category", "Category", "select", span=6,
              options=lambda: list(documents.CLAUSE_CATEGORIES.items()),
              default="commercial"),
        Field("applies_to", "Applies to", "csv", span=6, default="proposal,sow,amc",
              help="Document kinds, comma separated: proposal, sow, amc, quotation, "
                   "agreement, nda."),
        Field("body", "Text", "textarea", rows=12, required=True, span=12,
              help="Blank lines separate paragraphs; a line starting with a dash becomes a "
                   "bullet. Tokens filled at render time: {{ brand }}, {{ legal_name }}, "
                   "{{ client }}, {{ jurisdiction }}, {{ state }}, {{ late_interest }}, "
                   "{{ validity_days }}, {{ acceptance_days }}, {{ support_months }}, "
                   "{{ revisions }}, {{ gst_rate }}, {{ total }}, {{ ref }}."),
        Field("ver_head", "Version", "heading",
              help="Bump this and save as a new row when the wording changes materially. "
                   "The picker only offers the highest version of each code."),
        Field("version", "Version", "int", span=4, default=1),
        Field("effective_from", "Effective from", "date", span=4),
        Field("is_required", "Include in every document", "bool", span=4,
              help="Ticked, it is pre-selected on a new document of any kind it applies to."),
        Field("is_active", "Active", "bool", span=4, default=1),
    ],
)

crud.register(bp, CLAUSES)


# ── list ────────────────────────────────────────────────────────────────────
@bp.route("/documents")
@require_role("documents")
def documents_list():
    kind = request.args.get("kind") or ""
    status = request.args.get("status") or ""
    query = (request.args.get("q") or "").strip()

    documents.expire_stale()

    where, params = ["1 = 1"], []
    if kind:
        where.append("d.kind = ?")
        params.append(kind)
    if status:
        where.append("d.status = ?")
        params.append(status)
    if query:
        where.append("(d.ref LIKE ? OR d.title LIKE ? OR l.name LIKE ? OR c.name LIKE ?)")
        params += [f"%{query}%"] * 4

    rows = db.query(
        f"""SELECT d.*, l.name AS lead_name, c.name AS client_name, q.total AS quote_total,
                   s.token AS share_token, s.views AS share_views, s.expires_on AS share_expires
            FROM documents d
            LEFT JOIN leads l   ON l.id = d.lead_id
            LEFT JOIN clients c ON c.id = d.client_id
            LEFT JOIN quotes q  ON q.id = d.quote_id
            LEFT JOIN document_shares s ON s.id = (
              SELECT id FROM document_shares WHERE document_id = d.id AND revoked_at IS NULL
              ORDER BY id DESC LIMIT 1)
            WHERE {' AND '.join(where)}
            ORDER BY d.id DESC LIMIT 300""", tuple(params))

    return render_template(
        "admin/documents_list.html", title="Documents", rows=rows, kind=kind, status=status,
        q=query, kinds=documents.KINDS, statuses=documents.STATUSES,
        counts={r["status"]: r["n"] for r in db.query(
            "SELECT status, COUNT(*) AS n FROM documents GROUP BY status")},
        nav_active="admin.documents_list")


# ── create ──────────────────────────────────────────────────────────────────
@bp.route("/documents/new", methods=["GET", "POST"])
@require_role("documents")
def document_new():
    kind = request.args.get("kind") or "proposal"
    quote_id = parse_int(request.args.get("quote_id"), 0) or None
    lead_id = parse_int(request.args.get("lead_id"), 0) or None
    client_id = parse_int(request.args.get("client_id"), 0) or None

    quote = pricing.get_quote(quote_id) if quote_id else None
    if quote:
        lead_id = lead_id or quote["lead_id"]
        client_id = client_id or quote["client_id"]

    lead = db.one("SELECT * FROM leads WHERE id = ?", (lead_id,)) if lead_id else None
    client = db.one("SELECT * FROM clients WHERE id = ?", (client_id,)) if client_id else None
    package = db.one("SELECT * FROM packages WHERE id = ?", (quote["package_id"],)) \
        if quote and quote["package_id"] else None

    if request.method == "POST":
        verify_csrf()
        kind = request.form.get("kind") or "proposal"
        title = (request.form.get("title") or "").strip()
        if not title:
            flash("Give the document a title - the client sees it on the cover.", "error")
            return redirect(request.url)

        document_id = documents.create(
            kind=kind, title=title,
            quote_id=parse_int(request.form.get("quote_id"), 0) or None,
            lead_id=parse_int(request.form.get("lead_id"), 0) or None,
            client_id=parse_int(request.form.get("client_id"), 0) or None,
            body={key: (request.form.get(key) or "") for key in documents.BODY_FIELDS},
            clause_ids=[parse_int(c, 0) for c in request.form.getlist("clause_ids")])
        flash("Draft created. Read it once, then share it.", "ok")
        return redirect(url_for("admin.document_detail", document_id=document_id))

    party = client or lead
    body = documents.default_body(kind, quote=quote, package=package, party=party)
    suggested = "%s - %s" % (
        documents.KINDS.get(kind, "Document"),
        (party["name"] if party is not None else settings.get("brand.name")))

    return render_template(
        "admin/document_form.html", title="New document", kind=kind, kinds=documents.KINDS,
        quote=quote, lead=lead, client=client, body=body, suggested=suggested,
        clauses=documents.clauses_for(kind),
        selected=set(body.get("clause_ids") or []),
        categories=documents.CLAUSE_CATEGORIES,
        fields=documents.BODY_FIELDS, document=None,
        nav_active="admin.documents_list")


# ── detail and edit ─────────────────────────────────────────────────────────
@bp.route("/documents/<int:document_id>", methods=["GET", "POST"])
@require_role("documents")
def document_detail(document_id):
    document = documents.get(document_id)
    if not document:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        if document["status"] == "accepted":
            flash("This document has been accepted. Raise a new version rather than "
                  "editing what was agreed.", "error")
            return redirect(url_for("admin.document_detail", document_id=document_id))

        documents.save_body(
            document_id,
            {key: (request.form.get(key) or "") for key in documents.BODY_FIELDS},
            [parse_int(c, 0) for c in request.form.getlist("clause_ids")])
        changes = {
            "title": (request.form.get("title") or document["title"]).strip()[:300],
            "valid_until": (request.form.get("valid_until") or "").strip() or None,
        }
        db.update("documents", document_id, changes)
        audit.log("update", "documents", document_id, document["ref"], after=changes)
        flash("Document saved.", "ok")
        return redirect(url_for("admin.document_detail", document_id=document_id))

    body = load_json(document["body_json"], {})
    quote = pricing.get_quote(document["quote_id"]) if document["quote_id"] else None
    return render_template(
        "admin/document_detail.html", title=document["ref"], document=document, body=body,
        quote=quote, summary=pricing.quote_summary(document["quote_id"]) if quote else {},
        kinds=documents.KINDS, statuses=documents.STATUSES,
        clauses=documents.clauses_for(document["kind"], active_only=False),
        chosen=documents.clauses_for(document["kind"], active_only=False),
        selected=set(body.get("clause_ids") or []),
        categories=documents.CLAUSE_CATEGORIES, fields=documents.BODY_FIELDS,
        share=documents.live_share(document_id), all_shares=documents.shares(document_id),
        views=documents.views(document_id),
        lead=db.one("SELECT * FROM leads WHERE id = ?", (document["lead_id"],))
        if document["lead_id"] else None,
        client=db.one("SELECT * FROM clients WHERE id = ?", (document["client_id"],))
        if document["client_id"] else None,
        public_base=_public_base(), nav_active="admin.documents_list")


def _public_base() -> str:
    return (current_app.config.get("PUBLIC_BASE_URL")
            or request.host_url.rstrip("/"))


# ── the PDF ─────────────────────────────────────────────────────────────────
@bp.route("/documents/<int:document_id>/pdf")
@require_role("documents")
def document_pdf(document_id):
    document = documents.get(document_id)
    if not document:
        abort(404)
    payload = pdf.proposal_pdf(document)
    filename = "%s-%s.pdf" % (slugify(documents.KINDS.get(document["kind"], "document")),
                              document["ref"])
    inline = request.args.get("download") != "1"
    return Response(payload, mimetype="application/pdf", headers={
        "Content-Disposition": "%s; filename=%s" % ("inline" if inline else "attachment", filename),
        "Cache-Control": "no-store",
    })


# ── status, versions and shares ─────────────────────────────────────────────
@bp.route("/documents/<int:document_id>/status", methods=["POST"])
@require_role("documents")
def document_status(document_id):
    verify_csrf()
    status = request.form.get("status") or ""
    if status not in documents.STATUSES:
        abort(400, "Unknown status.")
    if status == "accepted":
        documents.accept(document_id,
                         name=(request.form.get("accepted_by") or documents.author_name()),
                         ip="", note="Marked accepted in the panel.")
        flash("Marked accepted. The quote and the lead moved with it.", "ok")
    else:
        documents.set_status(document_id, status, request.form.get("note") or "")
        flash(f"Marked {documents.STATUSES[status].lower()}.", "ok")
    return redirect(url_for("admin.document_detail", document_id=document_id))


@bp.route("/documents/<int:document_id>/version", methods=["POST"])
@require_role("documents")
def document_version(document_id):
    verify_csrf()
    try:
        new_id = documents.new_version(document_id)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.documents_list"))
    flash("New version drafted. The previous one is kept and marked superseded, and its "
          "share link is revoked.", "ok")
    return redirect(url_for("admin.document_detail", document_id=new_id))


@bp.route("/documents/<int:document_id>/share", methods=["POST"])
@require_role("documents")
def document_share(document_id):
    verify_csrf()
    days = parse_int(request.form.get("days"), 0) or None
    try:
        token = documents.share(document_id, days)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.documents_list"))
    flash("Share link created. Any earlier link for this document no longer works.", "ok")
    return redirect(url_for("admin.document_detail", document_id=document_id,
                            _anchor="share-" + token[:6]))


@bp.route("/documents/<int:document_id>/unshare", methods=["POST"])
@require_role("documents")
def document_unshare(document_id):
    verify_csrf()
    count = documents.revoke_shares(document_id)
    flash(f"Revoked {count} link(s). Anyone holding one now sees a polite dead end."
          if count else "There was no live link to revoke.", "ok")
    return redirect(url_for("admin.document_detail", document_id=document_id))


@bp.route("/documents/<int:document_id>/delete", methods=["POST"])
@require_role("owner")
def document_delete(document_id):
    verify_csrf()
    document = documents.get(document_id)
    if not document:
        abort(404)
    if document["status"] == "accepted":
        flash("An accepted document is the record of what was agreed. It stays.", "error")
        return redirect(url_for("admin.document_detail", document_id=document_id))
    db.delete("documents", document_id)
    audit.log("delete", "documents", document_id, document["ref"], before=document)
    flash("Document deleted.", "ok")
    return redirect(url_for("admin.documents_list"))
