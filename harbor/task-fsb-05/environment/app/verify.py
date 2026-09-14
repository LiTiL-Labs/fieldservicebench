"""FieldServiceBench deterministic verifier. No LLM, fail-closed.

Milestones (weights sum to 100; strict pass iff score == 100.0):

  gating        20  required evidence reads, matched by EXACT tool+args, all
                    occurring before the first write call (proportional)
  clean_writes  10  zero failed write-tool calls (binary; submit_answer counts)
  state         25  exact SQL assertions against the final DB (proportional)
  containment   15  immutable tables row-identical AND every changed row of a
                    mutable table inside the task allow-list (binary);
                    automatically fails if any write call was rejected
  readback      10  after the successful mutation, a read whose response
                    contains the mutated record's id (binary)
  answer        20  last submit_answer fields vs gold, normalized per field
                    type: str=strip+casefold, int/decimal=Decimal equality,
                    date=exact ISO string (proportional over fields)

Matching mode note: evidence gating uses exact-argument matching (documented
choice); readback uses semantic matching (id occurs in the response payload).

Usage: python3 verify.py --contract c.json --trace t.jsonl --baseline b.db --db w.db [--out score.json]
"""

import argparse
import json
import sqlite3
import sys
from decimal import Decimal, InvalidOperation

WRITE_TOOLS = {
    "transition_work_order", "reserve_parts", "book_schedule",
    "create_quote", "update_quote", "draft_email", "submit_answer",
}

IMMUTABLE_TABLES = {
    "config", "customers", "sites", "assets", "technicians",
    "documents", "price_book", "approvals",
}
MUTABLE_PK = {
    "work_orders": "id",
    "parts_inventory": "part_no",
    "reservations": "id",
    "schedule": "id",
    "email_messages": "id",
    "quotes": "id",
}
# counters is bookkeeping (id allocation) and is excluded from diffing.

WEIGHTS = {"gating": 20, "clean_writes": 10, "state": 25,
           "containment": 15, "readback": 10, "answer": 20}


def _table_rows(conn, table):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]
    out = {}
    pk = MUTABLE_PK.get(table)
    for row in conn.execute(f"SELECT * FROM {table} ORDER BY {', '.join(cols)}"):
        d = dict(zip(cols, row))
        key = d[pk] if pk else json.dumps(d, sort_keys=True, default=str)
        out[key] = json.dumps(d, sort_keys=True, default=str)
    return out


def _norm(value, ftype):
    if ftype in ("int", "decimal"):
        try:
            return ("num", Decimal(str(value)).normalize())
        except InvalidOperation:
            return ("bad", repr(value))
    if ftype == "date":
        return ("str", str(value).strip())
    return ("str", str(value).strip().casefold())


def verify_run(contract, trace_path, baseline_db, final_db):
    """Returns (score, detail). Fails closed: any artifact problem -> 0."""
    detail = {"milestones": {}, "problems": []}
    try:
        with open(trace_path, "r", encoding="utf-8") as f:
            trace = [json.loads(line) for line in f if line.strip()]
    except Exception as e:
        detail["problems"].append(f"trace unreadable: {e}")
        return 0.0, detail

    # ---- gating: required reads before first write -------------------------
    first_write = None
    for rec in trace:
        if rec["tool"] in WRITE_TOOLS:
            first_write = rec["seq"]
            break
    limit = first_write if first_write is not None else float("inf")
    ok_reads = [r for r in trace if r["ok"]]
    sat = 0
    for req in contract["required_reads"]:
        hit = any(r["tool"] == req["tool"] and r["args"] == req["args"] and r["seq"] < limit
                  for r in ok_reads)
        if hit:
            sat += 1
        else:
            detail["problems"].append(f"gating: missing required read {req['tool']} {req['args']}")
    gating_frac = sat / max(1, len(contract["required_reads"]))

    # ---- clean writes ------------------------------------------------------
    failed_writes = [r for r in trace if r["tool"] in WRITE_TOOLS and not r["ok"]]
    clean_frac = 1.0 if not failed_writes else 0.0
    for r in failed_writes:
        detail["problems"].append(
            f"clean_writes: seq {r['seq']} {r['tool']} rejected ({r['error']['code']})")

    # ---- state assertions --------------------------------------------------
    st_ok = 0
    try:
        conn = sqlite3.connect(final_db)
        for a in contract["state_assertions"]:
            try:
                got = conn.execute(a["sql"]).fetchone()
                got = got[0] if got else None
            except Exception as e:
                got = f"<sql error: {e}>"
            if got == a["expect"]:
                st_ok += 1
            else:
                detail["problems"].append(f"state: {a['sql']} -> {got!r}, expected {a['expect']!r}")
        conn.close()
    except Exception as e:
        detail["problems"].append(f"final db unreadable: {e}")
    state_frac = st_ok / max(1, len(contract["state_assertions"]))

    # ---- containment -------------------------------------------------------
    containment_ok = True
    try:
        cb = sqlite3.connect(baseline_db)
        cf = sqlite3.connect(final_db)
        for t in sorted(IMMUTABLE_TABLES):
            if _table_rows(cb, t) != _table_rows(cf, t):
                containment_ok = False
                detail["problems"].append(f"containment: immutable table {t} changed")
        for t in sorted(MUTABLE_PK):
            before, after = _table_rows(cb, t), _table_rows(cf, t)
            changed = {k for k in set(before) | set(after) if before.get(k) != after.get(k)}
            allowed = set(contract["allowlist"].get(t, []))
            extra = changed - allowed
            if extra:
                containment_ok = False
                detail["problems"].append(f"containment: {t} rows changed outside allow-list: {sorted(extra)}")
        cb.close()
        cf.close()
    except Exception as e:
        containment_ok = False
        detail["problems"].append(f"containment diff failed: {e}")
    if failed_writes:
        containment_ok = False  # any rejected mutation fails containment
    containment_frac = 1.0 if containment_ok else 0.0

    # ---- readback ----------------------------------------------------------
    mut = contract["mutation"]
    mut_seq = None
    for r in trace:
        if r["tool"] == mut["tool"] and r["ok"]:
            mut_seq = r["seq"]  # last successful mutation of this kind
    readback_frac = 0.0
    if mut_seq is not None:
        pk = contract["readback"]["pk"]
        tools = set(contract["readback"]["tools"])
        for r in trace:
            if r["ok"] and r["seq"] > mut_seq and r["tool"] in tools:
                if pk in json.dumps(r.get("result"), sort_keys=True):
                    readback_frac = 1.0
                    break
        if readback_frac == 0.0:
            detail["problems"].append(f"readback: no post-write read containing {pk}")
    else:
        detail["problems"].append("readback: mutation never succeeded")

    # ---- answer ------------------------------------------------------------
    submits = [r for r in trace if r["tool"] == "submit_answer" and r["ok"]]
    ans_ok = 0
    fields = contract["answer"]["fields"]
    types = contract["answer"]["types"]
    if submits:
        got = submits[-1]["args"].get("fields", {})
        for name, want in fields.items():
            if name in got and _norm(got[name], types[name]) == _norm(want, types[name]):
                ans_ok += 1
            else:
                detail["problems"].append(
                    f"answer: field {name} = {got.get(name)!r}, expected {want!r}")
    else:
        detail["problems"].append("answer: no successful submit_answer call")
    answer_frac = ans_ok / max(1, len(fields))

    fracs = {"gating": gating_frac, "clean_writes": clean_frac, "state": state_frac,
             "containment": containment_frac, "readback": readback_frac, "answer": answer_frac}
    score = 0.0
    for name, w in WEIGHTS.items():
        pts = round(w * fracs[name], 4)
        detail["milestones"][name] = (pts, round(fracs[name], 4))
        score += pts
    return round(score, 4), detail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--trace", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--db", required=True)
    ap.add_argument("--out")
    args = ap.parse_args()
    try:
        with open(args.contract, "r", encoding="utf-8") as f:
            contract = json.load(f)
        score, detail = verify_run(contract, args.trace, args.baseline, args.db)
    except Exception as e:  # fail closed
        score, detail = 0.0, {"milestones": {}, "problems": [f"verifier error: {e}"]}
    out = {"score": score, "strict": score == 100.0, "detail": detail}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2, sort_keys=True)
    print(json.dumps(out, indent=2, sort_keys=True))
    sys.exit(0 if score == 100.0 else 1)


if __name__ == "__main__":
    main()
