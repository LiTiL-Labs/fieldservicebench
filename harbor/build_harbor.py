"""Generate Harbor-format task directories for two FieldServiceBench tasks.

Usage: python3 harbor/build_harbor.py
Writes harbor/task-fsb-01/ and harbor/task-fsb-05/ (self-contained).
Run a task with:  harbor run -p harbor/task-fsb-01 -a oracle
"""

import json
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tasks  # noqa: E402

ROOT = os.path.dirname(os.path.abspath(__file__))
PKG = ["schema.sql", "tasks.py", "seed.py", "server.py", "runner.py", "verify.py", "oracle.py"]
TASK_IDS = ["FSB-01", "FSB-05"]

TASK_TOML = """schema_version = "1.4"
artifacts = []

[task]
name = "fieldservicebench/{slug}"
version = "1.0.0"
description = "{desc}"
keywords = ["field-service", "sqlite", "tool-use", "deterministic-verifier"]
[[task.authors]]
name = "FieldServiceBench clean-room"

[metadata]

[verifier]
timeout_sec = 600.0
collect = []

[verifier.env]

[agent]
timeout_sec = 600.0

[environment]
network_mode = "public"
build_timeout_sec = 600.0
os = "linux"
mcp_servers = []

[environment.env]

[solution.env]
"""

DOCKERFILE = """FROM python:3.12-slim
WORKDIR /app
COPY app/ /app/
RUN python3 -c "import seed; seed.build('/tmp/probe.db')" && rm /tmp/probe.db
"""

SOLVE_SH = """#!/bin/bash
# Oracle solution: replay the reference plan through the real tool server.
# Artifacts land in /app/work for the verifier.
python3 /app/oracle.py --task {task_id} --workdir /app/work || true
"""

TEST_SH = """#!/bin/bash
# Deterministic verifier: trace + state + containment + answer -> reward.
mkdir -p /logs/verifier
python3 /app/verify.py \\
  --contract /app/work/contract.json \\
  --trace /app/work/trace.jsonl \\
  --baseline /app/work/baseline.db \\
  --db /app/work/world.db \\
  --out /logs/verifier/score.json > /logs/verifier/verify.log 2>&1 || true
if [ -f /logs/verifier/score.json ]; then
python3 - <<'EOF'
import json
d = json.load(open("/logs/verifier/score.json"))
reward = 1.0 if d.get("strict") else round(d.get("score", 0.0) / 100.0, 4)
open("/logs/verifier/reward.txt", "w").write(str(reward))
EOF
else
  echo "0.0" > /logs/verifier/reward.txt
fi
"""


def build(task_id):
    slug = task_id.lower()
    tdir = os.path.join(ROOT, f"task-{slug}")
    if os.path.exists(tdir):
        shutil.rmtree(tdir)
    os.makedirs(os.path.join(tdir, "environment", "app"))
    os.makedirs(os.path.join(tdir, "solution"))
    os.makedirs(os.path.join(tdir, "tests"))

    t = tasks.TASKS[task_id]
    desc = t["prompt"].split(".")[0].replace('"', "'")
    with open(os.path.join(tdir, "task.toml"), "w") as f:
        f.write(TASK_TOML.format(slug=slug, desc=desc))
    with open(os.path.join(tdir, "instruction.md"), "w") as f:
        f.write(t["prompt"] + "\n\nSubmit your answer with the submit_answer tool, "
                "field names exactly as requested. All monetary values in integer cents.\n")
    with open(os.path.join(tdir, "environment", "Dockerfile"), "w") as f:
        f.write(DOCKERFILE)
    for fn in PKG:
        shutil.copyfile(os.path.join(ROOT, "..", fn), os.path.join(tdir, "environment", "app", fn))
    with open(os.path.join(tdir, "solution", "solve.sh"), "w") as f:
        f.write(SOLVE_SH.format(task_id=task_id))
    with open(os.path.join(tdir, "tests", "test.sh"), "w") as f:
        f.write(TEST_SH)
    os.chmod(os.path.join(tdir, "solution", "solve.sh"), 0o755)
    os.chmod(os.path.join(tdir, "tests", "test.sh"), 0o755)
    print(f"built {tdir}")


if __name__ == "__main__":
    for tid in TASK_IDS:
        build(tid)
