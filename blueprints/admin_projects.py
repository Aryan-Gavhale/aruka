"""Delivery: projects, the task board, launch checklist, the asset and credential
vault, referrals and review requests.

The vault is the one place in the panel that writes ciphertext. Reading a secret
back is owner-only and audited, so "who looked at the client's hosting password"
has an answer.
"""

from __future__ import annotations

from flask import abort, flash, jsonify, redirect, render_template, request, url_for

from blueprints.admin import bp
from core import audit, billing, crud, crypto, db, leads, numbering, projects, settings
from core.auth import current_user, require_role, verify_csrf
from core.crud import Field, Resource
from core.util import days_until, parse_bool, parse_float, parse_int, today_iso

PROJECT_STATUSES = projects.STATUSES
HEALTH = projects.HEALTH
TASK_COLUMNS = projects.TASK_COLUMNS
ASSET_KINDS = {
    "domain": "Domain",
    "hosting": "Hosting",
    "ssl": "SSL certificate",
    "email": "Email or mailbox",
    "dns": "DNS",
    "cdn": "CDN",
    "api": "API or third-party key",
    "repo": "Code repository",
    "analytics": "Analytics",
    "other": "Something else",
}


# ── projects ────────────────────────────────────────────────────────────────
@bp.route("/projects")
@require_role("projects")
def projects_list():
    status = request.args.get("status") or "live"
    query = (request.args.get("q") or "").strip()

    sql = ("SELECT p.*, c.name AS client_name, "
           "(SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.status != 'done') "
           "AS open_tasks, "
           "(SELECT COUNT(*) FROM tickets k WHERE k.project_id = p.id "
           " AND k.status IN ('open','in_progress','waiting_client')) AS live_tickets "
           "FROM projects p JOIN clients c ON c.id = p.client_id WHERE 1 = 1")
    args: list = []
    if status == "live":
        sql += " AND p.status IN ('planned','active','review')"
    elif status in PROJECT_STATUSES:
        sql += " AND p.status = ?"
        args.append(status)
    if query:
        sql += " AND (p.name LIKE ? OR p.ref LIKE ? OR c.name LIKE ?)"
        args += [f"%{query}%"] * 3
    sql += " ORDER BY p.target_on IS NULL, p.target_on, p.id DESC"

    rows = db.query(sql, args)
    counts = {r["status"]: r["n"] for r in db.query(
        "SELECT status, COUNT(*) AS n FROM projects GROUP BY status")}
    counts["live"] = sum(counts.get(s, 0) for s in ("planned", "active", "review"))

    return render_template(
        "admin/projects_list.html", title="Projects", rows=rows, status=status, q=query,
        counts=counts, statuses=PROJECT_STATUSES, health=HEALTH,
        nav_active="admin.projects_list")


@bp.route("/projects/new", methods=["GET", "POST"])
@require_role("projects")
def project_new():
    client_id = parse_int(request.args.get("client_id"), 0) or None

    if request.method == "POST":
        verify_csrf()
        data = _read_project_form(request.form)
        if not data["client_id"] or not data["name"]:
            flash("A project needs a client and a name.", "error")
            return redirect(request.url)
        data["ref"] = numbering.take("project")
        project_id = db.insert("projects", data)
        audit.log("create", "projects", project_id, data["name"], after=data)

        if parse_bool(request.form.get("seed_milestones")):
            billing.seed_milestones(project_id)
        if parse_bool(request.form.get("seed_checklist")):
            leads.seed_launch_checklist(project_id)

        flash("Project created.", "ok")
        return redirect(url_for("admin.project_detail", project_id=project_id))

    return render_template(
        "admin/project_form.html", title="New project", project=None,
        clients=db.query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name"),
        services=db.query("SELECT id, name FROM services WHERE is_published = 1 "
                          "ORDER BY sort_order"),
        packages=db.query("SELECT id, name, price FROM packages WHERE is_active = 1 "
                          "ORDER BY sort_order"),
        client_id=client_id, statuses=PROJECT_STATUSES, health=HEALTH,
        schedule=settings.get("doc.milestone_split") or [],
        nav_active="admin.projects_list")


def _read_project_form(form) -> dict:
    return {
        "client_id": parse_int(form.get("client_id"), 0) or None,
        "name": (form.get("name") or "").strip()[:200],
        "service_id": parse_int(form.get("service_id"), 0) or None,
        "package_id": parse_int(form.get("package_id"), 0) or None,
        "status": form.get("status") if form.get("status") in PROJECT_STATUSES else "planned",
        "health": form.get("health") if form.get("health") in HEALTH else "green",
        "billing_type": form.get("billing_type") or "milestone",
        "value": parse_float(form.get("value"), 0),
        "internal_cost": parse_float(form.get("internal_cost"), 0),
        "retainer_amount": parse_float(form.get("retainer_amount"), 0),
        "recurring_yearly": parse_float(form.get("recurring_yearly"), 0),
        "progress_pct": max(0, min(100, parse_int(form.get("progress_pct"), 0))),
        "start_on": form.get("start_on") or None,
        "target_on": form.get("target_on") or None,
        "launched_on": form.get("launched_on") or None,
        "notes": (form.get("notes") or "").strip(),
    }


@bp.route("/projects/<int:project_id>", methods=["GET", "POST"])
@require_role("projects")
def project_detail(project_id):
    project = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        abort(404)

    if request.method == "POST":
        verify_csrf()
        data = _read_project_form(request.form)
        data.pop("client_id", None)          # moving a project between clients is not a thing
        if data["status"] == "launched" and not data["launched_on"]:
            data["launched_on"] = today_iso()
        if data["status"] in ("closed", "cancelled"):
            data["closed_on"] = project["closed_on"] or today_iso()
        db.update("projects", project_id, data)
        audit.log("update", "projects", project_id, project["name"],
                  before=project, after=data)
        flash("Project saved.", "ok")
        return redirect(url_for("admin.project_detail", project_id=project_id))

    tasks = db.query("SELECT * FROM tasks WHERE project_id = ? ORDER BY sort_order, id",
                     (project_id,))
    board = {key: [t for t in tasks if t["status"] == key] for key in TASK_COLUMNS}
    checklist = db.query(
        "SELECT * FROM launch_checklist WHERE project_id = ? ORDER BY sort_order, id",
        (project_id,))

    return render_template(
        "admin/project_detail.html", title=project["name"], project=project,
        client=db.one("SELECT * FROM clients WHERE id = ?", (project["client_id"],)),
        milestones=billing.milestones(project_id), board=board, columns=TASK_COLUMNS,
        checklist=checklist,
        done_steps=len([c for c in checklist if c["is_done"]]),
        pl=billing.project_pl(project_id),
        invoices=db.query("SELECT * FROM invoices WHERE project_id = ? ORDER BY id DESC",
                          (project_id,)),
        assets=db.query("SELECT * FROM assets WHERE project_id = ? ORDER BY expires_on IS NULL, "
                        "expires_on", (project_id,)),
        credentials=db.query("SELECT * FROM credentials WHERE project_id = ? ORDER BY label",
                             (project_id,)),
        tickets_rows=db.query("SELECT * FROM tickets WHERE project_id = ? ORDER BY id DESC LIMIT 10",
                              (project_id,)),
        recurring=db.query("SELECT * FROM recurring_items WHERE project_id = ? ORDER BY next_due_on",
                           (project_id,)),
        quote=db.one("SELECT * FROM quotes WHERE id = ?", (project["quote_id"],))
        if project["quote_id"] else None,
        users=db.query("SELECT id, name FROM users WHERE is_active = 1 ORDER BY name"),
        statuses=PROJECT_STATUSES, health=HEALTH,
        services=db.query("SELECT id, name FROM services ORDER BY sort_order"),
        packages=db.query("SELECT id, name, price FROM packages ORDER BY sort_order"),
        nav_active="admin.projects_list")


@bp.route("/projects/<int:project_id>/delete", methods=["POST"])
@require_role("owner")
def project_delete(project_id):
    verify_csrf()
    project = db.one("SELECT * FROM projects WHERE id = ?", (project_id,))
    if not project:
        abort(404)
    if db.scalar("SELECT COUNT(*) FROM invoices WHERE project_id = ?", (project_id,), 0):
        flash("This project has invoices against it. Close or cancel it instead - deleting "
              "would leave the money records pointing at nothing.", "error")
        return redirect(url_for("admin.project_detail", project_id=project_id))
    db.delete("projects", project_id)
    audit.log("delete", "projects", project_id, project["name"], before=project)
    flash("Project deleted.", "ok")
    return redirect(url_for("admin.projects_list"))


# ── milestones ──────────────────────────────────────────────────────────────
@bp.route("/projects/<int:project_id>/milestones", methods=["POST"])
@require_role("projects")
def milestone_add(project_id):
    verify_csrf()
    action = request.form.get("action")

    if action == "seed":
        if billing.milestones(project_id):
            flash("This project already has a schedule. Clear it first if you want the "
                  "default one back.", "error")
        else:
            billing.seed_milestones(project_id)
            flash("Payment schedule added from your settings.", "ok")
        return redirect(url_for("admin.project_detail", project_id=project_id))

    label = (request.form.get("label") or "").strip()
    if not label:
        flash("A milestone needs a label.", "error")
        return redirect(url_for("admin.project_detail", project_id=project_id))
    db.insert("milestones", {
        "project_id": project_id,
        "label": label[:200],
        "description": (request.form.get("description") or "").strip(),
        "invoice_pct": parse_float(request.form.get("invoice_pct"), 0),
        "amount": parse_float(request.form.get("amount"), 0),
        "due_on": request.form.get("due_on") or None,
        "sort_order": db.next_sort_order("milestones", "project_id = ?", (project_id,)),
    })
    flash("Milestone added.", "ok")
    return redirect(url_for("admin.project_detail", project_id=project_id))


@bp.route("/milestones/<int:milestone_id>/done", methods=["POST"])
@require_role("projects")
def milestone_done(milestone_id):
    verify_csrf()
    ms = db.one("SELECT * FROM milestones WHERE id = ?", (milestone_id,))
    if not ms:
        abort(404)
    done = not ms["done_on"]
    db.update("milestones", milestone_id, {
        "done_on": today_iso() if done else None,
        "status": "done" if done else ("invoiced" if ms["invoice_id"] else "pending"),
    })
    flash("Milestone marked done." if done else "Milestone reopened.", "ok")
    return redirect(url_for("admin.project_detail", project_id=ms["project_id"]))


@bp.route("/milestones/<int:milestone_id>/delete", methods=["POST"])
@require_role("projects")
def milestone_delete(milestone_id):
    verify_csrf()
    ms = db.one("SELECT * FROM milestones WHERE id = ?", (milestone_id,))
    if not ms:
        abort(404)
    if ms["invoice_id"]:
        flash("That milestone has been invoiced, so it stays as a record.", "error")
    else:
        db.delete("milestones", milestone_id)
        flash("Milestone removed.", "ok")
    return redirect(url_for("admin.project_detail", project_id=ms["project_id"]))


# ── tasks ───────────────────────────────────────────────────────────────────
@bp.route("/projects/<int:project_id>/tasks", methods=["POST"])
@require_role("projects")
def task_add(project_id):
    verify_csrf()
    title = (request.form.get("title") or "").strip()
    if not title:
        flash("A task needs a title.", "error")
        return redirect(url_for("admin.project_detail", project_id=project_id))
    db.insert("tasks", {
        "project_id": project_id,
        "milestone_id": parse_int(request.form.get("milestone_id"), 0) or None,
        "title": title[:250],
        "notes": (request.form.get("notes") or "").strip(),
        "assignee_user_id": parse_int(request.form.get("assignee_user_id"), 0) or None,
        "status": request.form.get("status") if request.form.get("status") in TASK_COLUMNS else "todo",
        "priority": request.form.get("priority") or "normal",
        "estimate_hours": parse_float(request.form.get("estimate_hours"), 0),
        "due_on": request.form.get("due_on") or None,
        "sort_order": db.next_sort_order("tasks", "project_id = ?", (project_id,)),
    })
    _sync_progress(project_id)
    flash("Task added.", "ok")
    return redirect(url_for("admin.project_detail", project_id=project_id))


@bp.route("/tasks/<int:task_id>/move", methods=["POST"])
@require_role("projects")
def task_move(task_id):
    verify_csrf()
    task = db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        abort(404)
    status = (request.form.get("status")
              or (request.get_json(silent=True) or {}).get("status") or "")
    if status not in TASK_COLUMNS:
        abort(400, "Unknown column.")
    db.update("tasks", task_id, {
        "status": status,
        "done_at": db.scalar("SELECT datetime('now')") if status == "done" else None,
    })
    _sync_progress(task["project_id"])
    if crud.wants_json():
        return jsonify({"ok": True, "status": status,
                        "progress": db.scalar("SELECT progress_pct FROM projects WHERE id = ?",
                                              (task["project_id"],))})
    return redirect(url_for("admin.project_detail", project_id=task["project_id"]))


@bp.route("/tasks/<int:task_id>", methods=["POST"])
@require_role("projects")
def task_edit(task_id):
    verify_csrf()
    task = db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        abort(404)
    db.update("tasks", task_id, {
        "title": (request.form.get("title") or task["title"]).strip()[:250],
        "notes": (request.form.get("notes") or "").strip(),
        "assignee_user_id": parse_int(request.form.get("assignee_user_id"), 0) or None,
        "priority": request.form.get("priority") or task["priority"],
        "estimate_hours": parse_float(request.form.get("estimate_hours"), 0),
        "actual_hours": parse_float(request.form.get("actual_hours"), 0),
        "due_on": request.form.get("due_on") or None,
    })
    flash("Task updated.", "ok")
    return redirect(url_for("admin.project_detail", project_id=task["project_id"]))


@bp.route("/tasks/<int:task_id>/delete", methods=["POST"])
@require_role("projects")
def task_delete(task_id):
    verify_csrf()
    task = db.one("SELECT * FROM tasks WHERE id = ?", (task_id,))
    if not task:
        abort(404)
    db.delete("tasks", task_id)
    _sync_progress(task["project_id"])
    flash("Task removed.", "ok")
    return redirect(url_for("admin.project_detail", project_id=task["project_id"]))


def _sync_progress(project_id) -> None:
    """Progress is derived from done tasks, so it cannot drift from reality.

    A project with no tasks keeps whatever percentage was typed in, because there
    is nothing to derive it from and zeroing it would be a lie in the other direction.
    """
    total = parse_int(db.scalar("SELECT COUNT(*) FROM tasks WHERE project_id = ?",
                               (project_id,), 0))
    if not total:
        return
    done = parse_int(db.scalar(
        "SELECT COUNT(*) FROM tasks WHERE project_id = ? AND status = 'done'", (project_id,), 0))
    db.update("projects", project_id, {"progress_pct": round(done * 100 / total)})


# ── launch checklist ────────────────────────────────────────────────────────
@bp.route("/projects/<int:project_id>/checklist", methods=["POST"])
@require_role("projects")
def checklist_add(project_id):
    verify_csrf()
    if request.form.get("action") == "seed":
        if db.scalar("SELECT COUNT(*) FROM launch_checklist WHERE project_id = ?",
                     (project_id,), 0):
            flash("There is already a checklist here.", "error")
        else:
            leads.seed_launch_checklist(project_id)
            flash("Launch checklist added.", "ok")
        return redirect(url_for("admin.project_detail", project_id=project_id))

    label = (request.form.get("label") or "").strip()
    if label:
        db.insert("launch_checklist", {
            "project_id": project_id, "label": label[:250],
            "note": (request.form.get("note") or "").strip(),
            "sort_order": db.next_sort_order("launch_checklist", "project_id = ?", (project_id,)),
        })
        flash("Step added.", "ok")
    return redirect(url_for("admin.project_detail", project_id=project_id))


@bp.route("/checklist/<int:step_id>/toggle", methods=["POST"])
@require_role("projects")
def checklist_toggle(step_id):
    verify_csrf()
    step = db.one("SELECT * FROM launch_checklist WHERE id = ?", (step_id,))
    if not step:
        abort(404)
    done = not step["is_done"]
    db.update("launch_checklist", step_id, {
        "is_done": 1 if done else 0,
        "done_at": db.scalar("SELECT datetime('now')") if done else None,
    })
    if crud.wants_json():
        return jsonify({"ok": True, "on": done})
    return redirect(url_for("admin.project_detail", project_id=step["project_id"]))


@bp.route("/checklist/<int:step_id>/delete", methods=["POST"])
@require_role("projects")
def checklist_delete(step_id):
    verify_csrf()
    step = db.one("SELECT * FROM launch_checklist WHERE id = ?", (step_id,))
    if not step:
        abort(404)
    db.delete("launch_checklist", step_id)
    return redirect(url_for("admin.project_detail", project_id=step["project_id"]))


# ── assets and the credential vault ─────────────────────────────────────────
@bp.route("/vault")
@require_role("vault")
def vault():
    horizon = parse_int(settings.get("ops.expiry_warn_days"), 30)
    rows = db.query(
        "SELECT a.*, c.name AS client_name, p.name AS project_name FROM assets a "
        "JOIN clients c ON c.id = a.client_id "
        "LEFT JOIN projects p ON p.id = a.project_id "
        "WHERE a.is_active = 1 ORDER BY a.expires_on IS NULL, a.expires_on")

    expiring = [r for r in rows if r["expires_on"] and 0 <= days_until(r["expires_on"]) <= horizon]
    expired = [r for r in rows if r["expires_on"] and days_until(r["expires_on"]) < 0]

    return render_template(
        "admin/vault.html", title="Assets and vault", rows=rows, expiring=expiring,
        expired=expired, horizon=horizon, kinds=ASSET_KINDS,
        credentials=db.query(
            "SELECT cr.*, c.name AS client_name FROM credentials cr "
            "JOIN clients c ON c.id = cr.client_id ORDER BY c.name, cr.label"),
        clients=db.query("SELECT id, name FROM clients WHERE is_active = 1 ORDER BY name"),
        projects=db.query("SELECT id, ref, name, client_id FROM projects ORDER BY id DESC"),
        vault_ready=crypto.available(), nav_active="admin.vault")


@bp.route("/vault/assets", methods=["POST"])
@require_role("vault")
def asset_add():
    verify_csrf()
    client_id = parse_int(request.form.get("client_id"), 0) or None
    label = (request.form.get("label") or "").strip()
    if not client_id or not label:
        flash("An asset needs a client and a label.", "error")
        return redirect(url_for("admin.vault"))
    asset_id = db.insert("assets", {
        "client_id": client_id,
        "project_id": parse_int(request.form.get("project_id"), 0) or None,
        "kind": request.form.get("kind") if request.form.get("kind") in ASSET_KINDS else "other",
        "label": label[:200],
        "provider": (request.form.get("provider") or "").strip(),
        "identifier": (request.form.get("identifier") or "").strip(),
        "url": (request.form.get("url") or "").strip(),
        "starts_on": request.form.get("starts_on") or None,
        "expires_on": request.form.get("expires_on") or None,
        "renew_cost": parse_float(request.form.get("renew_cost"), 0),
        "auto_renew": 1 if request.form.get("auto_renew") else 0,
        "owned_by": request.form.get("owned_by") or "client",
        "notes": (request.form.get("notes") or "").strip(),
    })
    audit.log("create", "assets", asset_id, label)

    if parse_bool(request.form.get("make_recurring")):
        db.insert("recurring_items", {
            "client_id": client_id,
            "project_id": parse_int(request.form.get("project_id"), 0) or None,
            "asset_id": asset_id,
            "kind": request.form.get("kind") or "hosting",
            "label": f"{label} renewal",
            "amount": parse_float(request.form.get("renew_price"),
                                  parse_float(request.form.get("renew_cost"), 0) * 2),
            "internal_cost": parse_float(request.form.get("renew_cost"), 0),
            "period": "yearly",
            "next_due_on": request.form.get("expires_on") or None,
        })
        flash("Asset saved, and a yearly renewal item was created for it.", "ok")
    else:
        flash("Asset saved.", "ok")
    return redirect(url_for("admin.vault"))


@bp.route("/vault/assets/<int:asset_id>", methods=["POST"])
@require_role("vault")
def asset_edit(asset_id):
    verify_csrf()
    asset = db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not asset:
        abort(404)
    changes = {
        "label": (request.form.get("label") or asset["label"]).strip()[:200],
        "provider": (request.form.get("provider") or "").strip(),
        "identifier": (request.form.get("identifier") or "").strip(),
        "url": (request.form.get("url") or "").strip(),
        "expires_on": request.form.get("expires_on") or None,
        "renew_cost": parse_float(request.form.get("renew_cost"), 0),
        "auto_renew": 1 if request.form.get("auto_renew") else 0,
        "owned_by": request.form.get("owned_by") or asset["owned_by"],
        "notes": (request.form.get("notes") or "").strip(),
        "is_active": 1 if request.form.get("is_active") else 0,
    }
    db.update("assets", asset_id, changes)
    audit.log("update", "assets", asset_id, asset["label"], before=asset, after=changes)
    flash("Asset updated.", "ok")
    return redirect(request.referrer or url_for("admin.vault"))


@bp.route("/vault/assets/<int:asset_id>/delete", methods=["POST"])
@require_role("vault")
def asset_delete(asset_id):
    verify_csrf()
    asset = db.one("SELECT * FROM assets WHERE id = ?", (asset_id,))
    if not asset:
        abort(404)
    db.delete("assets", asset_id)
    audit.log("delete", "assets", asset_id, asset["label"], before=asset)
    flash("Asset removed.", "ok")
    return redirect(url_for("admin.vault"))


@bp.route("/vault/credentials", methods=["POST"])
@require_role("vault")
def credential_add():
    verify_csrf()
    client_id = parse_int(request.form.get("client_id"), 0) or None
    label = (request.form.get("label") or "").strip()
    secret = request.form.get("secret") or ""
    if not client_id or not label:
        flash("A credential needs a client and a label.", "error")
        return redirect(url_for("admin.vault"))

    row_id = db.insert("credentials", {
        "client_id": client_id,
        "project_id": parse_int(request.form.get("project_id"), 0) or None,
        "label": label[:200],
        "location": (request.form.get("location") or "").strip(),
        "url": (request.form.get("url") or "").strip(),
        "username": (request.form.get("username") or "").strip(),
        "secret_ciphertext": crypto.encrypt(secret) if secret else "",
        "notes": (request.form.get("notes") or "").strip(),
    })
    # Deliberately no `after=` payload: the ciphertext has no business in the log.
    audit.log("create", "credentials", row_id, label)
    flash("Credential stored, encrypted with your vault key.", "ok")
    return redirect(url_for("admin.vault"))


@bp.route("/vault/credentials/<int:row_id>/reveal", methods=["POST"])
@require_role("owner")
def credential_reveal(row_id):
    """Owner-only, and every look is written to the activity log."""
    verify_csrf()
    row = db.one("SELECT * FROM credentials WHERE id = ?", (row_id,))
    if not row:
        abort(404)
    user = current_user()
    audit.log("view", "credentials", row_id, row["label"],
              after={"revealed_by": user["email"] if user else "unknown"})

    if not row["secret_ciphertext"]:
        return jsonify({"ok": True, "secret": "", "username": row["username"],
                        "note": "Nothing was stored for this one - only the location."})
    secret = crypto.decrypt(row["secret_ciphertext"])
    if not secret:
        return jsonify({"ok": False, "error": "That did not decrypt. Either db/vault.key has "
                                              "changed since it was saved, or it was restored "
                                              "from a backup without its key file."}), 400
    return jsonify({"ok": True, "secret": secret, "username": row["username"]})


@bp.route("/vault/credentials/<int:row_id>", methods=["POST"])
@require_role("vault")
def credential_edit(row_id):
    verify_csrf()
    row = db.one("SELECT * FROM credentials WHERE id = ?", (row_id,))
    if not row:
        abort(404)
    changes = {
        "label": (request.form.get("label") or row["label"]).strip()[:200],
        "location": (request.form.get("location") or "").strip(),
        "url": (request.form.get("url") or "").strip(),
        "username": (request.form.get("username") or "").strip(),
        "notes": (request.form.get("notes") or "").strip(),
    }
    secret = request.form.get("secret") or ""
    if secret:
        changes["secret_ciphertext"] = crypto.encrypt(secret)
    db.update("credentials", row_id, changes)
    audit.log("update", "credentials", row_id, row["label"],
              after={k: v for k, v in changes.items() if k != "secret_ciphertext"})
    flash("Credential updated.", "ok")
    return redirect(url_for("admin.vault"))


@bp.route("/vault/credentials/<int:row_id>/delete", methods=["POST"])
@require_role("owner")
def credential_delete(row_id):
    verify_csrf()
    row = db.one("SELECT * FROM credentials WHERE id = ?", (row_id,))
    if not row:
        abort(404)
    db.delete("credentials", row_id)
    audit.log("delete", "credentials", row_id, row["label"])
    flash("Credential deleted.", "ok")
    return redirect(url_for("admin.vault"))


# ── referrals ───────────────────────────────────────────────────────────────
@bp.route("/referrals")
@require_role("billing")
def referrals():
    pct = parse_float(settings.get("crm.referral_payout_pct"), 5)
    referrers = db.query(
        "SELECT c.*, "
        "(SELECT COUNT(*) FROM clients r WHERE r.referred_by_client_id = c.id) AS sent, "
        "(SELECT COUNT(*) FROM leads l WHERE l.referred_by_client_id = c.id) AS leads_sent "
        "FROM clients c WHERE c.referral_code != '' ORDER BY sent DESC, c.name")
    payouts = db.query(
        "SELECT rp.*, c.name AS client_name, i.ref AS invoice_ref FROM referral_payouts rp "
        "JOIN clients c ON c.id = rp.client_id "
        "LEFT JOIN invoices i ON i.id = rp.invoice_id ORDER BY rp.status, rp.id DESC")
    return render_template(
        "admin/referrals.html", title="Referrals", referrers=referrers, payouts=payouts,
        payout_pct=pct,
        due_total=sum(parse_float(p["amount"]) for p in payouts if p["status"] == "due"),
        clients=db.query("SELECT id, name, referral_code FROM clients WHERE is_active = 1 "
                         "ORDER BY name"),
        discount_pct=settings.get("pricing.referral_discount_pct"),
        nav_active="admin.referrals")


@bp.route("/referrals/code/<int:client_id>", methods=["POST"])
@require_role("billing")
def referral_code(client_id):
    verify_csrf()
    client = db.one("SELECT * FROM clients WHERE id = ?", (client_id,))
    if not client:
        abort(404)
    if client["referral_code"]:
        flash(f"{client['name']} already has the code {client['referral_code']}.", "error")
        return redirect(url_for("admin.referrals"))

    from core.util import slugify
    base = (slugify(client["name"]).replace("-", "")[:8] or "aruka").upper()
    code = base
    suffix = 2
    while db.one("SELECT 1 FROM clients WHERE referral_code = ?", (code,)):
        code = f"{base}{suffix}"
        suffix += 1
    db.update("clients", client_id, {"referral_code": code})
    audit.log("update", "clients", client_id, client["name"], after={"referral_code": code})
    flash(f"Code {code} is theirs. Anyone entering it on the pricing page is tagged to them.", "ok")
    return redirect(url_for("admin.referrals"))


@bp.route("/referrals/payouts", methods=["POST"])
@require_role("billing")
def referral_payout_add():
    verify_csrf()
    client_id = parse_int(request.form.get("client_id"), 0) or None
    amount = parse_float(request.form.get("amount"), 0)
    if not client_id or amount <= 0:
        flash("Choose who it is owed to and how much.", "error")
        return redirect(url_for("admin.referrals"))
    db.insert("referral_payouts", {
        "client_id": client_id,
        "lead_id": parse_int(request.form.get("lead_id"), 0) or None,
        "invoice_id": parse_int(request.form.get("invoice_id"), 0) or None,
        "amount": amount,
        "notes": (request.form.get("notes") or "").strip(),
    })
    flash("Payout recorded as due.", "ok")
    return redirect(url_for("admin.referrals"))


@bp.route("/referrals/payouts/<int:payout_id>/paid", methods=["POST"])
@require_role("billing")
def referral_payout_paid(payout_id):
    verify_csrf()
    payout = db.one("SELECT * FROM referral_payouts WHERE id = ?", (payout_id,))
    if not payout:
        abort(404)
    db.update("referral_payouts", payout_id, {
        "status": "paid",
        "paid_on": request.form.get("paid_on") or today_iso(),
        "method": (request.form.get("method") or "UPI").strip(),
        "reference": (request.form.get("reference") or "").strip(),
    })

    # A referral payout is real money leaving, so it belongs in expenses too or the
    # analytics will overstate what the referred work actually earned.
    category = db.one("SELECT id FROM expense_categories WHERE slug = 'referral'")
    db.insert("expenses", {
        "ref": numbering.take("expense"),
        "category_id": category["id"] if category else None,
        "vendor": db.scalar("SELECT name FROM clients WHERE id = ?", (payout["client_id"],)) or "",
        "description": f"Referral payout{' for ' + payout['reference'] if payout['reference'] else ''}",
        "amount": parse_float(payout["amount"]),
        "paid_on": request.form.get("paid_on") or today_iso(),
        "method": (request.form.get("method") or "UPI").strip(),
        "client_id": payout["client_id"],
    })
    flash("Marked paid, and logged as an expense so your margins stay honest.", "ok")
    return redirect(url_for("admin.referrals"))


@bp.route("/referrals/payouts/<int:payout_id>/delete", methods=["POST"])
@require_role("owner")
def referral_payout_delete(payout_id):
    verify_csrf()
    db.execute("DELETE FROM referral_payouts WHERE id = ?", (payout_id,))
    flash("Payout removed.", "ok")
    return redirect(url_for("admin.referrals"))


# ── review requests ─────────────────────────────────────────────────────────
REVIEWS = Resource(
    key="reviews", table="review_requests", label="Review request",
    label_plural="Review requests", area="projects", row_label="contact_name",
    order_by="asked_on DESC, id DESC", searchable=("contact_name", "quote", "notes"),
    icon="star",
    intro="Ask once, at the moment they are happiest - the day the site goes live. "
          "Recording the ask is what stops you either forgetting or asking twice.",
    list_columns=[("contact_name", "Who"), ("platform", "Where"), ("status", "Status"),
                  ("asked_on", "Asked")],
    fields=[
        Field("client_id", "Client", "select", span=6, required=True,
              options=lambda: [(r["id"], r["name"]) for r in db.query(
                  "SELECT id, name FROM clients ORDER BY name")]),
        Field("project_id", "Project", "select", span=6,
              options=lambda: [("", "Not project-specific")] + [
                  (r["id"], f"{r['ref']} - {r['name']}") for r in db.query(
                      "SELECT id, ref, name FROM projects ORDER BY id DESC")]),
        Field("contact_name", "Who you asked", "text", span=6),
        Field("platform", "Where", "select", span=6, default="google",
              options=[("google", "Google Business Profile"), ("clutch", "Clutch"),
                       ("linkedin", "LinkedIn recommendation"), ("site", "Testimonial for the site"),
                       ("other", "Somewhere else")]),
        Field("status", "Status", "select", span=4, default="asked",
              options=[("asked", "Asked"), ("reminded", "Reminded"), ("done", "Left a review"),
                       ("declined", "Said no"), ("ignored", "No reply")]),
        Field("asked_on", "Asked on", "date", span=4),
        Field("done_on", "Left on", "date", span=4),
        Field("rating", "Rating out of 5", "number", span=4),
        Field("review_url", "Link to the review", "url", span=8),
        Field("quote", "The words worth quoting", "textarea", rows=4, span=12,
              help="Paste the useful sentence. You can lift it straight into Testimonials."),
        Field("notes", "Notes", "textarea", rows=2, span=12),
    ],
)

crud.register(bp, REVIEWS)


@bp.route("/reviews/<int:row_id>/testimonial", methods=["POST"])
@require_role("content")
def review_to_testimonial(row_id):
    """Turn a collected review into a testimonial on the public site."""
    verify_csrf()
    review = db.one("SELECT * FROM review_requests WHERE id = ?", (row_id,))
    if not review:
        abort(404)
    if not (review["quote"] or "").strip():
        flash("Paste the quote on the review first - there is nothing to publish yet.", "error")
        return redirect(url_for("admin.reviews_edit", row_id=row_id))
    if review["testimonial_id"]:
        flash("This one is already on the site.", "error")
        return redirect(url_for("admin.testimonials_edit", row_id=review["testimonial_id"]))

    client = db.one("SELECT * FROM clients WHERE id = ?", (review["client_id"],))
    testimonial_id = db.insert("testimonials", {
        "author": review["contact_name"] or (client["contact_name"] if client else ""),
        "company": client["name"] if client else "",
        "quote": review["quote"],
        "rating": review["rating"] or 5,
        "source": review["platform"],
        "source_url": review["review_url"] or "",
        "client_id": review["client_id"],
        "is_published": 0,
        "sort_order": db.next_sort_order("testimonials"),
    })
    db.update("review_requests", row_id, {"testimonial_id": testimonial_id})
    flash("Added as an unpublished testimonial. Check the wording, then publish it.", "ok")
    return redirect(url_for("admin.testimonials_edit", row_id=testimonial_id))
