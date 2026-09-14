# FINAL-RUN — FieldServiceBench-10 acceptance evidence

Date: 2026-09-13. Host: macOS, Python 3.12 (homebrew), Docker 29.4.0, Harbor 0.21.0.
All commands run from `~/blobfish-reverse/replica/fieldservicebench/`.

## 1. Qualification gate — GREEN

```
$ python3.12 qualify.py --workdir runs        # exit code 0
==========================================================================
FieldServiceBench-10 qualification report
==========================================================================
FSB-01: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 30.71  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 91.43  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-02: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 30.71  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 91.43  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-03: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 39.29  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 91.43  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-04: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 27.86  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 91.43  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-05: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 32.50  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 93.33  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-06: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 37.50  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 94.29  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-07: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 37.50  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 96.67  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-08: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 37.00  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 80.00  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
FSB-09: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 37.00  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 80.00  OK
    control wrong-target    score= 76.67  OK
    control omission        score= 65.00  OK
FSB-10: oracle=100.0 replay=100.0 byte_identical=yes OK
    control noop            score= 25.00  OK
    control shortcut        score= 37.00  OK
    control state-only      score= 70.00  OK
    control wrong-evidence  score= 95.00  OK
    control wrong-target    score= 40.00  OK
    control omission        score= 65.00  OK
--------------------------------------------------------------------------
control mean scores (must all be < 100):
  noop            mean= 25.00  min= 25.00  max= 25.00
  shortcut        mean= 34.71  min= 27.86  max= 39.29
  state-only      mean= 70.00  min= 70.00  max= 70.00
  wrong-evidence  mean= 90.50  min= 80.00  max= 96.67
  wrong-target    mean= 43.67  min= 40.00  max= 76.67
  omission        mean= 65.00  min= 65.00  max= 65.00
--------------------------------------------------------------------------
RESULT: QUALIFIED (10/10 oracle strict=100 required; all controls < 100 required)
```

- 10/10 oracle strict at exactly 100.0; double replay byte-identical
  (trace bytes + canonical DB dump hash compared).
- 6 negative probes per task (5 controls + mutation-omission) all < 100.

## 2. Live server smoke test (curl)

World seeded fresh, server on 127.0.0.1:8378.

```
$ curl -X POST /call book_schedule{WO-5002 (decoy, status=open)}
{"error": {"code": "INVALID_STATE", "message": "work order WO-5002 status open; must be triaged"}, "ok": false}

$ curl -X POST /call book_schedule{WO-5001, 2026-03-05 (valid but NOT gold 03-04)}
{"ok": true, "result": {"booking_id": "BK-0001", "date": "2026-03-05", "end_hour": 12, "option": "standard", "start_hour": 8, "tech_id": "T-22"}}

$ curl -X POST /call get_schedule{T-22 from 2026-03-05} (readback)
{"ok": true, "result": [{"date": "2026-03-05", "end_hour": 12, "id": "BK-0001", "kind": "booking", "start_hour": 8, "tech_id": "T-22", "work_order_id": "WO-5001"}, {"date": "2026-03-05", "end_hour": 16, "id": "SCH-106", "kind": "shift", "start_hour": 8, "tech_id": "T-22", "work_order_id": null}]}
```

- Wrong-target write **rejected** at write time with a deterministic error.
- Schema-valid, rule-compliant but **non-gold** write **accepted and
  reflected** — the server enforces business rules, not the gold answer
  (gold is not leaked into the world).

## 3. Harbor oracle runs in Docker — reward 1.0 on both packaged tasks

```
$ harbor run -p harbor/task-fsb-01 -a oracle -o harbor/jobs --job-name fsb01-oracle -q
adhoc • oracle
┏━━━━━━━━┳━━━━━━━━━━━━┳━━━━━━━┓
┃ Trials ┃ Exceptions ┃  Mean ┃
┡━━━━━━━━╇━━━━━━━━━━━━╇━━━━━━━┩
│      1 │          0 │ 1.000 │
└────────┴────────────┴───────┘
┏━━━━━━━━┳━━━━━━━┓
┃ Reward ┃ Count ┃
┡━━━━━━━━╇━━━━━━━┩
│ 1.0    │     1 │
└────────┴───────┘
Total runtime: 1m 20s

$ cat harbor/jobs/fsb01-oracle/task-fsb-01__*/verifier/reward.txt
1.0
$ cat harbor/jobs/fsb01-oracle/task-fsb-01__*/agent/oracle.txt
FSB-01: score=100.0000 strict=PASS
  answer          20.00  (fraction 1.000)
  clean_writes    10.00  (fraction 1.000)
  containment     15.00  (fraction 1.000)
  gating          20.00  (fraction 1.000)
  readback        10.00  (fraction 1.000)
  state           25.00  (fraction 1.000)

$ harbor run -p harbor/task-fsb-05 -a oracle -o harbor/jobs --job-name fsb05-oracle -q
(same summary table: 1 trial, 0 exceptions, Mean 1.000, Reward 1.0; runtime 6m 57s)
$ cat harbor/jobs/fsb05-oracle/task-fsb-05__*/verifier/reward.txt
1.0
```

Harbor packaging per task: `task.toml` (schema 1.4), `instruction.md` (the
employee prompt), `environment/Dockerfile` (python:3.12-slim + the
self-contained app), `solution/solve.sh` (replays the oracle through the real
tool server in the container), `tests/test.sh` (runs `verify.py`, writes
`/logs/verifier/reward.txt`). Regenerate with `python3.12 harbor/build_harbor.py`.

Incident note (honest log): the first `task-fsb-01` attempt hit a Docker
Desktop daemon restart on this host — the trial itself completed with
`reward.txt = 1.0`, but the harbor CLI hung in environment teardown and was
killed; the run was repeated cleanly (above) after the daemon recovered.

## 4. Contaminated check

```
$ grep -riE "ERPBench|LedgerBench|CounselBench|FactoryBench|HubBench|SemiOps|ArcCRM|DealBench|SalesBench|ERPScore|CounselScore|SemiOpsScore|HubScore|blobfishai|dataset_factory|harbor_receipts|chain_adapter" .
(no matches)

$ grep -rni blobfish .   # excluding harbor/jobs run artifacts
./README.md:116:## Clean-room notes — deliberately different from Blobfish
./README.md:118:All code here is original; Blobfish reports were read for *pattern shape*
./README.md:121:- **Domain**: commercial HVAC field service — a domain Blobfish does not cover.
```

Only intentional meta-references in the README clean-room notes. No code,
identifiers, entity names, or text lifted from any Blobfish repo.

## 5. LOC & manifest

```
schema.sql 143 | seed.py 45 | tasks.py 869 | server.py 471 | runner.py 76
oracle.py 34 | verify.py 225 | controls.py 59 | qualify.py 91 | release.py 36
harbor/build_harbor.py 118  => 2167 core LOC (+ generated harbor task files)
```

`python3.12 release.py` -> `release_manifest.sha256` (37 files).
