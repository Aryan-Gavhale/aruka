-- ===========================================================================
-- Aruka schema. Every statement is idempotent, which keeps "migrations" to
-- appending new statements to this file. Applied on boot by core.db.init_schema.
--
-- Money is stored as REAL rupees. Amounts are rounded at the point of display
-- and at the point an invoice is issued, never accumulated blindly.
-- ===========================================================================

PRAGMA foreign_keys = ON;

-- ── ops ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT
);

CREATE TABLE IF NOT EXISTS settings (
  key        TEXT PRIMARY KEY,
  value      TEXT,
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  email         TEXT NOT NULL UNIQUE,
  name          TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  role          TEXT NOT NULL DEFAULT 'staff',
  phone         TEXT DEFAULT '',
  is_active     INTEGER NOT NULL DEFAULT 1,
  last_login_at TEXT,
  created_at    TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS login_attempts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ip         TEXT DEFAULT '',
  email      TEXT DEFAULT '',
  ok         INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_login_attempts_ip ON login_attempts(ip, created_at);
CREATE INDEX IF NOT EXISTS ix_login_attempts_email ON login_attempts(email, created_at);

CREATE TABLE IF NOT EXISTS audit_log (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id     INTEGER,
  user_email  TEXT DEFAULT '',
  action      TEXT NOT NULL,
  entity      TEXT NOT NULL,
  entity_id   TEXT DEFAULT '',
  label       TEXT DEFAULT '',
  before_json TEXT,
  after_json  TEXT,
  ip          TEXT DEFAULT '',
  created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_audit_entity ON audit_log(entity, entity_id);

CREATE TABLE IF NOT EXISTS notifications (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  kind       TEXT NOT NULL DEFAULT 'info',
  title      TEXT NOT NULL,
  body       TEXT DEFAULT '',
  url        TEXT DEFAULT '',
  entity     TEXT DEFAULT '',
  entity_id  TEXT DEFAULT '',
  is_read    INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_notifications_unread ON notifications(is_read, id DESC);

-- ── content ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS media (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  filename   TEXT,
  medium     TEXT,
  thumb      TEXT,
  url        TEXT,
  alt        TEXT DEFAULT '',
  title      TEXT DEFAULT '',
  width      INTEGER,
  height     INTEGER,
  bytes      INTEGER,
  mime       TEXT DEFAULT '',
  source     TEXT DEFAULT 'upload',
  credit     TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pages (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  nav_label        TEXT DEFAULT '',
  kicker           TEXT DEFAULT '',
  heading          TEXT DEFAULT '',
  intro            TEXT DEFAULT '',
  meta_title       TEXT DEFAULT '',
  meta_description TEXT DEFAULT '',
  seo_keyword      TEXT DEFAULT '',
  og_media_id      INTEGER REFERENCES media(id) ON DELETE SET NULL,
  is_published     INTEGER NOT NULL DEFAULT 1,
  is_system        INTEGER NOT NULL DEFAULT 0,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS page_blocks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  page_id      INTEGER NOT NULL REFERENCES pages(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL,
  name         TEXT DEFAULT '',
  data         TEXT DEFAULT '{}',
  is_published INTEGER NOT NULL DEFAULT 1,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  updated_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_blocks_page ON page_blocks(page_id, sort_order);

CREATE TABLE IF NOT EXISTS nav_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  location   TEXT NOT NULL DEFAULT 'header',
  label      TEXT NOT NULL,
  url        TEXT NOT NULL DEFAULT '/',
  is_button  INTEGER NOT NULL DEFAULT 0,
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS services (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  tagline          TEXT DEFAULT '',
  summary          TEXT DEFAULT '',
  body             TEXT DEFAULT '',
  icon             TEXT DEFAULT 'spark',
  media_id         INTEGER REFERENCES media(id) ON DELETE SET NULL,
  price_from       REAL,
  timeline         TEXT DEFAULT '',
  features         TEXT DEFAULT '',
  deliverables     TEXT DEFAULT '',
  ideal_for        TEXT DEFAULT '',
  meta_title       TEXT DEFAULT '',
  meta_description TEXT DEFAULT '',
  is_featured      INTEGER NOT NULL DEFAULT 0,
  is_published     INTEGER NOT NULL DEFAULT 1,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS case_studies (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  client_name      TEXT DEFAULT '',
  sector           TEXT DEFAULT '',
  service_line     TEXT DEFAULT '',
  summary          TEXT DEFAULT '',
  challenge        TEXT DEFAULT '',
  approach         TEXT DEFAULT '',
  outcome          TEXT DEFAULT '',
  metrics          TEXT DEFAULT '',
  stack            TEXT DEFAULT '',
  live_url         TEXT DEFAULT '',
  media_id         INTEGER REFERENCES media(id) ON DELETE SET NULL,
  logo_media_id    INTEGER REFERENCES media(id) ON DELETE SET NULL,
  delivered_on     TEXT,
  meta_title       TEXT DEFAULT '',
  meta_description TEXT DEFAULT '',
  is_featured      INTEGER NOT NULL DEFAULT 0,
  is_published     INTEGER NOT NULL DEFAULT 1,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS testimonials (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  author       TEXT NOT NULL,
  role         TEXT DEFAULT '',
  company      TEXT DEFAULT '',
  quote        TEXT NOT NULL,
  rating       INTEGER DEFAULT 5,
  media_id     INTEGER REFERENCES media(id) ON DELETE SET NULL,
  client_id    INTEGER,
  source       TEXT DEFAULT 'direct',
  source_url   TEXT DEFAULT '',
  is_published INTEGER NOT NULL DEFAULT 1,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS faqs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  question     TEXT NOT NULL,
  answer       TEXT NOT NULL,
  category     TEXT DEFAULT 'general',
  is_published INTEGER NOT NULL DEFAULT 1,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS posts (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT NOT NULL UNIQUE,
  title            TEXT NOT NULL,
  excerpt          TEXT DEFAULT '',
  body             TEXT DEFAULT '',
  media_id         INTEGER REFERENCES media(id) ON DELETE SET NULL,
  author           TEXT DEFAULT '',
  tags             TEXT DEFAULT '',
  seo_keyword      TEXT DEFAULT '',
  meta_title       TEXT DEFAULT '',
  meta_description TEXT DEFAULT '',
  published_at     TEXT,
  is_published     INTEGER NOT NULL DEFAULT 0,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS legal_pages (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slug         TEXT NOT NULL UNIQUE,
  title        TEXT NOT NULL,
  intro        TEXT DEFAULT '',
  body         TEXT DEFAULT '',
  is_published INTEGER NOT NULL DEFAULT 1,
  sort_order   INTEGER NOT NULL DEFAULT 0,
  updated_at   TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS stats (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  label      TEXT NOT NULL,
  value      REAL NOT NULL DEFAULT 0,
  prefix     TEXT DEFAULT '',
  suffix     TEXT DEFAULT '',
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS tech_items (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  label      TEXT NOT NULL,
  category   TEXT DEFAULT '',
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

-- ── pricing ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS packages (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  tagline          TEXT DEFAULT '',
  category         TEXT DEFAULT 'website',
  price            REAL NOT NULL DEFAULT 0,
  internal_cost    REAL NOT NULL DEFAULT 0,
  pages_included   INTEGER NOT NULL DEFAULT 5,
  delivery_days    INTEGER NOT NULL DEFAULT 14,
  support_months   INTEGER NOT NULL DEFAULT 1,
  recurring_yearly REAL NOT NULL DEFAULT 0,
  recurring_label  TEXT DEFAULT '',
  features         TEXT DEFAULT '',
  excluded         TEXT DEFAULT '',
  best_for         TEXT DEFAULT '',
  is_from_price    INTEGER NOT NULL DEFAULT 0,
  is_featured      INTEGER NOT NULL DEFAULT 0,
  is_active        INTEGER NOT NULL DEFAULT 1,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS addons (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  slug             TEXT NOT NULL UNIQUE,
  name             TEXT NOT NULL,
  category         TEXT DEFAULT 'build',
  help             TEXT DEFAULT '',
  unit             TEXT DEFAULT 'each',
  unit_price       REAL NOT NULL DEFAULT 0,
  internal_cost    REAL NOT NULL DEFAULT 0,
  min_qty          INTEGER NOT NULL DEFAULT 1,
  max_qty          INTEGER NOT NULL DEFAULT 50,
  default_qty      INTEGER NOT NULL DEFAULT 1,
  is_recurring     INTEGER NOT NULL DEFAULT 0,
  recurring_period TEXT DEFAULT 'yearly',
  is_quantity      INTEGER NOT NULL DEFAULT 0,
  package_scope    TEXT DEFAULT '',
  is_active        INTEGER NOT NULL DEFAULT 1,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  updated_at       TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pricing_rules (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  code       TEXT NOT NULL UNIQUE,
  label      TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'surcharge_pct',
  value      REAL NOT NULL DEFAULT 0,
  applies_to TEXT DEFAULT 'total',
  help       TEXT DEFAULT '',
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  updated_at TEXT DEFAULT (datetime('now'))
);

-- ── crm ────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS lead_sources (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slug         TEXT NOT NULL UNIQUE,
  name         TEXT NOT NULL,
  cost_monthly REAL NOT NULL DEFAULT 0,
  is_paid      INTEGER NOT NULL DEFAULT 0,
  notes        TEXT DEFAULT '',
  is_active    INTEGER NOT NULL DEFAULT 1,
  sort_order   INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS leads (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ref               TEXT NOT NULL UNIQUE,
  name              TEXT NOT NULL,
  company           TEXT DEFAULT '',
  email             TEXT DEFAULT '',
  phone             TEXT DEFAULT '',
  whatsapp          TEXT DEFAULT '',
  city              TEXT DEFAULT '',
  stage             TEXT NOT NULL DEFAULT 'new',
  source_id         INTEGER REFERENCES lead_sources(id) ON DELETE SET NULL,
  source_note       TEXT DEFAULT '',
  service_interest  TEXT DEFAULT '',
  budget_band       TEXT DEFAULT '',
  message           TEXT DEFAULT '',
  quote_value       REAL NOT NULL DEFAULT 0,
  score             INTEGER NOT NULL DEFAULT 0,
  owner_user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  next_followup_on  TEXT,
  followup_note     TEXT DEFAULT '',
  lost_reason       TEXT DEFAULT '',
  tags              TEXT DEFAULT '',
  utm_source        TEXT DEFAULT '',
  utm_medium        TEXT DEFAULT '',
  utm_campaign      TEXT DEFAULT '',
  utm_term          TEXT DEFAULT '',
  utm_content       TEXT DEFAULT '',
  referrer          TEXT DEFAULT '',
  landing_page      TEXT DEFAULT '',
  ip                TEXT DEFAULT '',
  is_spam           INTEGER NOT NULL DEFAULT 0,
  opt_out           INTEGER NOT NULL DEFAULT 0,
  referral_code     TEXT DEFAULT '',
  referred_by_client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  client_id         INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  converted_at      TEXT,
  closed_at         TEXT,
  last_contact_at   TEXT,
  sort_order        INTEGER NOT NULL DEFAULT 0,
  created_at        TEXT DEFAULT (datetime('now')),
  updated_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_leads_stage ON leads(stage, id DESC);
CREATE INDEX IF NOT EXISTS ix_leads_followup ON leads(next_followup_on);

CREATE TABLE IF NOT EXISTS lead_events (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  lead_id    INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
  kind       TEXT NOT NULL DEFAULT 'note',
  body       TEXT DEFAULT '',
  meta       TEXT DEFAULT '{}',
  user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  user_email TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_lead_events_lead ON lead_events(lead_id, id DESC);

-- ── clients and delivery ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS clients (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  ref                 TEXT NOT NULL UNIQUE,
  name                TEXT NOT NULL,
  legal_name          TEXT DEFAULT '',
  gstin               TEXT DEFAULT '',
  pan                 TEXT DEFAULT '',
  contact_name        TEXT DEFAULT '',
  email               TEXT DEFAULT '',
  phone               TEXT DEFAULT '',
  whatsapp            TEXT DEFAULT '',
  billing_address     TEXT DEFAULT '',
  city                TEXT DEFAULT '',
  state               TEXT DEFAULT '',
  state_code          TEXT DEFAULT '',
  country             TEXT DEFAULT 'India',
  pincode             TEXT DEFAULT '',
  website             TEXT DEFAULT '',
  sector              TEXT DEFAULT '',
  logo_media_id       INTEGER REFERENCES media(id) ON DELETE SET NULL,
  notes               TEXT DEFAULT '',
  referral_code       TEXT DEFAULT '',
  referred_by_client_id INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  opt_out             INTEGER NOT NULL DEFAULT 0,
  is_active           INTEGER NOT NULL DEFAULT 1,
  created_at          TEXT DEFAULT (datetime('now')),
  updated_at          TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS contacts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  name       TEXT NOT NULL,
  role       TEXT DEFAULT '',
  email      TEXT DEFAULT '',
  phone      TEXT DEFAULT '',
  whatsapp   TEXT DEFAULT '',
  is_primary INTEGER NOT NULL DEFAULT 0,
  portal_access INTEGER NOT NULL DEFAULT 1,
  notes      TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_contacts_client ON contacts(client_id);

CREATE TABLE IF NOT EXISTS projects (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  ref              TEXT NOT NULL UNIQUE,
  client_id        INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  name             TEXT NOT NULL,
  service_id       INTEGER REFERENCES services(id) ON DELETE SET NULL,
  package_id       INTEGER REFERENCES packages(id) ON DELETE SET NULL,
  quote_id         INTEGER,
  status           TEXT NOT NULL DEFAULT 'planned',
  health           TEXT NOT NULL DEFAULT 'green',
  billing_type     TEXT NOT NULL DEFAULT 'milestone',
  value            REAL NOT NULL DEFAULT 0,
  internal_cost    REAL NOT NULL DEFAULT 0,
  retainer_amount  REAL NOT NULL DEFAULT 0,
  recurring_yearly REAL NOT NULL DEFAULT 0,
  progress_pct     INTEGER NOT NULL DEFAULT 0,
  start_on         TEXT,
  target_on        TEXT,
  launched_on      TEXT,
  closed_on        TEXT,
  notes            TEXT DEFAULT '',
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_projects_client ON projects(client_id);

CREATE TABLE IF NOT EXISTS milestones (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id  INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label       TEXT NOT NULL,
  description TEXT DEFAULT '',
  invoice_pct REAL NOT NULL DEFAULT 0,
  amount      REAL NOT NULL DEFAULT 0,
  due_on      TEXT,
  done_on     TEXT,
  status      TEXT NOT NULL DEFAULT 'pending',
  invoice_id  INTEGER,
  sort_order  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_milestones_project ON milestones(project_id, sort_order);

CREATE TABLE IF NOT EXISTS tasks (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id       INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  milestone_id     INTEGER REFERENCES milestones(id) ON DELETE SET NULL,
  title            TEXT NOT NULL,
  notes            TEXT DEFAULT '',
  assignee_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  status           TEXT NOT NULL DEFAULT 'todo',
  priority         TEXT NOT NULL DEFAULT 'normal',
  estimate_hours   REAL NOT NULL DEFAULT 0,
  actual_hours     REAL NOT NULL DEFAULT 0,
  due_on           TEXT,
  done_at          TEXT,
  sort_order       INTEGER NOT NULL DEFAULT 0,
  created_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_tasks_project ON tasks(project_id, status);

CREATE TABLE IF NOT EXISTS launch_checklist (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  label      TEXT NOT NULL,
  note       TEXT DEFAULT '',
  is_done    INTEGER NOT NULL DEFAULT 0,
  done_at    TEXT,
  sort_order INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_launch_project ON launch_checklist(project_id, sort_order);

CREATE TABLE IF NOT EXISTS assets (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  kind        TEXT NOT NULL DEFAULT 'domain',
  label       TEXT NOT NULL,
  provider    TEXT DEFAULT '',
  identifier  TEXT DEFAULT '',
  url         TEXT DEFAULT '',
  starts_on   TEXT,
  expires_on  TEXT,
  renew_cost  REAL NOT NULL DEFAULT 0,
  auto_renew  INTEGER NOT NULL DEFAULT 0,
  owned_by    TEXT DEFAULT 'client',
  notes       TEXT DEFAULT '',
  is_active   INTEGER NOT NULL DEFAULT 1,
  created_at  TEXT DEFAULT (datetime('now')),
  updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_assets_expiry ON assets(expires_on);

CREATE TABLE IF NOT EXISTS credentials (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id         INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  project_id        INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  label             TEXT NOT NULL,
  location          TEXT DEFAULT '',
  url               TEXT DEFAULT '',
  username          TEXT DEFAULT '',
  secret_ciphertext TEXT DEFAULT '',
  notes             TEXT DEFAULT '',
  created_at        TEXT DEFAULT (datetime('now')),
  updated_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_credentials_client ON credentials(client_id);

-- ── quotes and documents ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS quotes (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  ref              TEXT NOT NULL UNIQUE,
  lead_id          INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  client_id        INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  project_id       INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  package_id       INTEGER REFERENCES packages(id) ON DELETE SET NULL,
  title            TEXT DEFAULT '',
  status           TEXT NOT NULL DEFAULT 'draft',
  source           TEXT DEFAULT 'admin',
  pages            INTEGER NOT NULL DEFAULT 0,
  rush             INTEGER NOT NULL DEFAULT 0,
  complexity       REAL NOT NULL DEFAULT 1.0,
  annual_prepay    INTEGER NOT NULL DEFAULT 0,
  referral         INTEGER NOT NULL DEFAULT 0,
  subtotal         REAL NOT NULL DEFAULT 0,
  surcharge_amount REAL NOT NULL DEFAULT 0,
  discount_amount  REAL NOT NULL DEFAULT 0,
  taxable_value    REAL NOT NULL DEFAULT 0,
  tax_amount       REAL NOT NULL DEFAULT 0,
  total            REAL NOT NULL DEFAULT 0,
  recurring_yearly REAL NOT NULL DEFAULT 0,
  internal_cost    REAL NOT NULL DEFAULT 0,
  currency         TEXT NOT NULL DEFAULT 'INR',
  valid_until      TEXT,
  notes            TEXT DEFAULT '',
  config_json      TEXT DEFAULT '{}',
  accepted_at      TEXT,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_quotes_lead ON quotes(lead_id);

CREATE TABLE IF NOT EXISTS quote_lines (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  quote_id         INTEGER NOT NULL REFERENCES quotes(id) ON DELETE CASCADE,
  kind             TEXT NOT NULL DEFAULT 'addon',
  label            TEXT NOT NULL,
  description      TEXT DEFAULT '',
  qty              REAL NOT NULL DEFAULT 1,
  unit             TEXT DEFAULT 'each',
  unit_price       REAL NOT NULL DEFAULT 0,
  amount           REAL NOT NULL DEFAULT 0,
  internal_cost    REAL NOT NULL DEFAULT 0,
  is_recurring     INTEGER NOT NULL DEFAULT 0,
  recurring_period TEXT DEFAULT 'yearly',
  addon_id         INTEGER REFERENCES addons(id) ON DELETE SET NULL,
  is_override      INTEGER NOT NULL DEFAULT 0,
  sort_order       INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_quote_lines_quote ON quote_lines(quote_id, sort_order);

CREATE TABLE IF NOT EXISTS clause_library (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  code           TEXT NOT NULL,
  title          TEXT NOT NULL,
  body           TEXT NOT NULL,
  category       TEXT DEFAULT 'commercial',
  applies_to     TEXT DEFAULT 'proposal,sow,amc',
  version        INTEGER NOT NULL DEFAULT 1,
  effective_from TEXT DEFAULT (date('now')),
  is_required    INTEGER NOT NULL DEFAULT 0,
  is_active      INTEGER NOT NULL DEFAULT 1,
  sort_order     INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT DEFAULT (datetime('now')),
  updated_at     TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_clause_code_version ON clause_library(code, version);

CREATE TABLE IF NOT EXISTS documents (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  ref          TEXT NOT NULL UNIQUE,
  kind         TEXT NOT NULL DEFAULT 'proposal',
  title        TEXT NOT NULL DEFAULT '',
  status       TEXT NOT NULL DEFAULT 'draft',
  version      INTEGER NOT NULL DEFAULT 1,
  lead_id      INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  client_id    INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  project_id   INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  quote_id     INTEGER REFERENCES quotes(id) ON DELETE SET NULL,
  invoice_id   INTEGER,
  payment_id   INTEGER,
  body_json    TEXT DEFAULT '{}',
  pdf_filename TEXT DEFAULT '',
  issued_on    TEXT,
  valid_until  TEXT,
  sent_at      TEXT,
  accepted_at  TEXT,
  accepted_by  TEXT DEFAULT '',
  accepted_ip  TEXT DEFAULT '',
  declined_at  TEXT,
  decline_note TEXT DEFAULT '',
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_documents_kind ON documents(kind, id DESC);

CREATE TABLE IF NOT EXISTS document_shares (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id    INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  token          TEXT NOT NULL UNIQUE,
  expires_on     TEXT,
  views          INTEGER NOT NULL DEFAULT 0,
  last_viewed_at TEXT,
  revoked_at     TEXT,
  created_at     TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS document_views (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  share_id    INTEGER REFERENCES document_shares(id) ON DELETE SET NULL,
  ip          TEXT DEFAULT '',
  user_agent  TEXT DEFAULT '',
  created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_doc_views_doc ON document_views(document_id, id DESC);

-- ── money ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS number_series (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  series      TEXT NOT NULL,
  fy          TEXT NOT NULL,
  prefix      TEXT DEFAULT '',
  last_number INTEGER NOT NULL DEFAULT 0,
  updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_number_series ON number_series(series, fy);

CREATE TABLE IF NOT EXISTS invoices (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  ref             TEXT NOT NULL UNIQUE,
  kind            TEXT NOT NULL DEFAULT 'invoice',
  doc_mode        TEXT NOT NULL DEFAULT 'bill_of_supply',
  client_id       INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  project_id      INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  quote_id        INTEGER REFERENCES quotes(id) ON DELETE SET NULL,
  milestone_id    INTEGER REFERENCES milestones(id) ON DELETE SET NULL,
  recurring_id    INTEGER,
  ticket_id       INTEGER,
  status          TEXT NOT NULL DEFAULT 'draft',
  place_of_supply TEXT DEFAULT '',
  supply_type     TEXT DEFAULT 'intra',
  issued_on       TEXT,
  due_on          TEXT,
  subtotal        REAL NOT NULL DEFAULT 0,
  discount_amount REAL NOT NULL DEFAULT 0,
  taxable_value   REAL NOT NULL DEFAULT 0,
  cgst            REAL NOT NULL DEFAULT 0,
  sgst            REAL NOT NULL DEFAULT 0,
  igst            REAL NOT NULL DEFAULT 0,
  tax_amount      REAL NOT NULL DEFAULT 0,
  round_off       REAL NOT NULL DEFAULT 0,
  total           REAL NOT NULL DEFAULT 0,
  amount_paid     REAL NOT NULL DEFAULT 0,
  balance         REAL NOT NULL DEFAULT 0,
  tds_amount      REAL NOT NULL DEFAULT 0,
  written_off     REAL NOT NULL DEFAULT 0,
  currency        TEXT NOT NULL DEFAULT 'INR',
  notes           TEXT DEFAULT '',
  terms           TEXT DEFAULT '',
  sent_at         TEXT,
  closed_at       TEXT,
  cancelled_at    TEXT,
  cancel_reason   TEXT DEFAULT '',
  dunning_stage   INTEGER NOT NULL DEFAULT 0,
  last_reminder_at TEXT,
  created_at      TEXT DEFAULT (datetime('now')),
  updated_at      TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_invoices_client ON invoices(client_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_invoices_status ON invoices(status, due_on);

CREATE TABLE IF NOT EXISTS invoice_lines (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  invoice_id   INTEGER NOT NULL REFERENCES invoices(id) ON DELETE CASCADE,
  label        TEXT NOT NULL,
  description  TEXT DEFAULT '',
  hsn_sac      TEXT DEFAULT '',
  qty          REAL NOT NULL DEFAULT 1,
  unit         TEXT DEFAULT 'each',
  unit_price   REAL NOT NULL DEFAULT 0,
  discount_pct REAL NOT NULL DEFAULT 0,
  amount       REAL NOT NULL DEFAULT 0,
  tax_rate     REAL NOT NULL DEFAULT 0,
  sort_order   INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_invoice_lines_invoice ON invoice_lines(invoice_id, sort_order);

CREATE TABLE IF NOT EXISTS payments (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ref         TEXT NOT NULL UNIQUE,
  invoice_id  INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
  client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  amount      REAL NOT NULL DEFAULT 0,
  tds_amount  REAL NOT NULL DEFAULT 0,
  method      TEXT NOT NULL DEFAULT 'UPI',
  reference   TEXT DEFAULT '',
  paid_on     TEXT NOT NULL DEFAULT (date('now')),
  is_advance  INTEGER NOT NULL DEFAULT 0,
  notes       TEXT DEFAULT '',
  voided_at   TEXT,
  void_reason TEXT DEFAULT '',
  created_by  TEXT DEFAULT '',
  created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_payments_invoice ON payments(invoice_id);
CREATE INDEX IF NOT EXISTS ix_payments_paid_on ON payments(paid_on);

CREATE TABLE IF NOT EXISTS credit_notes (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ref        TEXT NOT NULL UNIQUE,
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
  client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  amount     REAL NOT NULL DEFAULT 0,
  reason     TEXT DEFAULT '',
  issued_on  TEXT NOT NULL DEFAULT (date('now')),
  notes      TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS expense_categories (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  slug       TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL,
  kind       TEXT NOT NULL DEFAULT 'operating',
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS expenses (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  ref              TEXT NOT NULL UNIQUE,
  category_id      INTEGER REFERENCES expense_categories(id) ON DELETE SET NULL,
  vendor           TEXT DEFAULT '',
  description      TEXT DEFAULT '',
  amount           REAL NOT NULL DEFAULT 0,
  tax_amount       REAL NOT NULL DEFAULT 0,
  paid_on          TEXT NOT NULL DEFAULT (date('now')),
  method           TEXT DEFAULT 'UPI',
  reference        TEXT DEFAULT '',
  project_id       INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  client_id        INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  is_recurring     INTEGER NOT NULL DEFAULT 0,
  recurring_period TEXT DEFAULT 'monthly',
  next_due_on      TEXT,
  receipt_media_id INTEGER REFERENCES media(id) ON DELETE SET NULL,
  is_billable      INTEGER NOT NULL DEFAULT 0,
  notes            TEXT DEFAULT '',
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_expenses_paid_on ON expenses(paid_on);
CREATE INDEX IF NOT EXISTS ix_expenses_project ON expenses(project_id);

CREATE TABLE IF NOT EXISTS recurring_items (
  id               INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id        INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  project_id       INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  asset_id         INTEGER REFERENCES assets(id) ON DELETE SET NULL,
  kind             TEXT NOT NULL DEFAULT 'hosting',
  label            TEXT NOT NULL,
  amount           REAL NOT NULL DEFAULT 0,
  internal_cost    REAL NOT NULL DEFAULT 0,
  period           TEXT NOT NULL DEFAULT 'yearly',
  next_due_on      TEXT,
  last_invoiced_on TEXT,
  starts_on        TEXT,
  ends_on          TEXT,
  auto_invoice     INTEGER NOT NULL DEFAULT 0,
  reminder_sent_at TEXT,
  notes            TEXT DEFAULT '',
  is_active        INTEGER NOT NULL DEFAULT 1,
  created_at       TEXT DEFAULT (datetime('now')),
  updated_at       TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_recurring_due ON recurring_items(next_due_on, is_active);

CREATE TABLE IF NOT EXISTS referral_payouts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  lead_id    INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  invoice_id INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
  amount     REAL NOT NULL DEFAULT 0,
  status     TEXT NOT NULL DEFAULT 'due',
  paid_on    TEXT,
  method     TEXT DEFAULT '',
  reference  TEXT DEFAULT '',
  notes      TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);

-- ── support ────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sla_policies (
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  priority        TEXT NOT NULL UNIQUE,
  label           TEXT NOT NULL,
  description     TEXT DEFAULT '',
  response_hours  REAL NOT NULL DEFAULT 24,
  resolve_hours   REAL NOT NULL DEFAULT 120,
  is_active       INTEGER NOT NULL DEFAULT 1,
  sort_order      INTEGER NOT NULL DEFAULT 0,
  updated_at      TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tickets (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  ref               TEXT NOT NULL UNIQUE,
  client_id         INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  project_id        INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  contact_name      TEXT DEFAULT '',
  contact_email     TEXT DEFAULT '',
  contact_phone     TEXT DEFAULT '',
  subject           TEXT NOT NULL,
  body              TEXT DEFAULT '',
  category          TEXT NOT NULL DEFAULT 'bug',
  priority          TEXT NOT NULL DEFAULT 'p3',
  status            TEXT NOT NULL DEFAULT 'open',
  source            TEXT NOT NULL DEFAULT 'web',
  assignee_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
  response_due_at   TEXT,
  resolve_due_at    TEXT,
  first_response_at TEXT,
  resolved_at       TEXT,
  closed_at         TEXT,
  reopened_count    INTEGER NOT NULL DEFAULT 0,
  is_billable       INTEGER NOT NULL DEFAULT 0,
  rate_per_hour     REAL NOT NULL DEFAULT 0,
  quote_id          INTEGER REFERENCES quotes(id) ON DELETE SET NULL,
  invoice_id        INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
  is_change_request INTEGER NOT NULL DEFAULT 0,
  satisfaction      INTEGER,
  ip                TEXT DEFAULT '',
  created_at        TEXT DEFAULT (datetime('now')),
  updated_at        TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status, priority);
CREATE INDEX IF NOT EXISTS ix_tickets_client ON tickets(client_id, id DESC);

CREATE TABLE IF NOT EXISTS ticket_messages (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id   INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  author_kind TEXT NOT NULL DEFAULT 'agent',
  author_name TEXT DEFAULT '',
  body        TEXT NOT NULL DEFAULT '',
  is_internal INTEGER NOT NULL DEFAULT 0,
  media_id    INTEGER REFERENCES media(id) ON DELETE SET NULL,
  user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_ticket_messages_ticket ON ticket_messages(ticket_id, id);

CREATE TABLE IF NOT EXISTS ticket_time_logs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id  INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  user_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
  minutes    INTEGER NOT NULL DEFAULT 0,
  note       TEXT DEFAULT '',
  logged_on  TEXT NOT NULL DEFAULT (date('now')),
  is_billable INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_time_logs_ticket ON ticket_time_logs(ticket_id);

-- ── comms ──────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS message_templates (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  code       TEXT NOT NULL UNIQUE,
  name       TEXT NOT NULL,
  channel    TEXT NOT NULL DEFAULT 'whatsapp',
  category   TEXT NOT NULL DEFAULT 'followup',
  subject    TEXT DEFAULT '',
  body       TEXT NOT NULL,
  cloud_template_name TEXT DEFAULT '',
  help       TEXT DEFAULT '',
  is_active  INTEGER NOT NULL DEFAULT 1,
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS messages (
  id                  INTEGER PRIMARY KEY AUTOINCREMENT,
  channel             TEXT NOT NULL DEFAULT 'whatsapp',
  direction           TEXT NOT NULL DEFAULT 'out',
  template_id         INTEGER REFERENCES message_templates(id) ON DELETE SET NULL,
  to_name             TEXT DEFAULT '',
  to_number           TEXT DEFAULT '',
  to_email            TEXT DEFAULT '',
  subject             TEXT DEFAULT '',
  body                TEXT DEFAULT '',
  status              TEXT NOT NULL DEFAULT 'queued',
  provider            TEXT DEFAULT '',
  provider_message_id TEXT DEFAULT '',
  error               TEXT DEFAULT '',
  lead_id             INTEGER REFERENCES leads(id) ON DELETE SET NULL,
  client_id           INTEGER REFERENCES clients(id) ON DELETE SET NULL,
  ticket_id           INTEGER REFERENCES tickets(id) ON DELETE SET NULL,
  invoice_id          INTEGER REFERENCES invoices(id) ON DELETE SET NULL,
  document_id         INTEGER REFERENCES documents(id) ON DELETE SET NULL,
  recurring_id        INTEGER REFERENCES recurring_items(id) ON DELETE SET NULL,
  user_id             INTEGER REFERENCES users(id) ON DELETE SET NULL,
  batch_id            TEXT DEFAULT '',
  queued_at           TEXT,
  sent_at             TEXT,
  delivered_at        TEXT,
  read_at             TEXT,
  failed_at           TEXT,
  created_at          TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_messages_lead ON messages(lead_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_messages_client ON messages(client_id, id DESC);
CREATE INDEX IF NOT EXISTS ix_messages_status ON messages(status, channel);

CREATE TABLE IF NOT EXISTS email_log (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  message_id INTEGER REFERENCES messages(id) ON DELETE SET NULL,
  to_email   TEXT NOT NULL DEFAULT '',
  subject    TEXT DEFAULT '',
  ok         INTEGER NOT NULL DEFAULT 0,
  detail     TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);

-- ── client portal ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS client_logins (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id  INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  contact_id INTEGER REFERENCES contacts(id) ON DELETE SET NULL,
  email      TEXT NOT NULL,
  code_hash  TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  used_at    TEXT,
  ip         TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_client_logins_email ON client_logins(email, id DESC);

CREATE TABLE IF NOT EXISTS portal_attempts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  ip         TEXT DEFAULT '',
  email      TEXT DEFAULT '',
  ok         INTEGER NOT NULL DEFAULT 0,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_portal_attempts_ip ON portal_attempts(ip, created_at);

-- ── opt-outs, reviews and our own costs ────────────────────────────────────
-- An opt-out is deliberately not a flag on the contact: someone who has never
-- been a client can still tell you to stop, and that has to be honoured without
-- inventing a client record for them.
CREATE TABLE IF NOT EXISTS optouts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  name       TEXT DEFAULT '',
  number     TEXT DEFAULT '',
  email      TEXT DEFAULT '',
  channel    TEXT NOT NULL DEFAULT 'whatsapp',
  reason     TEXT DEFAULT '',
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_optouts_number ON optouts(number);
CREATE INDEX IF NOT EXISTS ix_optouts_email ON optouts(email);

CREATE TABLE IF NOT EXISTS review_requests (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  client_id   INTEGER NOT NULL REFERENCES clients(id) ON DELETE CASCADE,
  project_id  INTEGER REFERENCES projects(id) ON DELETE SET NULL,
  contact_name TEXT DEFAULT '',
  platform    TEXT NOT NULL DEFAULT 'google',
  status      TEXT NOT NULL DEFAULT 'asked',
  asked_on    TEXT NOT NULL DEFAULT (date('now')),
  done_on     TEXT,
  rating      INTEGER,
  quote       TEXT DEFAULT '',
  review_url  TEXT DEFAULT '',
  testimonial_id INTEGER REFERENCES testimonials(id) ON DELETE SET NULL,
  notes       TEXT DEFAULT '',
  created_at  TEXT DEFAULT (datetime('now')),
  updated_at  TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_review_requests_client ON review_requests(client_id, id DESC);

-- Your own tool bill. Separate from expenses because a subscription is a
-- standing commitment you want to see totalled per month, not a payment that
-- happened once; the expense rows it produces still live in expenses.
CREATE TABLE IF NOT EXISTS subscriptions (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  name         TEXT NOT NULL,
  vendor       TEXT DEFAULT '',
  purpose      TEXT DEFAULT '',
  category_id  INTEGER REFERENCES expense_categories(id) ON DELETE SET NULL,
  amount       REAL NOT NULL DEFAULT 0,
  currency     TEXT NOT NULL DEFAULT 'INR',
  period       TEXT NOT NULL DEFAULT 'monthly',
  renews_on    TEXT,
  started_on   TEXT,
  cancelled_on TEXT,
  seats        INTEGER NOT NULL DEFAULT 1,
  is_essential INTEGER NOT NULL DEFAULT 1,
  is_active    INTEGER NOT NULL DEFAULT 1,
  notes        TEXT DEFAULT '',
  created_at   TEXT DEFAULT (datetime('now')),
  updated_at   TEXT DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS ix_subscriptions_renews ON subscriptions(renews_on, is_active);
