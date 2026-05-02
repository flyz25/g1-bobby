#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."

.venv/bin/python -m g1_bobby_unitree_bridge.export_bundle --api-url "${G1_BOBBY_API_URL:-http://127.0.0.1:8010}"
