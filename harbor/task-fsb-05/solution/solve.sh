#!/bin/bash
# Oracle solution: replay the reference plan through the real tool server.
# Artifacts land in /app/work for the verifier.
python3 /app/oracle.py --task FSB-05 --workdir /app/work || true
