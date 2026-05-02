from __future__ import annotations

import json
import shutil
import subprocess
from typing import Any, Mapping

from .diagnostic_report import build_unitree_diagnostic_report
from .source_trace import build_unitree_source_trace


KNOWN_SURFACES = (
    {"topic": "rt/lowstate", "role": "simulator_state", "kind": "dds"},
    {"topic": "rt/sportmodestate", "role": "simulator_state", "kind": "dds"},
    {"topic": "rt/lowcmd", "role": "low_level_command", "kind": "dds"},
    {"topic": "/api/sport/request", "role": "high_level_command", "kind": "ros2"},
    {"topic": "/api/sport/response", "role": "high_level_response", "kind": "ros2"},
)


def _ros2_topic_list() -> list[str] | None:
    if shutil.which("ros2") is None:
        return None
    try:
        result = subprocess.run(
            ["ros2", "topic", "list"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


async def build_dds_introspection_report(
    *,
    network_interface: str | None = None,
    sdk_module: str | None = None,
    transport: str | None = None,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    diagnostic = await build_unitree_diagnostic_report(
        transport=transport,
        network_interface=network_interface,
        sdk_module=sdk_module,
        probe_lowcmd_write=True,
        env=env,
    )
    ros2_topics = _ros2_topic_list()
    lowcmd_probe = diagnostic.get("lowcmd_write_probe") or {}
    surfaces = []
    for surface in KNOWN_SURFACES:
        status = "unknown"
        detail = None
        if surface["topic"] == "rt/lowcmd":
            status = str(lowcmd_probe.get("status", "unknown"))
            detail = lowcmd_probe.get("detail")
        elif surface["kind"] == "dds":
            status = "not_queried"
            detail = "raw DDS topic is not enumerable via ros2 topic list"
        elif ros2_topics is not None:
            status = "present" if surface["topic"] in ros2_topics else "absent"
        surfaces.append(
            {
                **surface,
                "status": status,
                "detail": detail,
            }
        )
    return {
        "status": diagnostic["status"],
        "surfaces": surfaces,
        "ros2_topics_observed": ros2_topics,
        "source_trace": build_unitree_source_trace(),
    }


def format_dds_introspection_text(payload: Mapping[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True)
