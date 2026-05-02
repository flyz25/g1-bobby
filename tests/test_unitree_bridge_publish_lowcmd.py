import json
import sys
from types import SimpleNamespace

import pytest

from g1_bobby_adapters.unitree_transport import UnitreeTransportConfigurationError
from g1_bobby_unitree_bridge.publish_lowcmd import HgLowCmdProbePublisher, list_lowcmd_templates, main


class _FakeMotorCmd:
    def __init__(self, mode: int, q: float, dq: float, tau: float, kp: float, kd: float, reserve: int) -> None:
        self.mode = mode
        self.q = q
        self.dq = dq
        self.tau = tau
        self.kp = kp
        self.kd = kd
        self.reserve = reserve


class _FakeLowCmd:
    def __init__(self, mode_pr: int, mode_machine: int, motor_cmd, reserve, crc: int) -> None:
        self.mode_pr = mode_pr
        self.mode_machine = mode_machine
        self.motor_cmd = list(motor_cmd)
        self.reserve = list(reserve)
        self.crc = crc


class _FakeCRC:
    def Crc(self, message) -> int:
        return 123456


class _FakeChannelPublisher:
    def __init__(self, topic: str, message_class, *, write_result=True) -> None:
        self.topic = topic
        self.message_class = message_class
        self.write_result = write_result
        self.initialized = False
        self.closed = False
        self.writes = []

    def Init(self) -> None:
        self.initialized = True

    def Write(self, sample, timeout: float = None):
        self.writes.append((sample, timeout))
        return self.write_result

    def Close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_lowcmd_probe_publisher_builds_neutral_frame(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_initialize(domain_id: int, interface: str) -> None:
        captured["domain_id"] = domain_id
        captured["interface"] = interface

    publisher = _FakeChannelPublisher("rt/lowcmd", _FakeLowCmd)
    monkeypatch.setitem(sys.modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "unitree_sdk2py.core.channel",
        SimpleNamespace(
            ChannelFactoryInitialize=fake_initialize,
            ChannelPublisher=lambda topic, message_class: publisher,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "unitree_sdk2py.idl.unitree_hg.msg.dds_",
        SimpleNamespace(LowCmd_=_FakeLowCmd, MotorCmd_=_FakeMotorCmd),
    )
    monkeypatch.setitem(sys.modules, "unitree_sdk2py.utils.crc", SimpleNamespace(CRC=lambda: _FakeCRC()))

    probe = HgLowCmdProbePublisher(network_interface="lo", sdk_module="unitree_sdk_for_test")
    await probe.connect()
    try:
        result = await probe.publish_neutral_frame(mode_pr=2, mode_machine=7, motor_mode=9)
    finally:
        await probe.disconnect()

    assert captured == {"domain_id": 0, "interface": "lo"}
    assert publisher.initialized is True
    assert publisher.closed is True
    assert result["topic"] == "rt/lowcmd"
    assert result["mode_pr"] == 2
    assert result["mode_machine"] == 7
    assert result["motor_count"] == 35
    assert result["motor_mode"] == 9
    assert result["crc"] == 123456
    assert result["write_result"] is True
    message, timeout = publisher.writes[0]
    assert timeout == 0.1
    assert message.crc == 123456
    assert len(message.motor_cmd) == 35
    assert all(motor.mode == 9 for motor in message.motor_cmd)


@pytest.mark.asyncio
async def test_lowcmd_probe_publisher_requires_network_interface() -> None:
    probe = HgLowCmdProbePublisher(network_interface=None)
    with pytest.raises(
        UnitreeTransportConfigurationError,
        match="requires a network interface",
    ):
        await probe.connect()


def test_publish_lowcmd_cli_emits_json(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def fake_initialize(domain_id: int, interface: str) -> None:
        captured["domain_id"] = domain_id
        captured["interface"] = interface

    publisher = _FakeChannelPublisher("rt/lowcmd", _FakeLowCmd)
    monkeypatch.setitem(sys.modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "unitree_sdk2py.core.channel",
        SimpleNamespace(
            ChannelFactoryInitialize=fake_initialize,
            ChannelPublisher=lambda topic, message_class: publisher,
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "unitree_sdk2py.idl.unitree_hg.msg.dds_",
        SimpleNamespace(LowCmd_=_FakeLowCmd, MotorCmd_=_FakeMotorCmd),
    )
    monkeypatch.setitem(sys.modules, "unitree_sdk2py.utils.crc", SimpleNamespace(CRC=lambda: _FakeCRC()))

    exit_code = main(
        [
            "--network-interface",
            "lo",
            "--sdk-module",
            "unitree_sdk_for_test",
            "--count",
            "2",
            "--period-s",
            "0",
            "--mode-pr",
            "1",
            "--mode-machine",
            "5",
            "--motor-mode",
            "3",
        ]
    )

    assert exit_code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ok"
    assert payload["count"] == 2
    assert payload["template"] == "neutral_probe"
    assert payload["write_success"] is True
    assert len(payload["frames"]) == 2
    assert payload["frames"][0]["mode_pr"] == 1
    assert payload["frames"][0]["mode_machine"] == 5
    assert payload["frames"][0]["motor_mode"] == 3
    assert captured == {"domain_id": 0, "interface": "lo"}


def test_publish_lowcmd_cli_rejects_invalid_count(capsys) -> None:
    exit_code = main(["--network-interface", "lo", "--count", "0"])

    assert exit_code == 2
    assert "--count must be >= 1" in capsys.readouterr().err


def test_publish_lowcmd_cli_can_require_successful_write(capsys, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "unitree_sdk_for_test", SimpleNamespace())
    monkeypatch.setitem(
        sys.modules,
        "unitree_sdk2py.core.channel",
        SimpleNamespace(
            ChannelFactoryInitialize=lambda domain_id, interface: None,
            ChannelPublisher=lambda topic, message_class: _FakeChannelPublisher(
                topic,
                message_class,
                write_result=False,
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "unitree_sdk2py.idl.unitree_hg.msg.dds_",
        SimpleNamespace(LowCmd_=_FakeLowCmd, MotorCmd_=_FakeMotorCmd),
    )
    monkeypatch.setitem(sys.modules, "unitree_sdk2py.utils.crc", SimpleNamespace(CRC=lambda: _FakeCRC()))

    exit_code = main(
        [
            "--network-interface",
            "lo",
            "--sdk-module",
            "unitree_sdk_for_test",
            "--require-write",
        ]
    )

    assert exit_code == 2
    assert "write was rejected on topic rt/lowcmd" in capsys.readouterr().err


def test_list_lowcmd_templates_exposes_neutral_probe() -> None:
    templates = list_lowcmd_templates()

    assert templates == [
        {
            "name": "neutral_probe",
            "description": "Zeroed HG lowcmd frame for DDS write-acceptance diagnostics only.",
            "defaults": {
                "topic": "rt/lowcmd",
                "mode_pr": 0,
                "mode_machine": 0,
                "motor_mode": 0,
                "motor_count": 35,
            },
        }
    ]
