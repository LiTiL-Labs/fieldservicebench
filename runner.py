"""Run a tool-call plan against a freshly seeded world + real HTTP tool server.

Produces a run directory:
  world.db      - database after the run
  baseline.db   - seeded database before the run (containment baseline)
  trace.jsonl   - server-side call trace (seq/tool/args/ok/result|error)
  contract.json - verifier contract for the task

Determinism: fresh seed, in-process server on an ephemeral localhost port,
fixed clock from the DB, counters from zero. No wall time anywhere.
"""

import hashlib
import json
import os
import shutil
import sqlite3
import threading
import urllib.request

import seed
import server
import tasks


def canonical_dump_hash(db_path):
    """Order-stable hash of every row in every table (counters included)."""
    conn = sqlite3.connect(db_path)
    h = hashlib.sha256()
    try:
        tables = [r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        for t in tables:
            cols = [r[1] for r in conn.execute(f"PRAGMA table_info({t})")]
            for row in conn.execute(f"SELECT * FROM {t} ORDER BY {', '.join(cols)}"):
                h.update(t.encode() + b"|" + repr(row).encode() + b"\n")
    finally:
        conn.close()
    return h.hexdigest()


def post(port, call, timeout=10):
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/call",
        data=json.dumps({"tool": call["tool"], "args": call["args"]}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def run_plan(task_id, plan, run_dir, quiet=True):
    os.makedirs(run_dir, exist_ok=True)
    db_path = os.path.join(run_dir, "world.db")
    trace_path = os.path.join(run_dir, "trace.jsonl")
    seed.build(db_path)
    shutil.copyfile(db_path, os.path.join(run_dir, "baseline.db"))

    httpd = server.serve(db_path, trace_path, port=0)
    port = httpd.server_address[1]
    th = threading.Thread(target=httpd.serve_forever, daemon=True)
    th.start()
    responses = []
    try:
        for call in plan:
            responses.append(post(port, call))
    finally:
        httpd.shutdown()
        httpd.server_close()
        th.join(timeout=5)

    contract = tasks.TASKS[task_id]["contract"]
    with open(os.path.join(run_dir, "contract.json"), "w", encoding="utf-8") as f:
        json.dump(contract, f, indent=2, sort_keys=True)
    return {"run_dir": run_dir, "db": db_path,
            "baseline": os.path.join(run_dir, "baseline.db"),
            "trace": trace_path, "contract": contract, "responses": responses}
