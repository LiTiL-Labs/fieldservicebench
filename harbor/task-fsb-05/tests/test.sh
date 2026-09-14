#!/bin/bash
# Deterministic verifier: trace + state + containment + answer -> reward.
mkdir -p /logs/verifier
python3 /app/verify.py \
  --contract /app/work/contract.json \
  --trace /app/work/trace.jsonl \
  --baseline /app/work/baseline.db \
  --db /app/work/world.db \
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
