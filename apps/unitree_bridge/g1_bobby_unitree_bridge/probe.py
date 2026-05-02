from __future__ import annotations

from importlib.util import find_spec
from os import environ
import sys
from typing import Mapping


def is_truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def module_available(module_name: str) -> bool:
    if module_name in sys.modules:
        return True
    try:
        return find_spec(module_name) is not None
    except ModuleNotFoundError:
        return False


def build_probe_status(
    env: Mapping[str, str] | None = None,
    *,
    network_interface: str | None = None,
    sdk_module: str | None = None,
) -> dict[str, object]:
    source_env = env or environ
    resolved_sdk_module = sdk_module or source_env.get("G1_BOBBY_UNITREE_SDK_MODULE", "unitree_sdk2py")
    dds_interface = (
        network_interface
        or source_env.get("G1_BOBBY_UNITREE_NETWORK_INTERFACE")
        or source_env.get("G1_BOBBY_UNITREE_DDS_INTERFACE", "lo")
    )

    return {
        "ros_distro": source_env.get("ROS_DISTRO"),
        "rmw_implementation": source_env.get("RMW_IMPLEMENTATION"),
        "cyclonedds_uri": source_env.get("CYCLONEDDS_URI"),
        "dds_interface": dds_interface,
        "g1_bobby_api_url": source_env.get("G1_BOBBY_API_URL", "http://127.0.0.1:8010"),
        "unitree_sdk_module": resolved_sdk_module,
        "unitree_sdk_available": module_available(resolved_sdk_module),
        "rclpy_available": module_available("rclpy"),
        "unitree_api_request_available": module_available("unitree_api.msg"),
        "unitree_hg_lowcmd_available": module_available("unitree_sdk2py.idl.unitree_hg.msg.dds_"),
        "unitree_crc_available": module_available("unitree_sdk2py.utils.crc"),
        "motor_commands_enabled": is_truthy(
            source_env.get("G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS")
        ),
        "robot_network_selected": dds_interface not in {"", "lo"},
    }


def readiness_errors(status: Mapping[str, object]) -> list[str]:
    errors: list[str] = []
    if status.get("ros_distro") != "humble":
        errors.append("ROS_DISTRO is not humble")
    if status.get("rmw_implementation") != "rmw_cyclonedds_cpp":
        errors.append("RMW_IMPLEMENTATION is not rmw_cyclonedds_cpp")
    if not status.get("rclpy_available"):
        errors.append("rclpy is not importable")
    if not status.get("unitree_api_request_available"):
        errors.append("unitree_api.msg is not importable")
    if not status.get("unitree_sdk_available"):
        errors.append(f"{status.get('unitree_sdk_module')} is not importable")
    if not status.get("unitree_hg_lowcmd_available"):
        errors.append("unitree_sdk2py.idl.unitree_hg.msg.dds_ is not importable")
    if not status.get("unitree_crc_available"):
        errors.append("unitree_sdk2py.utils.crc is not importable")
    if not status.get("robot_network_selected"):
        errors.append("G1_BOBBY_UNITREE_NETWORK_INTERFACE is still loopback/local")
    return errors
