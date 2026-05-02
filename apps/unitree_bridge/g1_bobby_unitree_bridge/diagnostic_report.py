from __future__ import annotations

from typing import Any, Mapping

from g1_bobby_adapters import UnitreeAdapterConfig, describe_unitree_transport_capability

from .probe import build_probe_status, readiness_errors
from .publish_lowcmd import HgLowCmdProbePublisher, list_lowcmd_templates


async def build_unitree_diagnostic_report(
    *,
    transport: str | None = None,
    network_interface: str | None = None,
    sdk_module: str | None = None,
    probe_lowcmd_write: bool = False,
    env: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    checks = build_probe_status(
        env,
        network_interface=network_interface,
        sdk_module=sdk_module,
    )
    payload: dict[str, Any] = {
        "checks": checks,
        "errors": readiness_errors(checks),
        "lowcmd_templates": list_lowcmd_templates(),
    }

    resolved_transport = transport
    if resolved_transport:
        capability = describe_unitree_transport_capability(
            UnitreeAdapterConfig(
                network_interface=str(checks["dds_interface"]),
                sdk_module=str(checks["unitree_sdk_module"]),
                enable_motor_commands=bool(checks["motor_commands_enabled"]),
                command_transport=resolved_transport,
            ),
            env=env,
        )
        payload["transport_capability"] = capability.model_dump(mode="json")

    if probe_lowcmd_write:
        try:
            publisher = HgLowCmdProbePublisher(
                network_interface=str(checks["dds_interface"]),
                sdk_module=str(checks["unitree_sdk_module"]),
            )
            await publisher.connect()
            try:
                result = await publisher.publish_neutral_frame()
            finally:
                await publisher.disconnect()
        except Exception as exc:
            payload["lowcmd_write_probe"] = {
                "status": "error",
                "topic": "rt/lowcmd",
                "detail": str(exc),
            }
        else:
            payload["lowcmd_write_probe"] = {
                **result,
                "status": "accepted" if result.get("write_result") is not False else "rejected",
            }

    report_status = "ready" if not payload["errors"] else "not_ready"
    capability_payload = payload.get("transport_capability")
    if isinstance(capability_payload, dict) and not capability_payload.get("ready", False):
        report_status = "blocked" if capability_payload.get("environment_ready", False) else "not_ready"
    lowcmd_probe = payload.get("lowcmd_write_probe")
    if isinstance(lowcmd_probe, dict) and lowcmd_probe.get("status") in {"rejected", "error"}:
        report_status = "blocked" if report_status == "ready" else report_status
    payload["status"] = report_status
    return payload
