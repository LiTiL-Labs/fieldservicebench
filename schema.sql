-- FieldServiceBench-10 world schema (clean-room, stdlib SQLite).
-- Fixed simulation clock lives in config('now'). All ids are TEXT for
-- stable, human-readable allow-lists and containment diffs.

CREATE TABLE config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE counters (
    name TEXT PRIMARY KEY,
    n    INTEGER NOT NULL
);

CREATE TABLE customers (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    tier           TEXT NOT NULL,
    region         TEXT NOT NULL,
    account_status TEXT NOT NULL DEFAULT 'active'
);

CREATE TABLE sites (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    name        TEXT NOT NULL,
    address     TEXT NOT NULL
);

CREATE TABLE assets (
    id               TEXT PRIMARY KEY,
    site_id          TEXT NOT NULL REFERENCES sites(id),
    unit_tag         TEXT NOT NULL,
    model            TEXT NOT NULL,
    serial           TEXT NOT NULL,
    install_revision INTEGER NOT NULL,
    install_date     TEXT NOT NULL,
    warranty_until   TEXT NOT NULL
);

CREATE TABLE technicians (
    id             TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    region         TEXT NOT NULL,
    skills         TEXT NOT NULL,  -- comma-separated job kinds
    cert_type      TEXT NOT NULL,
    cert_expires   TEXT NOT NULL,  -- ISO date; expired if < config('now')
    std_rate_cents INTEGER NOT NULL,
    ot_rate_cents  INTEGER NOT NULL
);

CREATE TABLE work_orders (
    id          TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL REFERENCES customers(id),
    site_id     TEXT NOT NULL REFERENCES sites(id),
    asset_id    TEXT NOT NULL REFERENCES assets(id),
    kind        TEXT NOT NULL,     -- repair | maintenance | install
    status      TEXT NOT NULL,     -- open|triaged|scheduled|in_progress|completed|cancelled|closed
    priority    TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at  TEXT NOT NULL
);

CREATE TABLE parts_inventory (
    part_no         TEXT PRIMARY KEY,
    description     TEXT NOT NULL,
    on_hand         INTEGER NOT NULL,
    reserved        INTEGER NOT NULL,
    quarantined     INTEGER NOT NULL,
    unit_cost_cents INTEGER NOT NULL
);

CREATE TABLE reservations (
    id            TEXT PRIMARY KEY,
    work_order_id TEXT NOT NULL REFERENCES work_orders(id),
    part_no       TEXT NOT NULL REFERENCES parts_inventory(part_no),
    qty           INTEGER NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE TABLE price_book (
    id               TEXT PRIMARY KEY,
    code             TEXT NOT NULL,  -- part_no or labor code e.g. LABOR-STD
    kind             TEXT NOT NULL,  -- part | labor
    revision         INTEGER NOT NULL,
    effective_from   TEXT NOT NULL,
    status           TEXT NOT NULL,  -- current | superseded
    unit_price_cents INTEGER NOT NULL
);

CREATE TABLE approvals (
    id               TEXT PRIMARY KEY,
    customer_id      TEXT NOT NULL REFERENCES customers(id),
    work_order_id    TEXT NOT NULL REFERENCES work_orders(id),
    max_amount_cents INTEGER NOT NULL,
    allowed_option   TEXT NOT NULL,  -- standard | overtime | any
    status           TEXT NOT NULL,  -- approved | pending | revoked
    created_by       TEXT NOT NULL
);

CREATE TABLE schedule (
    id            TEXT PRIMARY KEY,
    tech_id       TEXT NOT NULL REFERENCES technicians(id),
    date          TEXT NOT NULL,
    start_hour    INTEGER NOT NULL,
    end_hour      INTEGER NOT NULL,
    kind          TEXT NOT NULL,     -- shift | overtime | blackout | booking
    work_order_id TEXT REFERENCES work_orders(id)
);

CREATE TABLE email_messages (
    id        TEXT PRIMARY KEY,
    folder    TEXT NOT NULL,         -- inbox | draft | sent
    from_addr TEXT NOT NULL,
    to_addr   TEXT NOT NULL,
    subject   TEXT NOT NULL,
    body      TEXT NOT NULL,
    sent_at   TEXT NOT NULL
);

CREATE TABLE documents (
    id       TEXT PRIMARY KEY,
    title    TEXT NOT NULL,
    kind     TEXT NOT NULL,          -- service_bulletin | spec_sheet | policy
    model    TEXT NOT NULL,
    revision INTEGER NOT NULL,
    status   TEXT NOT NULL,          -- current | superseded
    body     TEXT NOT NULL
);

CREATE TABLE quotes (
    id                 TEXT PRIMARY KEY,
    work_order_id      TEXT NOT NULL REFERENCES work_orders(id),
    status             TEXT NOT NULL, -- draft | submitted
    labor_hours        TEXT NOT NULL, -- Decimal stored as text, exact
    labor_rate_cents   INTEGER NOT NULL,
    parts_json         TEXT NOT NULL,
    parts_total_cents  INTEGER NOT NULL,
    labor_total_cents  INTEGER NOT NULL,
    total_cents        INTEGER NOT NULL,
    option             TEXT NOT NULL,
    created_at         TEXT NOT NULL
);
