#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."

if [ ! -x .venv/bin/uvicorn ]; then
  echo "missing .venv/bin/uvicorn; install local dev environment first" >&2
  exit 2
fi

exec .venv/bin/uvicorn g1_bobby_api.app:app --host 127.0.0.1 --port 8010
