"""Oracle: replay a task's reference plan through the real tool server.

Usage: python3 oracle.py --task FSB-01 --workdir runs/oracle-FSB-01
Prints the verifier score; exits non-zero unless the run is a strict pass.
"""

import argparse
import json
import sys

import runner
import tasks
import verify


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=tasks.TASK_IDS)
    ap.add_argument("--workdir", required=True)
    args = ap.parse_args()

    plan = tasks.TASKS[args.task]["plan"]
    art = runner.run_plan(args.task, plan, args.workdir)
    score, detail = verify.verify_run(art["contract"], art["trace"], art["baseline"], art["db"])
    with open(f"{args.workdir}/score.json", "w", encoding="utf-8") as f:
        json.dump({"score": score, "detail": detail}, f, indent=2, sort_keys=True)
    print(f"{args.task}: score={score:.4f} strict={'PASS' if score == 100.0 else 'FAIL'}")
    for name, (pts, frac) in sorted(detail["milestones"].items()):
        print(f"  {name:<14} {pts:6.2f}  (fraction {frac:.3f})")
    sys.exit(0 if score == 100.0 else 1)


if __name__ == "__main__":
    main()
