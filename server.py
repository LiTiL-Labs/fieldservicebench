"""FieldServiceBench tool server.

Provider-shaped JSON tool server over HTTP (stdlib http.server only).
POST /call {"tool": <name>, "args": {...}} -> {"ok": true, "result": ...}
                                          or {"ok": false, "error": {"code", "message"}}
Every call is appended to a JSONL trace with a deterministic sequence number.

Determinism: the simulation clock comes from config('now') in the seeded DB;
generated ids come from the counters table; nothing reads wall time or RNG.

Usage: python3 server.py --db <path> --trace <jsonl> --port <n>
"""

import argparse
import json
import sqlite3
import threading
from decimal import Decimal
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

READ_TOOLS = {
    "list_customers", "get_customer", "list_sites", "get_site", "list_assets", "get_asset",
    "list_technicians", "get_technician", "list_work_orders", "get_work_order",
    "query_parts", "get_price_book", "list_approvals", "get_schedule",
    "list_emails", "list_documents", "get_document", "get_quote",
}
WRITE_TOOLS = {
    "transition_work_order", "reserve_parts", "book_schedule",
    "create_quote", "update_quote", "draft_email", "submit_answer",
}
ALL_TOOLS = READ_TOOLS | WRITE_TOOLS

# open -> triaged -> scheduled -> in_progress -> completed -> closed; cancel early
TRANSITIONS = {
    "open": {"triaged", "cancelled"},
    "triaged": {"scheduled", "cancelled"},
    "scheduled": {"in_progress", "cancelled"},
    "in_progress": {"completed"},
    "completed": {"closed"},
    "cancelled": set(),
    "closed": set(),
}
RESERVABLE_WO_STATUSES = {"open", "triaged", "scheduled"}
QUOTABLE_WO_STATUSES = {"triaged", "scheduled"}


class ToolError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def rows(cur):
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def one(cur):
    r = rows(cur)
    return r[0] if r else None


class World:
    def __init__(self, db_path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.lock = threading.Lock()

    def now(self):
        return self.conn.execute("SELECT value FROM config WHERE key='now'").fetchone()[0]

    def next_id(self, prefix):
        self.conn.execute("UPDATE counters SET n = n + 1 WHERE name = ?", (prefix,))
        n = self.conn.execute("SELECT n FROM counters WHERE name = ?", (prefix,)).fetchone()[0]
        return f"{prefix}-{n:04d}"

    # ---------------- read tools ----------------

    def list_customers(self, a):
        return rows(self.conn.execute("SELECT * FROM customers ORDER BY id"))

    def get_customer(self, a):
        r = one(self.conn.execute("SELECT * FROM customers WHERE id = ?", (a["customer_id"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"customer {a['customer_id']}")
        return r

    def list_sites(self, a):
        if "customer_id" in a:
            return rows(self.conn.execute("SELECT * FROM sites WHERE customer_id = ? ORDER BY id",
                                          (a["customer_id"],)))
        return rows(self.conn.execute("SELECT * FROM sites ORDER BY id"))

    def get_site(self, a):
        r = one(self.conn.execute("SELECT * FROM sites WHERE id = ?", (a["site_id"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"site {a['site_id']}")
        return r

    def list_assets(self, a):
        if "site_id" in a:
            return rows(self.conn.execute("SELECT * FROM assets WHERE site_id = ? ORDER BY id",
                                          (a["site_id"],)))
        return rows(self.conn.execute("SELECT * FROM assets ORDER BY id"))

    def get_asset(self, a):
        r = one(self.conn.execute("SELECT * FROM assets WHERE id = ?", (a["asset_id"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"asset {a['asset_id']}")
        return r

    def list_technicians(self, a):
        if "region" in a:
            return rows(self.conn.execute("SELECT * FROM technicians WHERE region = ? ORDER BY id",
                                          (a["region"],)))
        return rows(self.conn.execute("SELECT * FROM technicians ORDER BY id"))

    def get_technician(self, a):
        r = one(self.conn.execute("SELECT * FROM technicians WHERE id = ?", (a["tech_id"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"technician {a['tech_id']}")
        return r

    def list_work_orders(self, a):
        q, p = "SELECT * FROM work_orders", []
        conds = []
        for k in ("customer_id", "site_id", "status"):
            if k in a:
                conds.append(f"{k} = ?")
                p.append(a[k])
        if conds:
            q += " WHERE " + " AND ".join(conds)
        return rows(self.conn.execute(q + " ORDER BY id", p))

    def get_work_order(self, a):
        r = one(self.conn.execute("SELECT * FROM work_orders WHERE id = ?", (a["work_order_id"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"work order {a['work_order_id']}")
        return r

    def query_parts(self, a):
        if "part_no" in a:
            r = one(self.conn.execute("SELECT * FROM parts_inventory WHERE part_no = ?", (a["part_no"],)))
            if not r:
                raise ToolError("NOT_FOUND", f"part {a['part_no']}")
            r["available"] = r["on_hand"] - r["reserved"] - r["quarantined"]
            r["reservations"] = rows(self.conn.execute(
                "SELECT * FROM reservations WHERE part_no = ? ORDER BY id", (a["part_no"],)))
            return r
        out = rows(self.conn.execute("SELECT * FROM parts_inventory ORDER BY part_no"))
        for r in out:
            r["available"] = r["on_hand"] - r["reserved"] - r["quarantined"]
        return out

    def get_price_book(self, a):
        r = rows(self.conn.execute(
            "SELECT * FROM price_book WHERE code = ? ORDER BY revision", (a["code"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"price book code {a['code']}")
        return r

    def list_approvals(self, a):
        return rows(self.conn.execute(
            "SELECT * FROM approvals WHERE work_order_id = ? ORDER BY id", (a["work_order_id"],)))

    def get_schedule(self, a):
        q = "SELECT * FROM schedule WHERE tech_id = ?"
        p = [a["tech_id"]]
        if "date_from" in a:
            q += " AND date >= ?"
            p.append(a["date_from"])
        if "date_to" in a:
            q += " AND date <= ?"
            p.append(a["date_to"])
        return rows(self.conn.execute(q + " ORDER BY date, start_hour, id", p))

    def list_emails(self, a):
        return rows(self.conn.execute(
            "SELECT * FROM email_messages WHERE folder = ? ORDER BY sent_at, id", (a["folder"],)))

    def list_documents(self, a):
        q, p = "SELECT id, title, kind, model, revision, status FROM documents", []
        conds = []
        for k in ("kind", "model", "status"):
            if k in a and a[k] != "":
                conds.append(f"{k} = ?")
                p.append(a[k])
        if conds:
            q += " WHERE " + " AND ".join(conds)
        return rows(self.conn.execute(q + " ORDER BY id", p))

    def get_document(self, a):
        r = one(self.conn.execute("SELECT * FROM documents WHERE id = ?", (a["document_id"],)))
        if not r:
            raise ToolError("NOT_FOUND", f"document {a['document_id']}")
        return r

    def get_quote(self, a):
        return rows(self.conn.execute(
            "SELECT * FROM quotes WHERE work_order_id = ? ORDER BY id", (a["work_order_id"],)))

    # ---------------- write tools ----------------

    def _wo(self, wo_id):
        r = one(self.conn.execute("SELECT * FROM work_orders WHERE id = ?", (wo_id,)))
        if not r:
            raise ToolError("NOT_FOUND", f"work order {wo_id}")
        return r

    def transition_work_order(self, a):
        wo = self._wo(a["work_order_id"])
        to = a["to"]
        if to not in TRANSITIONS[wo["status"]]:
            raise ToolError("INVALID_TRANSITION", f"{wo['status']} -> {to} not allowed")
        self.conn.execute("UPDATE work_orders SET status = ? WHERE id = ?", (to, wo["id"]))
        self.conn.commit()
        return {"work_order_id": wo["id"], "status": to}

    def reserve_parts(self, a):
        wo = self._wo(a["work_order_id"])
        if wo["status"] not in RESERVABLE_WO_STATUSES:
            raise ToolError("INVALID_STATE", f"work order {wo['id']} status {wo['status']} not reservable")
        part = one(self.conn.execute("SELECT * FROM parts_inventory WHERE part_no = ?", (a["part_no"],)))
        if not part:
            raise ToolError("NOT_FOUND", f"part {a['part_no']}")
        qty = a["qty"]
        if not isinstance(qty, int) or qty <= 0:
            raise ToolError("INVALID_INPUT", "qty must be a positive integer")
        available = part["on_hand"] - part["reserved"] - part["quarantined"]
        if qty > available:
            raise ToolError("INSUFFICIENT_STOCK",
                            f"requested {qty} but only {available} available "
                            f"(on_hand {part['on_hand']} - reserved {part['reserved']} "
                            f"- quarantined {part['quarantined']})")
        rid = self.next_id("RSV")
        self.conn.execute("UPDATE parts_inventory SET reserved = reserved + ? WHERE part_no = ?",
                          (qty, a["part_no"]))
        self.conn.execute(
            "INSERT INTO reservations (id, work_order_id, part_no, qty, created_at) VALUES (?,?,?,?,?)",
            (rid, wo["id"], a["part_no"], qty, self.now()))
        self.conn.commit()
        return {"reservation_id": rid, "part_no": a["part_no"], "qty": qty,
                "available_after": available - qty}

    def book_schedule(self, a):
        wo = self._wo(a["work_order_id"])
        if wo["status"] != "triaged":
            raise ToolError("INVALID_STATE", f"work order {wo['id']} status {wo['status']}; must be triaged")
        tech = one(self.conn.execute("SELECT * FROM technicians WHERE id = ?", (a["tech_id"],)))
        if not tech:
            raise ToolError("NOT_FOUND", f"technician {a['tech_id']}")
        date, start, hours = a["date"], a["start_hour"], a["hours"]
        if not isinstance(start, int) or not isinstance(hours, int) or hours <= 0:
            raise ToolError("INVALID_INPUT", "start_hour/hours must be integers, hours > 0")
        end = start + hours
        if tech["cert_expires"] < date:
            raise ToolError("CERT_EXPIRED",
                            f"{tech['id']} cert {tech['cert_type']} expired {tech['cert_expires']}")
        if wo["kind"] not in tech["skills"].split(","):
            raise ToolError("SKILL_MISMATCH", f"{tech['id']} lacks skill {wo['kind']}")
        shift = one(self.conn.execute(
            "SELECT * FROM schedule WHERE tech_id = ? AND date = ? AND kind IN ('shift','overtime') "
            "AND start_hour <= ? AND end_hour >= ?", (tech["id"], date, start, end)))
        if not shift:
            raise ToolError("NO_SHIFT", f"{tech['id']} has no shift covering {date} {start}-{end}")
        conflict = one(self.conn.execute(
            "SELECT * FROM schedule WHERE tech_id = ? AND date = ? AND kind IN ('booking','blackout') "
            "AND start_hour < ? AND end_hour > ?", (tech["id"], date, end, start)))
        if conflict:
            raise ToolError("TIME_CONFLICT",
                            f"{tech['id']} has {conflict['kind']} {conflict['id']} overlapping")
        appr = one(self.conn.execute(
            "SELECT * FROM approvals WHERE work_order_id = ? AND status = 'approved'", (wo["id"],)))
        if not appr:
            raise ToolError("NO_APPROVAL", f"no approved approval for {wo['id']}")
        option = "overtime" if shift["kind"] == "overtime" else "standard"
        if appr["allowed_option"] not in (option, "any"):
            raise ToolError("APPROVAL_SCOPE",
                            f"approval {appr['id']} covers {appr['allowed_option']} only")
        bid = self.next_id("BK")
        self.conn.execute(
            "INSERT INTO schedule (id, tech_id, date, start_hour, end_hour, kind, work_order_id) "
            "VALUES (?,?,?,?,?,'booking',?)", (bid, tech["id"], date, start, end, wo["id"]))
        self.conn.commit()
        return {"booking_id": bid, "tech_id": tech["id"], "date": date,
                "start_hour": start, "end_hour": end, "option": option}

    def _current_price(self, code, kind):
        r = one(self.conn.execute(
            "SELECT * FROM price_book WHERE code = ? AND kind = ? AND status = 'current'", (code, kind)))
        if not r:
            raise ToolError("PRICE_NOT_FOUND", f"no current {kind} price for {code}")
        return r["unit_price_cents"]

    def _quote_totals(self, labor_hours, parts):
        try:
            hours = Decimal(str(labor_hours))
        except Exception:
            raise ToolError("INVALID_INPUT", f"labor_hours {labor_hours!r} not a number")
        if hours <= 0:
            raise ToolError("INVALID_INPUT", "labor_hours must be > 0")
        labor_rate = self._current_price("LABOR-STD", "labor")
        labor_total = int((hours * labor_rate).quantize(Decimal("1")))
        parts_total = 0
        norm_parts = []
        for p in parts:
            part = one(self.conn.execute("SELECT * FROM parts_inventory WHERE part_no = ?",
                                         (p["part_no"],)))
            if not part:
                raise ToolError("NOT_FOUND", f"part {p['part_no']}")
            qty = p["qty"]
            if not isinstance(qty, int) or qty <= 0:
                raise ToolError("INVALID_INPUT", "part qty must be a positive integer")
            unit = self._current_price(p["part_no"], "part")
            parts_total += unit * qty
            norm_parts.append({"part_no": p["part_no"], "qty": qty, "unit_price_cents": unit})
        return hours, labor_rate, labor_total, parts_total, norm_parts

    def create_quote(self, a):
        wo = self._wo(a["work_order_id"])
        if wo["status"] not in QUOTABLE_WO_STATUSES:
            raise ToolError("INVALID_STATE", f"work order {wo['id']} status {wo['status']}; not quotable")
        appr = one(self.conn.execute(
            "SELECT * FROM approvals WHERE work_order_id = ? AND status = 'approved'", (wo["id"],)))
        if not appr:
            raise ToolError("NO_APPROVAL", f"no approved approval for {wo['id']}")
        hours, rate, labor_total, parts_total, norm_parts = self._quote_totals(
            a["labor_hours"], a.get("parts", []))
        total = labor_total + parts_total
        if total > appr["max_amount_cents"]:
            raise ToolError("APPROVAL_EXCEEDED",
                            f"total {total} exceeds approval {appr['id']} cap {appr['max_amount_cents']}")
        qid = self.next_id("Q")
        status = "submitted" if a.get("submit") else "draft"
        self.conn.execute(
            "INSERT INTO quotes (id, work_order_id, status, labor_hours, labor_rate_cents, parts_json, "
            "parts_total_cents, labor_total_cents, total_cents, option, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (qid, wo["id"], status, str(hours.normalize()), rate, json.dumps(norm_parts, sort_keys=True),
             parts_total, labor_total, total, a.get("option", "standard"), self.now()))
        self.conn.commit()
        return {"quote_id": qid, "status": status, "parts_total_cents": parts_total,
                "labor_total_cents": labor_total, "total_cents": total, "approval_id": appr["id"]}

    def update_quote(self, a):
        q = one(self.conn.execute("SELECT * FROM quotes WHERE id = ?", (a["quote_id"],)))
        if not q:
            raise ToolError("NOT_FOUND", f"quote {a['quote_id']}")
        if q["status"] != "draft":
            raise ToolError("INVALID_STATE", f"quote {q['id']} is {q['status']}; only drafts are editable")
        labor_hours = a.get("labor_hours", q["labor_hours"])
        parts = a.get("parts", json.loads(q["parts_json"]))
        appr = one(self.conn.execute(
            "SELECT * FROM approvals WHERE work_order_id = ? AND status = 'approved'",
            (q["work_order_id"],)))
        hours, rate, labor_total, parts_total, norm_parts = self._quote_totals(labor_hours, parts)
        total = labor_total + parts_total
        if appr and total > appr["max_amount_cents"]:
            raise ToolError("APPROVAL_EXCEEDED",
                            f"total {total} exceeds approval {appr['id']} cap {appr['max_amount_cents']}")
        self.conn.execute(
            "UPDATE quotes SET labor_hours = ?, labor_rate_cents = ?, parts_json = ?, "
            "parts_total_cents = ?, labor_total_cents = ?, total_cents = ? WHERE id = ?",
            (str(hours.normalize()), rate, json.dumps(norm_parts, sort_keys=True),
             parts_total, labor_total, total, q["id"]))
        self.conn.commit()
        return {"quote_id": q["id"], "parts_total_cents": parts_total,
                "labor_total_cents": labor_total, "total_cents": total}

    def draft_email(self, a):
        if "@" not in a.get("to_addr", ""):
            raise ToolError("INVALID_INPUT", "to_addr must be an email address")
        eid = self.next_id("EM")
        self.conn.execute(
            "INSERT INTO email_messages (id, folder, from_addr, to_addr, subject, body, sent_at) "
            "VALUES (?,'draft','dispatch@apexclimate.example',?,?,?,?)",
            (eid, a["to_addr"], a.get("subject", ""), a.get("body", ""), self.now()))
        self.conn.commit()
        return {"email_id": eid, "folder": "draft"}

    def submit_answer(self, a):
        fields = a.get("fields")
        if not isinstance(fields, dict) or not fields:
            raise ToolError("INVALID_INPUT", "submit_answer requires non-empty 'fields' object")
        return {"accepted": True, "fields_received": sorted(fields.keys())}


class Handler(BaseHTTPRequestHandler):
    world = None
    trace_path = None
    trace_lock = threading.Lock()
    seq = 0

    def log_message(self, *args):  # silence request logs (keeps runs byte-clean)
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, sort_keys=True).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/health":
            self._send(200, {"ok": True, "tools": sorted(ALL_TOOLS)})
        else:
            self._send(404, {"ok": False, "error": {"code": "BAD_PATH", "message": self.path}})

    def do_POST(self):
        if self.path != "/call":
            self._send(404, {"ok": False, "error": {"code": "BAD_PATH", "message": self.path}})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            req = json.loads(self.rfile.read(length).decode())
            tool, args = req["tool"], req.get("args", {})
        except Exception as e:
            self._send(400, {"ok": False, "error": {"code": "BAD_REQUEST", "message": str(e)}})
            return

        if tool not in ALL_TOOLS:
            resp = {"ok": False, "error": {"code": "TOOL_NOT_FOUND", "message": tool}}
        elif not isinstance(args, dict):
            resp = {"ok": False, "error": {"code": "BAD_ARGS", "message": "args must be an object"}}
        else:
            with self.world.lock:
                try:
                    result = getattr(self.world, tool)(args)
                    resp = {"ok": True, "result": result}
                except ToolError as e:
                    self.world.conn.rollback()
                    resp = {"ok": False, "error": {"code": e.code, "message": e.message}}
                except (KeyError, TypeError) as e:
                    self.world.conn.rollback()
                    resp = {"ok": False, "error": {"code": "BAD_ARGS",
                                                   "message": f"{type(e).__name__}: {e}"}}
        with Handler.trace_lock:
            Handler.seq += 1
            rec = {"seq": Handler.seq, "tool": tool, "args": args, "ok": resp["ok"]}
            if resp["ok"]:
                rec["result"] = resp["result"]
            else:
                rec["error"] = resp["error"]
            with open(self.trace_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, sort_keys=True, separators=(",", ":")) + "\n")
        self._send(200, resp)


def serve(db_path, trace_path, port):
    Handler.world = World(db_path)
    Handler.trace_path = trace_path
    Handler.seq = 0
    open(trace_path, "w").close()
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--port", type=int, default=8377)
    args = ap.parse_args()
    httpd = serve(args.db, args.trace, args.port)
    print(f"tool server on 127.0.0.1:{args.port} db={args.db} trace={args.trace}", flush=True)
    httpd.serve_forever()


if __name__ == "__main__":
    main()
