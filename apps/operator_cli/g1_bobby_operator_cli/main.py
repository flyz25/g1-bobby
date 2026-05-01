from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

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
    parser.add_argument(
        "--telemetry-only",
        action="store_true",
        help="Connect read-only and listen without sending demo or script commands",
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Reconnect automatically after disconnect or connect failure",
    )
    parser.add_argument(
        "--reconnect-delay-s",
        type=float,
        default=1.0,
        help="Delay before retrying when --watch is enabled",
    )
    parser.add_argument("--raw", action="store_true", help="Print raw JSON events")
    return parser


async def receive_event(websocket, timeout_s: float) -> str:
    return await asyncio.wait_for(websocket.recv(), timeout=timeout_s)


def _format_unitree_suffix(event: dict[str, Any]) -> str:
    unitree_state = event.get("unitree_state")
    if not isinstance(unitree_state, dict):
        return ""
    sample_counts = unitree_state.get("sample_counts")
    if not isinstance(sample_counts, dict):
        return ""
    low_state = sample_counts.get("low_state")
    sport_mode_state = sample_counts.get("sport_mode_state")
    details: list[str] = []
    source = unitree_state.get("source")
    if isinstance(source, str):
        details.append(f"source={source}")
    stale = unitree_state.get("stale")
    if isinstance(stale, bool) and stale:
        details.append("stale=true")
    if isinstance(low_state, int | float):
        details.append(f"low={int(low_state)}")
    if isinstance(sport_mode_state, int | float):
        details.append(f"sport={int(sport_mode_state)}")
    status = unitree_state.get("status")
    if isinstance(status, str):
        details.insert(0, f"unitree={status}")
    return f" [{' '.join(details)}]" if details else ""


def _format_unitree_command_plan_suffix(event: dict[str, Any]) -> str:
    record = event.get("unitree_command_plan")
    if not isinstance(record, dict):
        return ""
    plan = record.get("plan")
    if not isinstance(plan, dict):
        return ""
    details: list[str] = []
    action = plan.get("action")
    if isinstance(action, str):
        details.append(f"action={action}")
    target = plan.get("unitree_target")
    if isinstance(target, str):
        details.append(f"target={target}")
    source = record.get("source")
    if isinstance(source, str):
        details.append(f"source={source}")
    stale = record.get("stale")
    if isinstance(stale, bool) and stale:
        details.append("stale=true")
    return f" [{' '.join(details)}]" if details else ""


def format_event(raw_text: str, raw: bool = False) -> str:
    if raw:
        return raw_text

    try:
        event = json.loads(raw_text)
    except json.JSONDecodeError:
        return raw_text
    if not isinstance(event, dict):
        return raw_text

    event_type = event.get("type")
    if event_type == "state":
        state = event.get("state", {})
        if isinstance(state, dict):
            return (
                "state "
                f"connected={state.get('connected')} "
                f"mode={state.get('mode')} "
                f"estop={state.get('estop_engaged')} "
                f"pose={state.get('pose_label')}"
                f"{_format_unitree_suffix(event)}"
            )
    if event_type == "telemetry":
        state = event.get("state", {})
        if isinstance(state, dict):
            return (
                "telemetry "
                f"accepted={event.get('accepted_commands')} "
                f"rejected={event.get('rejected_commands')} "
                f"mode={state.get('mode')} "
                f"pose={state.get('pose_label')}"
                f"{_format_unitree_suffix(event)}"
            )
    if event_type == "ack":
        return (
            "ack "
            f"seq={event.get('seq')} "
            f"command={event.get('command_type')} "
            f"message={event.get('message')}"
            f"{_format_unitree_command_plan_suffix(event)}"
        )
    if event_type == "reject":
        return (
            "reject "
            f"seq={event.get('seq')} "
            f"code={event.get('code')} "
            f"reason={event.get('reason')}"
        )
    return raw_text


def print_event(raw_text: str, raw: bool = False) -> None:
    print(format_event(raw_text, raw=raw))


def can_retry(exc: Exception) -> bool:
    return isinstance(exc, OSError | TimeoutError | websockets.WebSocketException)


def should_retry(args: argparse.Namespace, exc: Exception) -> bool:
    return args.watch and can_retry(exc)


def should_replay_messages(args: argparse.Namespace) -> bool:
    return not args.telemetry_only and args.script is None


def build_outbound_messages(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.telemetry_only:
        return []
    if args.script is not None:
        messages = load_jsonl_messages(args.script)
        if not args.keep_script_timestamps:
            messages = refresh_message_timestamps(messages)
        return messages
    return demo_messages(client_id=args.client_id)


def effective_listen_s(args: argparse.Namespace) -> float:
    if args.listen_s > 0:
        return args.listen_s
    if args.telemetry_only:
        return args.timeout_s
    return 0.0


async def run(args: argparse.Namespace) -> int:
    url = attach_token(args.url, args.token)
    outbound_messages = build_outbound_messages(args)
    replay_on_retry = should_replay_messages(args)

    while True:
        try:
            async with websockets.connect(url, open_timeout=args.timeout_s) as websocket:
                print_event(await receive_event(websocket, args.timeout_s), raw=args.raw)
                for message in outbound_messages:
                    await websocket.send(json.dumps(message, separators=(",", ":")))
                    print_event(await receive_event(websocket, args.timeout_s), raw=args.raw)
                    if args.delay_s > 0:
                        await asyncio.sleep(args.delay_s)

                listen_s = effective_listen_s(args)
                if listen_s > 0:
                    listen_until = asyncio.get_running_loop().time() + listen_s
                    while True:
                        timeout_s = listen_until - asyncio.get_running_loop().time()
                        if timeout_s <= 0:
                            break
                        try:
                            print_event(
                                await receive_event(websocket, min(timeout_s, args.timeout_s)),
                                raw=args.raw,
                            )
                        except TimeoutError:
                            break
            return 0
        except Exception as exc:
            if not should_retry(args, exc):
                raise
            print(
                f"operator cli reconnecting in {max(args.reconnect_delay_s, 0.1):.1f}s: {exc}",
                file=sys.stderr,
            )
            await asyncio.sleep(max(args.reconnect_delay_s, 0.1))
            if not replay_on_retry:
                outbound_messages = []


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
