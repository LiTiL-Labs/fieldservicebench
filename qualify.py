"""Qualification gate for FieldServiceBench-10.

For every task:
  * oracle run -> verifier score must be exactly 100.0 (strict)
  * second oracle run -> score 100.0 AND byte-identical trace AND identical
    canonical DB dump hash (deterministic replay)
  * all 5 adversarial controls + the mutation-omission probe must score < 100

Prints a report; exit 0 only if every gate passes.
Usage: python3 qualify.py [--workdir runs]
"""

import argparse
import hashlib
import json
import os
import sys

import controls
import runner
import tasks
import verify


def file_hash(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workdir", default="runs")
    args = ap.parse_args()

    all_ok = True
    control_scores = {c: [] for c in controls.CONTROL_NAMES}
    lines = []

    for task_id in tasks.TASK_IDS:
        task = tasks.TASKS[task_id]
        # --- oracle + replay ---
        runs = []
        for tag in ("oracle-a", "oracle-b"):
            art = runner.run_plan(task_id, task["plan"], os.path.join(args.workdir, task_id, tag))
            score, detail = verify.verify_run(art["contract"], art["trace"], art["baseline"], art["db"])
            runs.append((score, detail, art))
        s1, d1, a1 = runs[0]
        s2, d2, a2 = runs[1]
        replay_ok = (file_hash(a1["trace"]) == file_hash(a2["trace"]) and
                     runner.canonical_dump_hash(a1["db"]) == runner.canonical_dump_hash(a2["db"]))
        oracle_ok = (s1 == 100.0 and s2 == 100.0)
        if not (oracle_ok and replay_ok):
            all_ok = False
        lines.append(f"{task_id}: oracle={s1:.1f} replay={s2:.1f} "
                     f"byte_identical={'yes' if replay_ok else 'NO'} "
                     f"{'OK' if oracle_ok and replay_ok else 'FAIL'}")
        for s, d, tag in ((s1, d1, "oracle-a"), (s2, d2, "oracle-b")):
            if s != 100.0:
                for p in d["problems"]:
                    lines.append(f"    [{tag}] {p}")

        # --- controls ---
        for cname in controls.CONTROL_NAMES:
            plan = controls.transform(cname, task)
            art = runner.run_plan(task_id, plan, os.path.join(args.workdir, task_id, f"ctl-{cname}"))
            score, detail = verify.verify_run(art["contract"], art["trace"], art["baseline"], art["db"])
            control_scores[cname].append(score)
            flag = "OK" if score < 100.0 else "FAIL (control reached 100)"
            if score >= 100.0:
                all_ok = False
            lines.append(f"    control {cname:<15} score={score:6.2f}  {flag}")

    print("=" * 74)
    print("FieldServiceBench-10 qualification report")
    print("=" * 74)
    for ln in lines:
        print(ln)
    print("-" * 74)
    print("control mean scores (must all be < 100):")
    for cname in controls.CONTROL_NAMES:
        vals = control_scores[cname]
        print(f"  {cname:<15} mean={sum(vals)/len(vals):6.2f}  min={min(vals):6.2f}  max={max(vals):6.2f}")
    oracle_all = all("OK" in ln for ln in lines if ln.startswith("FSB"))
    print("-" * 74)
    print(f"RESULT: {'QUALIFIED' if all_ok else 'NOT QUALIFIED'} "
          f"(10/10 oracle strict=100 required; all controls < 100 required)")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
