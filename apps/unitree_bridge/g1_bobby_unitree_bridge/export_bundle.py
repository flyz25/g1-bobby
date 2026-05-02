from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any, Sequence
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


def _fetch_json(url: str) -> Any:
    with urlopen(url, timeout=5.0) as response:
        return json.loads(response.read().decode("utf-8"))


async def build_export_bundle(api_url: str) -> dict[str, Any]:
    base = api_url.rstrip("/")
    return {
        "api_url": base,
        "runtime": _fetch_json(f"{base}/runtime"),
        "state": _fetch_json(f"{base}/state"),
        "diagnostic_report": _fetch_json(f"{base}/unitree/diagnostic-report"),
        "sim_trace": _fetch_json(f"{base}/unitree/sim-trace"),
        "lowcmd_experiments": _fetch_json(f"{base}/unitree/lowcmd-experiments"),
        "command_plans": _fetch_json(f"{base}/unitree/command-plans"),
        "execution_plans": _fetch_json(f"{base}/unitree/execution-plans"),
        "execution_results": _fetch_json(f"{base}/unitree/execution-results"),
        "rejected_commands": _fetch_json(f"{base}/operator/rejections"),
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Export a consolidated G1 Bobby diagnostic bundle from the API.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8010", help="API base URL.")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        payload = asyncio.run(build_export_bundle(args.api_url))
    except (HTTPError, URLError, json.JSONDecodeError, TimeoutError, OSError) as exc:
        print(f"unitree export bundle failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
