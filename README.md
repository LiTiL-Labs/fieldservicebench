# FieldServiceBench-10

A small, fully deterministic, **clean-room** agent benchmark in the style of
the "world + tools + oracle + verifier" pattern: a fictional commercial-HVAC
field-service company (*Apex Climate Services*) modeled in SQLite, a
provider-shaped JSON tool server (stdlib `http.server` only), 10 hand-authored
employee-request tasks, a reference oracle, a deterministic no-LLM verifier,
and 5 adversarial controls + a mutation-omission probe as mechanical plan
transforms.

- **Zero dependencies**: Python 3.12 standard library only.
- **Deterministic**: fixed simulation clock (`config('now') = 2026-03-02`),
  counter-generated ids, no wall-clock or RNG anywhere; replays are
  byte-identical.
- **Self-contained**: world, tasks, oracle, verifier, controls, qualification
  gate, and Harbor packaging in one tree.

## Layout

```
schema.sql    world schema (14 tables)
seed.py       deterministic world builder (noise rows + 10 task clusters)
tasks.py      10 scenario spines + decision specs; derives prompts, gold
              answers (Decimal math), oracle plans, verifier contracts
server.py     tool server: 25 tools (18 read, 7 write), business-rule
              rejections, JSONL trace of every call
runner.py     seed -> serve (ephemeral localhost port) -> run plan -> artifacts
oracle.py     replays a task's reference plan through the real server
verify.py     deterministic verifier (trace + state + containment + answer)
controls.py   noop / shortcut / state-only / wrong-evidence / wrong-target
              (+ omission probe) as mechanical transforms of the oracle plan
qualify.py    runs oracle twice + all controls on all 10 tasks; exit != 0
              unless every oracle is strict-100 and every control < 100
harbor/       Harbor-format packaging for 2 tasks + generator script
```

## The world

Tables: `customers, sites, assets, technicians, work_orders, parts_inventory,
reservations, price_book, approvals, schedule, email_messages, documents,
quotes, config, counters`. The evidence room deliberately contains current vs
superseded revisions (documents, price book), decoys (similarly named sites,
look-alike parts and units), quarantined stock, expired tech certifications,
and approvals scoped to one work order with a max amount and an allowed
option. **Gold is never precomputed in any agent-visible artifact** — it lives
only in the verifier contract, derived from the seed by pure functions.

Tools (25): `list/get` for customers, sites, assets, technicians, work orders;
`query_parts`, `get_price_book`, `list_approvals`, `get_schedule`,
`list_emails`, `list_documents`, `get_document`, `get_quote`; writes:
`transition_work_order`, `reserve_parts`, `book_schedule`, `create_quote`,
`update_quote`, `draft_email`, `submit_answer`. Writes are validated at write
time with deterministic error codes (`INVALID_STATE`, `CERT_EXPIRED`,
`TIME_CONFLICT`, `NO_APPROVAL`, `APPROVAL_SCOPE`, `APPROVAL_EXCEEDED`,
`INSUFFICIENT_STOCK`, `NOT_FOUND`, ...). The server enforces **business rules,
never gold** — a schema-valid, rule-compliant but non-gold write is accepted.

## The 10 tasks

| task | archetype | core trap(s) |
|------|-----------|--------------|
| FSB-01 | commit repair visit | expired cert on the early tech; approval covers standard only |
| FSB-02 | commit repair visit | superseded part price; overtime exceeds cap |
| FSB-03 | commit repair visit | primary part fully quarantined; alternate only in current bulletin |
| FSB-04 | commit repair visit | decoy look-alike site/unit; blackout window; expired cert |
| FSB-05 | quote | superseded price book revision is cheaper |
| FSB-06 | quote | customer prefers OEM but approval cap only fits reman |
| FSB-07 | quote | labor hours changed in current bulletin revision |
| FSB-08 | reserve parts | on-hand hides reserved+quarantined units |
| FSB-09 | reserve parts | similarly named legacy valve is incompatible per current bulletin |
| FSB-10 | reserve parts | superseded PM standard says half the quantity; existing reservations |

Each task requires evidence across 3+ systems (email, work orders, documents,
price book, inventory, approvals, schedule), reconciling current vs superseded
revisions, comparing 2–3 options of which exactly one is authorized+optimal,
executing **exactly one authorized mutation**, and submitting exact answer
fields via `submit_answer`.

## Verifier (deterministic, fail-closed)

Weighted milestones summing to 100; strict pass iff score == 100.0;
proportional partial credit per milestone:

- **gating (20)** — required evidence reads before the first write, matched by
  **exact tool+args** (documented choice; readback uses semantic matching).
- **clean_writes (10)** — zero rejected write calls (incl. `submit_answer`).
- **state (25)** — exact expected values via SQL against the final DB.
- **containment (15)** — immutable tables row-identical AND every changed row
  of a mutable table inside the task allow-list; auto-fails on any rejected
  write.
- **readback (10)** — a read after the successful mutation whose response
  contains the mutated record's id.
- **answer (20)** — last `submit_answer` fields vs gold; normalization per
  field type (str: strip+casefold, int/decimal: `Decimal` equality, date:
  exact ISO).

## Run it

```bash
PY=/opt/homebrew/bin/python3.12        # any python >= 3.10 works
$PY oracle.py  --task FSB-01 --workdir runs/FSB-01     # single oracle run
$PY qualify.py --workdir runs                          # full gate (10 tasks)
$PY harbor/build_harbor.py                             # regen Harbor task dirs
harbor run -p harbor/task-fsb-01 -a oracle             # Harbor oracle run
```

Manual server for poking around:

```bash
$PY seed.py /tmp/world.db
$PY server.py --db /tmp/world.db --trace /tmp/trace.jsonl --port 8377 &
curl -X POST http://127.0.0.1:8377/call -H 'Content-Type: application/json' \
  -d '{"tool":"query_parts","args":{"part_no":"P-3001"}}'
```

## Clean-room notes — deliberately different from Blobfish

All code here is original; Blobfish reports were read for *pattern shape*
only. Concrete design choices of our own:

- **Domain**: commercial HVAC field service — a domain Blobfish does not cover.
- **Transport**: single `/call` JSON endpoint over stdlib `http.server`
  (not MCP/JSON-RPC framing); trace is written by the server itself.
- **IDs**: human-readable text PKs (`WO-5001`, `BK-0001`) so allow-lists and
  assertions are readable; generated ids come from a `counters` table.
- **Matching**: evidence gating by *exact args*; readback by *semantic
  containment* of the mutated id in a later read response.
- **World sharing**: all 10 task clusters coexist in one seeded world;
  per-task isolation is enforced by the containment allow-list instead of
  per-task databases.
- **Server-side pricing**: `create_quote` computes totals from the *current*
  price book at write time, so even a malicious write cannot quote off a
  superseded revision — revision discipline is checked in the *answer*.
- **Release**: Apache-2.0 (see `LICENSE`), plus `release_manifest.sha256`.
