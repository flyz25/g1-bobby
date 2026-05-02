#!/usr/bin/env bash
set -eu

cd "$(dirname "$0")/.."

docker compose -f compose.unitree.yml --profile unitree run --rm unitree-ros2 \
  g1-bobby-unitree-diagnostic-report \
  --network-interface "${G1_BOBBY_UNITREE_NETWORK_INTERFACE:-eth0}" \
  --transport "${G1_BOBBY_UNITREE_COMMAND_TRANSPORT:-sdk_real}" \
  --probe-lowcmd-write
