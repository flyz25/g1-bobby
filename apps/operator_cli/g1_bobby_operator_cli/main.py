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
    attach_after_id,
    attach_token,
    default_audit_url,
    demo_messages,
    load_jsonl_messages,
    refresh_message_timestamps,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Send operator commands to G1 Bobby.")
    parser.add_argument("--url", default=DEFAULT_WS_URL, help="WebSocket URL without token")
    parser.add_argument("--audit-url", help="Audit WebSocket URL without token")
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
        "--audit-stream",
        action="store_true",
        help="Connect to the read-only command-plan audit stream",
    )
    parser.add_argument(
        "--after-id",
        type=int,
        default=0,
        help="Replay only audit events with event_id greater than this value",
    )
    parser.add_argument(
        "--resume-file",
        type=Path,
        help="Persist the highest seen audit event_id and reuse it on reconnect",
    )
    parser.add_argument(
        "--resume-reset",
        action="store_true",
        help="Ignore any saved resume-file cursor and start audit replay from --after-id",
    )
    resume_command_group = parser.add_mutually_exclusive_group()
    resume_command_group.add_argument(
        "--resume-status",
        action="store_true",
        help="Print the effective audit resume cursor and exit",
    )
    resume_command_group.add_argument(
        "--resume-clear",
        action="store_true",
        help="Reset the resume-file cursor to zero and exit",
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


def _truncate_detail(value: str, *, limit: int = 48) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


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
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"id={int(event_id)}")
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


def _format_unitree_execution_plan_suffix(event: dict[str, Any]) -> str:
    record = event.get("unitree_execution_plan")
    if not isinstance(record, dict):
        return ""
    execution_plan = record.get("execution_plan")
    if not isinstance(execution_plan, dict):
        return ""
    details: list[str] = []
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"exec_id={int(event_id)}")
    transport = execution_plan.get("transport")
    if isinstance(transport, str):
        details.append(f"transport={transport}")
    target = execution_plan.get("target")
    if isinstance(target, str):
        details.append(f"exec_target={target}")
    return f" [{' '.join(details)}]" if details else ""


def _format_unitree_execution_result_suffix(event: dict[str, Any]) -> str:
    record = event.get("unitree_execution_result")
    if not isinstance(record, dict):
        return ""
    execution_result = record.get("execution_result")
    if not isinstance(execution_result, dict):
        return ""
    details: list[str] = []
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"result_id={int(event_id)}")
    status = execution_result.get("status")
    if isinstance(status, str):
        details.append(f"status={status}")
    transport = execution_result.get("transport")
    if isinstance(transport, str):
        details.append(f"transport={transport}")
    target = execution_result.get("target")
    if isinstance(target, str):
        details.append(f"target={target}")
    detail = execution_result.get("detail")
    if isinstance(detail, str) and detail:
        details.append(f"detail={_truncate_detail(detail)}")
    return f" [{' '.join(details)}]" if details else ""


def _format_unitree_command_plan_record(record: dict[str, Any]) -> str:
    plan = record.get("plan")
    if not isinstance(plan, dict):
        return "command-plan"
    details: list[str] = []
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"id={int(event_id)}")
    details.extend([f"seq={plan.get('seq')}", f"action={plan.get('action')}"])
    target = plan.get("unitree_target")
    if isinstance(target, str):
        details.append(f"target={target}")
    source = record.get("source")
    if isinstance(source, str):
        details.append(f"source={source}")
    stale = record.get("stale")
    if isinstance(stale, bool) and stale:
        details.append("stale=true")
    return "command-plan " + " ".join(details)


def _format_rejected_command_record(record: dict[str, Any]) -> str:
    rejection = record.get("rejection")
    if not isinstance(rejection, dict):
        return "rejected-command"
    details: list[str] = []
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"id={int(event_id)}")
    details.extend([f"seq={rejection.get('seq')}", f"code={rejection.get('code')}"])
    command_type = record.get("command_type")
    if isinstance(command_type, str):
        details.append(f"command={command_type}")
    source = record.get("source")
    if isinstance(source, str):
        details.append(f"source={source}")
    stale = record.get("stale")
    if isinstance(stale, bool) and stale:
        details.append("stale=true")
    reason = rejection.get("reason")
    if isinstance(reason, str):
        details.append(f"reason={reason}")
    return "rejected-command " + " ".join(details)


def _format_unitree_execution_plan_record(record: dict[str, Any]) -> str:
    execution_plan = record.get("execution_plan")
    if not isinstance(execution_plan, dict):
        return "execution-plan"
    details: list[str] = []
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"id={int(event_id)}")
    transport = execution_plan.get("transport")
    if isinstance(transport, str):
        details.append(f"transport={transport}")
    command_type = execution_plan.get("command_type")
    if isinstance(command_type, str):
        details.append(f"command={command_type}")
    target = execution_plan.get("target")
    if isinstance(target, str):
        details.append(f"target={target}")
    source = record.get("source")
    if isinstance(source, str):
        details.append(f"source={source}")
    stale = record.get("stale")
    if isinstance(stale, bool) and stale:
        details.append("stale=true")
    return "execution-plan " + " ".join(details)


def _format_unitree_execution_result_record(record: dict[str, Any]) -> str:
    execution_result = record.get("execution_result")
    if not isinstance(execution_result, dict):
        return "execution-result"
    details: list[str] = []
    event_id = record.get("event_id")
    if isinstance(event_id, int | float):
        details.append(f"id={int(event_id)}")
    transport = execution_result.get("transport")
    if isinstance(transport, str):
        details.append(f"transport={transport}")
    command_type = execution_result.get("command_type")
    if isinstance(command_type, str):
        details.append(f"command={command_type}")
    status = execution_result.get("status")
    if isinstance(status, str):
        details.append(f"status={status}")
    target = execution_result.get("target")
    if isinstance(target, str):
        details.append(f"target={target}")
    source = record.get("source")
    if isinstance(source, str):
        details.append(f"source={source}")
    stale = record.get("stale")
    if isinstance(stale, bool) and stale:
        details.append("stale=true")
    return "execution-result " + " ".join(details)


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
            f"{_format_unitree_execution_plan_suffix(event)}"
            f"{_format_unitree_execution_result_suffix(event)}"
        )
    if event_type == "command_plan":
        record = event.get("unitree_command_plan")
        if isinstance(record, dict):
            return _format_unitree_command_plan_record(record)
    if event_type == "rejected_command":
        record = event.get("rejected_command")
        if isinstance(record, dict):
            return _format_rejected_command_record(record)
    if event_type == "execution_plan":
        record = event.get("unitree_execution_plan")
        if isinstance(record, dict):
            return _format_unitree_execution_plan_record(record)
    if event_type == "execution_result":
        record = event.get("unitree_execution_result")
        if isinstance(record, dict):
            return _format_unitree_execution_result_record(record)
    if event_type == "reject":
        return (
            "reject "
            f"seq={event.get('seq')} "
            f"code={event.get('code')} "
            f"reason={event.get('reason')}"
            f"{_format_unitree_execution_result_suffix(event)}"
        )
    return raw_text


def print_event(raw_text: str, raw: bool = False) -> None:
    print(format_event(raw_text, raw=raw))


def can_retry(exc: Exception) -> bool:
    return isinstance(exc, OSError | TimeoutError | websockets.WebSocketException)


def should_retry(args: argparse.Namespace, exc: Exception) -> bool:
    return args.watch and can_retry(exc)


def should_replay_messages(args: argparse.Namespace) -> bool:
    return not args.telemetry_only and not args.audit_stream and args.script is None


def build_outbound_messages(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.telemetry_only or args.audit_stream:
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
    if args.telemetry_only or args.audit_stream:
        return args.timeout_s
    return 0.0


def resolve_ws_url(args: argparse.Namespace) -> str:
    base_url = args.audit_url or default_audit_url(args.url) if args.audit_stream else args.url
    if args.audit_stream:
        after_id = current_after_id(args)
        if after_id > 0:
            return attach_after_id(base_url, after_id)
    return base_url


def load_resume_after_id(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0
    value = payload.get("after_id", 0)
    if not isinstance(value, int):
        return 0
    return max(value, 0)


def initialize_resume_after_id(args: argparse.Namespace) -> int:
    if args.resume_reset:
        if args.resume_file is not None:
            persist_resume_after_id(args.resume_file, max(args.after_id, 0))
        return max(args.after_id, 0)
    return load_resume_after_id(args.resume_file)


def handle_resume_file_command(args: argparse.Namespace) -> int | None:
    if args.resume_clear:
        if args.resume_file is None:
            print("operator cli failed: --resume-clear requires --resume-file", file=sys.stderr)
            return 1
        persist_resume_after_id(args.resume_file, 0)
        print(json.dumps({"resume_file": str(args.resume_file) if args.resume_file else None, "after_id": 0}))
        return 0
    if args.resume_status:
        effective_after_id = initialize_resume_after_id(args)
        print(
            json.dumps(
                {
                    "resume_file": str(args.resume_file) if args.resume_file else None,
                    "after_id": effective_after_id,
                    "after_id_arg": max(args.after_id, 0),
                }
            )
        )
        return 0
    return None


def persist_resume_after_id(path: Path | None, after_id: int) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"after_id": max(after_id, 0)}) + "\n", encoding="utf-8")


def current_after_id(args: argparse.Namespace) -> int:
    return max(getattr(args, "_resume_after_id", 0), max(args.after_id, 0))


def extract_event_id(raw_text: str) -> int | None:
    try:
        event = json.loads(raw_text)
    except json.JSONDecodeError:
        return None
    if not isinstance(event, dict):
        return None
    event_type = event.get("type")
    if event_type == "command_plan":
        record = event.get("unitree_command_plan")
    elif event_type == "execution_plan":
        record = event.get("unitree_execution_plan")
    elif event_type == "execution_result":
        record = event.get("unitree_execution_result")
    elif event_type == "rejected_command":
        record = event.get("rejected_command")
    else:
        return None
    if not isinstance(record, dict):
        return None
    event_id = record.get("event_id")
    if not isinstance(event_id, int | float):
        return None
    return int(event_id)


def update_resume_checkpoint(args: argparse.Namespace, raw_text: str) -> None:
    event_id = extract_event_id(raw_text)
    if event_id is None:
        return
    if event_id > getattr(args, "_resume_after_id", 0):
        args._resume_after_id = event_id
        persist_resume_after_id(args.resume_file, event_id)


async def run(args: argparse.Namespace) -> int:
    args._resume_after_id = initialize_resume_after_id(args)
    outbound_messages = build_outbound_messages(args)
    replay_on_retry = should_replay_messages(args)

    while True:
        try:
            url = attach_token(resolve_ws_url(args), args.token)
            if args.audit_stream:
                print(
                    f"operator cli audit cursor after_id={current_after_id(args)}",
                    file=sys.stderr,
                )
            async with websockets.connect(url, open_timeout=args.timeout_s) as websocket:
                first_event = await receive_event(websocket, args.timeout_s)
                update_resume_checkpoint(args, first_event)
                print_event(first_event, raw=args.raw)
                for message in outbound_messages:
                    await websocket.send(json.dumps(message, separators=(",", ":")))
                    event = await receive_event(websocket, args.timeout_s)
                    update_resume_checkpoint(args, event)
                    print_event(event, raw=args.raw)
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
                            event = await receive_event(websocket, min(timeout_s, args.timeout_s))
                            update_resume_checkpoint(args, event)
                            print_event(event, raw=args.raw)
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
    early_exit = handle_resume_file_command(args)
    if early_exit is not None:
        return early_exit
    try:
        return asyncio.run(run(args))
    except (OSError, TimeoutError, websockets.WebSocketException, ValueError) as exc:
        print(f"operator cli failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
