# Deploy Aruka on PythonAnywhere (free tier)

Aruka is one Flask app — public site, admin panel and client portal together. There is
no separate frontend build and no external database service. SQLite lives in `db/aruka.db`
on disk, which is why PythonAnywhere works and Vercel does not.

**Time:** about 20 minutes the first time.

**You will get:** `https://YOURUSERNAME.pythonanywhere.com`

---

## Before you start

1. Create a free account at [pythonanywhere.com](https://www.pythonanywhere.com).
2. Note your **username** — every path below uses it.
3. On the free (Beginner) plan you get:
   - A persistent disk (database and uploads survive restarts)
   - One web app at `username.pythonanywhere.com`
   - **No custom domain** (upgrade to Hacker ~$5/mo when you need one)
   - Limited outbound HTTP (WhatsApp Cloud API may need a paid plan or whitelisting)

---

## Step 1 — Clone the repo

Open a **Bash console** on PythonAnywhere (Consoles → Bash).

```bash
cd ~
git clone https://github.com/Aryan-Gavhale/aruka.git
cd aruka
```

If the repo is private, use a personal access token or upload a zip instead.

---

## Step 2 — Run the setup script

Still in the Bash console:

```bash
bash deploy/setup_pythonanywhere.sh
```

This creates a virtualenv, installs dependencies and copies `config.json` if you do not
have one yet.

---

## Step 3 — Edit `config.json`

```bash
nano ~/aruka/config.json
```

Change at least these fields (replace `YOURUSERNAME`):

| Field | Example |
| --- | --- |
| `secret_key` | A long random string (32+ characters) |
| `owner_email` | Your real email |
| `owner_password` | A strong password you will use at `/admin` |
| `public_base_url` | `https://YOURUSERNAME.pythonanywhere.com` |
| `https_only` | `true` (already set in the example) |
| `trusted_proxies` | `1` (already set — PythonAnywhere sits behind a proxy) |

Save: `Ctrl+O`, Enter, `Ctrl+X`.

---

## Step 4 — Seed the database

```bash
cd ~/aruka
source .venv/bin/activate
python app.py seed
```

This creates `db/aruka.db` with the demo rate card and public site content. Safe to run
again later — it only adds missing rows.

---

## Step 5 — Create the web app

1. Go to the **Web** tab.
2. Click **Add a new web app**.
3. Choose **Manual configuration** (not Flask wizard).
4. Pick **Python 3.12** (or 3.11 if 3.12 is not listed).

Then fill in:

| Setting | Value |
| --- | --- |
| **Source code** | `/home/YOURUSERNAME/aruka` |
| **Working directory** | `/home/YOURUSERNAME/aruka` |
| **Virtualenv** | `/home/YOURUSERNAME/aruka/.venv` |

### WSGI configuration file

Click the WSGI file link and **replace the entire contents** with
`deploy/pythonanywhere_wsgi.py` from the repo, after changing `YOURUSERNAME`:

```python
import sys

path = "/home/YOURUSERNAME/aruka"
if path not in sys.path:
    sys.path.insert(0, path)

from wsgi import application
```

Save.

### Static files (recommended)

Scroll to **Static files** and add:

| URL | Directory |
| --- | --- |
| `/static/` | `/home/YOURUSERNAME/aruka/static/` |

This lets PythonAnywhere serve CSS and JS directly instead of going through Flask.

---

## Step 6 — Reload and sign in

1. Click the green **Reload** button on the Web tab.
2. Open `https://YOURUSERNAME.pythonanywhere.com` — you should see the public site.
3. Sign in at `https://YOURUSERNAME.pythonanywhere.com/admin` with the email and password
   from `config.json`.
4. Run the **setup wizard** in the admin banner to replace demo branding with yours.

---

## Step 7 — Turn off search indexing until you are ready

In the admin panel: **SEO → Allow indexing** — leave this off while you are still setting
up. Turn it on when the site is ready to go public.

---

## Updating after a code change

On your machine, push to GitHub. On PythonAnywhere:

```bash
cd ~/aruka
git pull
source .venv/bin/activate
pip install -r requirements.txt    # only if requirements changed
```

Then **Reload** on the Web tab.

Your database, uploads and keys are not touched by `git pull`.

---

## Backups (do this weekly)

Download these from the **Files** tab or copy them with `scp`:

| File / folder | Why |
| --- | --- |
| `db/aruka.db` | Everything — clients, invoices, content |
| `db/vault.key` | Without this, stored credentials cannot be read |
| `db/secret.key` | Session signing — everyone gets logged out if lost |
| `static/uploads/` | Uploaded images and files |

Quick backup in Bash:

```bash
cd ~/aruka
tar czf ~/aruka-backup-$(date +%Y%m%d).tar.gz db/aruka.db db/vault.key db/secret.key static/uploads
```

---

## Daily digest (optional)

`python app.py digest` prints follow-ups, overdue invoices and SLA warnings. On the free
plan there is no scheduled task runner — run it manually in a Bash console when you want a
check-in, or upgrade to a paid plan for a daily scheduled task.

---

## Troubleshooting

### Something went wrong / 500 error

Open **Web → Log files → Error log**. The last traceback usually points at the problem.

Common fixes:

| Symptom | Fix |
| --- | --- |
| `No module named 'flask'` | Virtualenv path wrong on Web tab — set to `/home/YOURUSERNAME/aruka/.venv` |
| `ImportError: cannot import name 'application'` | WSGI file path wrong — check `YOURUSERNAME` in `sys.path` |
| Admin login loops | Set `https_only: true` and `trusted_proxies: 1` in `config.json`, then reload |
| Uploads fail | `mkdir -p ~/aruka/static/uploads` and reload |
| Database empty | Run `python app.py seed` from the virtualenv |

### Static files 404

Add the `/static/` mapping on the Web tab (Step 5) and reload.

### Proposal links point at the wrong host

Set `public_base_url` in `config.json` to your full `https://YOURUSERNAME.pythonanywhere.com`
URL and reload.

---

## When you outgrow the free tier

| Need | Upgrade to |
| --- | --- |
| Custom domain (`aruka.studio`) | PythonAnywhere Hacker ($5/mo) or move to a VPS |
| Scheduled digest email | Hacker plan scheduled tasks, or external cron hitting a protected endpoint |
| WhatsApp Cloud API outbound | Hacker plan, or whitelist the API host with support |
| More traffic / CPU | Hacker plan or Railway / Hetzner VPS |

---

## Quick reference

```bash
cd ~/aruka && source .venv/bin/activate

python app.py seed          # create / refresh schema and demo content
python app.py digest        # print today's follow-up digest
python app.py user EMAIL "Name" PASSWORD owner   # add another admin
```

Live URLs:

- Public site: `/`
- Admin: `/admin`
- Client portal: `/portal`
