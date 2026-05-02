from __future__ import annotations


def build_unitree_source_trace() -> dict[str, object]:
    findings = [
        {
            "id": "sim_bridge_lowcmd_consumer",
            "source_path": "/opt/unitree/unitree_mujoco/simulate_python/unitree_sdk2py_bridge.py",
            "summary": (
                "Simulator bridge constructs ChannelSubscriber('rt/lowcmd', LowCmd_) and, on callback, "
                "maps tau + kp*(q-state) + kd*(dq-state) onto mujoco ctrl."
            ),
            "kind": "confirmed",
        },
        {
            "id": "sim_bridge_state_publishers",
            "source_path": "/opt/unitree/unitree_mujoco/simulate_python/unitree_sdk2py_bridge.py",
            "summary": (
                "Simulator bridge publishes rt/lowstate and rt/sportmodestate continuously from mujoco state."
            ),
            "kind": "confirmed",
        },
        {
            "id": "g1_low_level_motion_switcher",
            "source_path": "/opt/unitree/unitree_sdk2_python/example/g1/low_level/g1_low_level_example.py",
            "summary": (
                "Official G1 low-level example releases MotionSwitcher mode, waits for low_state.mode_machine, "
                "then publishes rt/lowcmd every 2ms with motor_cmd.mode=1 and non-zero gains."
            ),
            "kind": "confirmed",
        },
        {
            "id": "g1_low_level_motor_count",
            "source_path": "/opt/unitree/unitree_sdk2_python/example/g1/low_level/g1_low_level_example.py",
            "summary": "Official example drives 29 G1 motors even though HG LowCmd_ IDL carries 35 slots.",
            "kind": "confirmed",
        },
        {
            "id": "g1_loco_request_surface",
            "source_path": "/opt/unitree/unitree_ros2/example/src/include/g1/g1_loco_client.hpp",
            "summary": (
                "Official G1 ROS2 high-level loco client uses /api/sport/request and /api/sport/response "
                "for SetFsmId and SetVelocity."
            ),
            "kind": "confirmed",
        },
        {
            "id": "dds_rejection_inference",
            "source_path": "/opt/unitree/unitree_mujoco/simulate_python/unitree_sdk2py_bridge.py",
            "summary": (
                "Because the Python simulator bridge registers a lowcmd subscriber directly, a write rejection "
                "before callback likely points to DDS routing/registration or simulator bring-up state, not "
                "to the callback math itself."
            ),
            "kind": "inference",
        },
    ]
    return {
        "status": "ok",
        "findings": findings,
        "summary": {
            "confirmed": sum(1 for item in findings if item["kind"] == "confirmed"),
            "inferences": sum(1 for item in findings if item["kind"] == "inference"),
        },
    }
