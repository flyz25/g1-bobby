from types import SimpleNamespace

from g1_bobby_unitree_bridge.listener import (
    UnitreeStateCollector,
    build_api_ingest_url,
    config_from_args,
    post_snapshot_to_api,
    sequence_to_floats,
    summarize_low_state,
    summarize_sport_mode_state,
)


def test_config_from_args_uses_defaults() -> None:
    config = config_from_args([], env={})

    assert config.domain_id == 1
    assert config.interface == "lo"
    assert config.robot == "g1"
    assert config.duration_s is None
    assert config.sample_interval_s == 1.0
    assert config.max_motors == 6
    assert config.require_samples is False
    assert config.api_url is None
    assert config.api_token == "dev-operator-token"


def test_config_from_args_prefers_environment() -> None:
    config = config_from_args(
        [],
        env={
            "G1_BOBBY_UNITREE_DDS_DOMAIN_ID": "3",
            "G1_BOBBY_UNITREE_DDS_INTERFACE": "eth0",
            "G1_BOBBY_UNITREE_SIM_ROBOT": "go2",
            "G1_BOBBY_UNITREE_LISTEN_DURATION_S": "5",
            "G1_BOBBY_UNITREE_LISTEN_SAMPLE_INTERVAL_S": "0.25",
            "G1_BOBBY_UNITREE_LISTEN_MAX_MOTORS": "2",
            "G1_BOBBY_UNITREE_LISTEN_REQUIRE_SAMPLES": "true",
            "G1_BOBBY_API_URL": "http://api:8010",
            "G1_BOBBY_OPERATOR_TOKEN": "secret",
        },
    )

    assert config.domain_id == 3
    assert config.interface == "eth0"
    assert config.robot == "go2"
    assert config.duration_s == 5
    assert config.sample_interval_s == 0.25
    assert config.max_motors == 2
    assert config.require_samples is True
    assert config.api_url == "http://api:8010"
    assert config.api_token == "secret"


def test_sequence_to_floats_limits_values() -> None:
    assert sequence_to_floats([1, "2.5", 3], 2) == [1.0, 2.5]


def test_summarize_low_state_limits_motor_detail() -> None:
    msg = SimpleNamespace(
        tick=42,
        mode_pr=1,
        mode_machine=2,
        imu_state=SimpleNamespace(
            quaternion=[1, 0, 0, 0],
            rpy=[0.1, 0.2, 0.3],
            gyroscope=[0.4, 0.5, 0.6],
            accelerometer=[0.7, 0.8, 0.9],
            temperature=33,
        ),
        motor_state=[
            SimpleNamespace(mode=1, q=0.1, dq=0.2, tau_est=0.3, temperature=40),
            SimpleNamespace(mode=1, q=1.1, dq=1.2, tau_est=1.3, temperature=41),
        ],
    )

    payload = summarize_low_state(msg, max_motors=1)

    assert payload["tick"] == 42
    assert payload["motor_count"] == 2
    assert payload["imu"] == {
        "quaternion": [1.0, 0.0, 0.0, 0.0],
        "rpy": [0.1, 0.2, 0.3],
        "gyroscope": [0.4, 0.5, 0.6],
        "accelerometer": [0.7, 0.8, 0.9],
        "temperature": 33,
    }
    assert payload["motors"] == [
        {"mode": 1, "q": 0.1, "dq": 0.2, "tau_est": 0.3, "temperature": 40}
    ]


def test_summarize_sport_mode_state_extracts_pose_fields() -> None:
    msg = SimpleNamespace(
        mode=3,
        position=[1, 2, 3],
        velocity=[0.1, 0.2, 0.3],
        yaw_speed=0.4,
        body_height=0.5,
    )

    assert summarize_sport_mode_state(msg) == {
        "mode": 3,
        "position": [1.0, 2.0, 3.0],
        "velocity": [0.1, 0.2, 0.3],
        "yaw_speed": 0.4,
        "body_height": 0.5,
    }


def test_state_collector_snapshot_reports_samples() -> None:
    collector = UnitreeStateCollector(domain_id=1, interface="lo", robot="g1", max_motors=0)
    collector.handle_sport_state(
        SimpleNamespace(mode=1, position=[0, 0, 1], velocity=[0, 0, 0], yaw_speed=0)
    )

    snapshot = collector.snapshot()

    assert snapshot["status"] == "receiving"
    assert snapshot["dds"] == {
        "domain_id": 1,
        "interface": "lo",
        "robot": "g1",
        "topics": {
            "low_state": "rt/lowstate",
            "sport_mode_state": "rt/sportmodestate",
        },
    }
    assert snapshot["sample_counts"]["sport_mode_state"] == 1


def test_build_api_ingest_url_appends_unitree_state_path() -> None:
    assert build_api_ingest_url("http://127.0.0.1:8010/") == (
        "http://127.0.0.1:8010/unitree/state"
    )


def test_post_snapshot_to_api_posts_json(monkeypatch) -> None:
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"status":"accepted"}'

    def fake_urlopen(request, timeout):
        calls.append((request, timeout))
        return Response()

    monkeypatch.setattr("g1_bobby_unitree_bridge.listener.urlopen", fake_urlopen)

    response = post_snapshot_to_api(
        {"status": "receiving"},
        "http://api:8010",
        "token",
        timeout_s=3,
    )

    request, timeout = calls[0]
    assert response == {"status": "accepted"}
    assert request.full_url == "http://api:8010/unitree/state"
    assert request.headers["X-operator-token"] == "token"
    assert timeout == 3
