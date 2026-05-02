import sys
from types import SimpleNamespace

import pytest

from g1_bobby_unitree_bridge.main import main
from g1_bobby_unitree_bridge.probe import build_probe_status, is_truthy, readiness_errors


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_is_truthy_accepts_common_enabled_values(value: str) -> None:
    assert is_truthy(value)


@pytest.mark.parametrize("value", [None, "", "0", "false", "off"])
def test_is_truthy_rejects_disabled_values(value: str | None) -> None:
    assert not is_truthy(value)


def test_build_probe_status_uses_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "rclpy", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace())

    status = build_probe_status(
        {
            "ROS_DISTRO": "humble",
            "RMW_IMPLEMENTATION": "rmw_cyclonedds_cpp",
            "CYCLONEDDS_URI": "file:///tmp/cyclonedds.xml",
            "G1_BOBBY_API_URL": "http://api:8010",
            "G1_BOBBY_UNITREE_NETWORK_INTERFACE": "eth0",
            "G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS": "false",
            "G1_BOBBY_UNITREE_SDK_MODULE": "unitree_sdk_for_test",
        }
    )

    assert status["ros_distro"] == "humble"
    assert status["rmw_implementation"] == "rmw_cyclonedds_cpp"
    assert status["dds_interface"] == "eth0"
    assert status["g1_bobby_api_url"] == "http://api:8010"
    assert status["unitree_sdk_available"] is True
    assert status["rclpy_available"] is True
    assert status["unitree_api_request_available"] is True
    assert status["motor_commands_enabled"] is False
    assert status["robot_network_selected"] is True


def test_readiness_errors_reports_local_unready_environment() -> None:
    status = {
        "ros_distro": None,
        "rmw_implementation": None,
        "rclpy_available": False,
        "unitree_api_request_available": False,
        "unitree_sdk_available": False,
        "unitree_sdk_module": "unitree_sdk2py",
        "robot_network_selected": False,
    }

    errors = readiness_errors(status)

    assert "ROS_DISTRO is not humble" in errors
    assert "RMW_IMPLEMENTATION is not rmw_cyclonedds_cpp" in errors
    assert "rclpy is not importable" in errors
    assert "unitree_api.msg is not importable" in errors
    assert "unitree_sdk2py is not importable" in errors
    assert "G1_BOBBY_UNITREE_NETWORK_INTERFACE is still loopback/local" in errors


def test_probe_main_can_render_transport_capability(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.setitem(sys.modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "rclpy", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace())
    monkeypatch.setenv("ROS_DISTRO", "humble")
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
    monkeypatch.setenv("G1_BOBBY_UNITREE_NETWORK_INTERFACE", "eth0")
    monkeypatch.setenv("G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS", "true")
    monkeypatch.setenv("G1_BOBBY_UNITREE_SDK_MODULE", "unitree_sdk_for_test")

    exit_code = main(["--transport", "ros2_real"])

    assert exit_code == 0
    captured = capsys.readouterr()
    assert '"transport": "ros2_real"' in captured.out
    assert '"environment_ready": true' in captured.out
    assert '"binding_implemented": true' in captured.out
    assert '"transport_status": "ready"' in captured.out


def test_probe_main_require_ready_succeeds_for_ready_real_transport(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "rclpy", SimpleNamespace())
    monkeypatch.setitem(sys.modules, "unitree_api.msg", SimpleNamespace())
    monkeypatch.setenv("ROS_DISTRO", "humble")
    monkeypatch.setenv("RMW_IMPLEMENTATION", "rmw_cyclonedds_cpp")
    monkeypatch.setenv("G1_BOBBY_UNITREE_NETWORK_INTERFACE", "eth0")
    monkeypatch.setenv("G1_BOBBY_UNITREE_ENABLE_MOTOR_COMMANDS", "true")
    monkeypatch.setenv("G1_BOBBY_UNITREE_SDK_MODULE", "unitree_sdk_for_test")

    assert main(["--transport", "ros2_real", "--require-ready"]) == 0
