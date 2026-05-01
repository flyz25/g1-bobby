from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import websockets

from .messages import (
    DEFAULT_OPERATOR_TOKEN,
    DEFAULT_WS_URL,
    attach_token,
    demo_messages,
    load_jsonl_messages,
    refresh_message_timestamps,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send operator commands to G1 Bobby.")
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="WebSocket URL without token")
    parser.add_argument("--token", default=DEFAULT_OPERATOR_TOKEN, help="Operator token")
    parser.add_argument("--client-id", default="operator-cli", help="Heartbeat client id")
    parser.add_argument("--script", type=Path, help="JSONL command script to send")
    parser.add_argument(
        "--keep-script-timestamps",
        action="store_true",
        help="Do not refresh script timestamps before sending",
    )
    parser.add_argument("--delay-s", type=float, default=0.05, help="Delay between commands")
    parser.add_argument("--listen-s", type=float, default=0.0, help="Listen for telemetry after send")
    parser.add_argument("--timeout-s", type=float, default=5.0, help="Connect/receive timeout")
    return parser


async def receive_event(websocket, timeout_s: float) -> str:
    return await asyncio.wait_for(websocket.recv(), timeout=timeout_s)


async def run(args: argparse.Namespace) -> int:
    url = attach_token(args.url, args.token)
    messages = (
        load_jsonl_messages(args.script)
        if args.script is not None
        else demo_messages(client_id=args.client_id)
    )
    if args.script is not None and not args.keep_script_timestamps:
        messages = refresh_message_timestamps(messages)

    async with websockets.connect(url, open_timeout=args.timeout_s) as websocket:
        print(await receive_event(websocket, args.timeout_s))
        for message in messages:
            await websocket.send(json.dumps(message, separators=(",", ":")))
            print(await receive_event(websocket, args.timeout_s))
            if args.delay_s > 0:
                await asyncio.sleep(args.delay_s)

        if args.listen_s > 0:
            listen_until = asyncio.get_running_loop().time() + args.listen_s
            while True:
                timeout_s = listen_until - asyncio.get_running_loop().time()
                if timeout_s <= 0:
                    break
                try:
                    print(await receive_event(websocket, min(timeout_s, args.timeout_s)))
                except TimeoutError:
                    break

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(run(args))
    except (OSError, TimeoutError, websockets.WebSocketException, ValueError) as exc:
        print(f"operator cli failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
